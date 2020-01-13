import logging
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from requests import HTTPError
from string import punctuation
from typing import List

import tvdbsimple as tvdb
import tmdbsimple as tmdb

from turbopotato.config import config
from turbopotato.helpers import MediaNameParse
from turbopotato.helpers import QueryResult
from turbopotato.helpers import MediaType

logger = logging.getLogger(__name__)


def err_str(e: Exception = None):
    return f'{getattr(e.response, "status_code", e)} ({type(e).__name__})'


def add_unique_elements(l, new_elements):
    if not new_elements:
        return
    if not isinstance(new_elements, list):
        new_elements = [new_elements]
    for new_element in new_elements:
        if new_element['id'] not in [e['id'] for e in l]:
            l.append(new_element)


class DBQuery:
    def __init__(self):
        self.exact_matches: List[QueryResult] = list()
        self.fuzzy_matches: List[QueryResult] = list()

    @property
    def is_matches(self):
        return bool(self.exact_matches or self.fuzzy_matches)

    @property
    def fuzzy_matches_sorted(self):
        return sorted(self.fuzzy_matches,
                      key=lambda m: (m.fuzzy_match_score, m.season, m.episode),
                      reverse=True)


class TVDBQuery(DBQuery):
    TVDB_API_KEY = ""  # override key in file

    def __init__(self, parts: MediaNameParse = None):
        super().__init__()
        self.parts = parts
        self.series_list = list()
        self.series_idx = dict()
        self.exact_episode_matches = list()
        self.fuzzy_episode_matches = list()

    def query(self):
        tvdb.KEYS.API_KEY = TVDBQuery.TVDB_API_KEY or config.TVDB_API_KEY
        logger.info('>>> Starting TVDB query...')

        self._get_series()
        self.series_idx = {s.get('id'): s for s in self.series_list}

        if self.parts.season != '' and self.parts.episode != '':
            for series in self.series_list:
                self._get_episodes_from_season_and_episode_no(series=series)
        if not self.exact_episode_matches:
            for series in self.series_list:
                self._get_episodes_from_episode_title(series=series)

        self.exact_matches = [QueryResult(data=e, media_type=MediaType.SERIES) for e in self.exact_episode_matches]
        self.fuzzy_matches = [QueryResult(data=e, media_type=MediaType.SERIES) for e in self.fuzzy_episode_matches]

        logger.info(f'Found {len(self.exact_episode_matches)} exact matches and '
                    f'{len(self.fuzzy_episode_matches)} fuzzy matches.')
        logger.info('<<< Finished TVDB query')
        return self

    def _get_series(self):
        ''' use defaulted series ID '''
        if self.parts.series_id:
            try:
                logger.debug(f'Querying for series using series ID "{self.parts.series_id}"...')
                results = tvdb.Series(id=self.parts.series_id).info()
                add_unique_elements(self.series_list, results)
                logger.debug(f'Found {len(results)} series: {[s["seriesName"] for s in results]}')
            except HTTPError as e:
                logger.error(f'TVDB could not find series using defaulted series ID "{self.parts.series_id}". Error: {err_str(e)}')

        ''' search for series with title '''
        if not self.series_list:
            searches = ((self.parts.title, self.parts.year),
                        (getattr(self.parts.parent_parts, 'title', None), getattr(self.parts.parent_parts, 'year', None)))
            for title, year in searches:
                results = None
                if title and year:
                    try:
                        logger.debug(f'Querying for series using "{title}" and "{year}"...')
                        results = tvdb.Search().series(name=f'{title}, {year}')
                        add_unique_elements(self.series_list, results)
                        logger.debug(f'Found {len(results)} series: {[s["seriesName"] for s in results]}')
                    except HTTPError as e:
                        logger.debug(f'TVDB returned zero series\'. Error: {err_str(e)}')
                if title and not results:
                    try:
                        logger.debug(f'Querying for series using "{title}"...')
                        results = tvdb.Search().series(name=title)
                        add_unique_elements(self.series_list, results)
                        logger.debug(f'Found {len(results)} series: {[s["seriesName"] for s in results]}')
                    except HTTPError as e:
                        logger.debug(f'TVDB returned zero series\'. Error: {err_str(e)}')

    def _get_episodes_from_season_and_episode_no(self, series: dict = None):
        if series is None:
            return

        try:
            logger.debug(f'Querying for episodes for "{series.get("seriesName")}" using season {self.parts.season} '
                         f'and episode {self.parts.episode}...')
            results = tvdb.Series_Episodes(id=series.get('id'),
                                           airedSeason=self.parts.season,
                                           airedEpisode=self.parts.episode
                                           ).all()
            results = list(map(lambda r: dict(r, _series=series), results))
            add_unique_elements(self.exact_episode_matches, results)
            logger.debug(f'Found {len(results)} episodes: {[e.get("episodeName") for e in results]}')
        except HTTPError as e:
            logger.debug(f'TVDB returned zero episodes. Error: {err_str(e)}')

    def _get_episodes_from_episode_title(self, series: dict = None):
        if series is None:
            return
        ''' use free-text output from parser to match against episode titles '''
        fn_tokens = ''
        for fn_part in ['episode_name', 'group', 'excess']:
            detail = getattr(self.parts, fn_part, None)
            ''' convert list to string '''
            if isinstance(detail, list):
                detail = ' '.join(detail)
            if detail is None:
                continue
            fn_tokens = fn_tokens + ' ' + detail
        fn_tokens = self._clean_and_tokenize(fn_tokens)

        if fn_tokens:
            logger.debug(f'Fuzzy matching against {series["seriesName"]}')
            logger.debug(f'Search tokens: {fn_tokens}')
            all_episode_list = []
            try:
                logger.debug(f'Querying for all episodes for {series.get("seriesName")}...')
                all_episode_list = tvdb.Series_Episodes(id=series.get('id')).all()
                logger.debug(f'TVDB returned {len(all_episode_list)} episodes.')
            except HTTPError as e:
                logger.debug(f'TVDB returned zero episodes: Error: {err_str(e)}')

            for episode in (e for e in all_episode_list if e.get('episodeName')):
                episode_title_tokens = self._clean_and_tokenize(episode.get('episodeName'))
                aired_date_tokens = self._clean_and_tokenize(episode['firstAired'].replace('-', ' '))

                ''' first find any intersection between filename and database episode title (skip numbers) '''
                intersection = [value for value in fn_tokens if
                                value in episode_title_tokens and value.replace('.', '', 1).isdigit() is False]
                '''' then look for matches between filename (including numbers) and aired date '''
                intersection.extend([value for value in fn_tokens if value in aired_date_tokens])
                if intersection:
                    logger.debug(f'Intersection: {intersection} Episode tokens: {episode_title_tokens} Episode name: {episode.get("episodeName")}')
                    episode['_fuzzy_score'] = len(intersection)
                    episode['_series'] = series
                    add_unique_elements(self.fuzzy_episode_matches, episode)

    @staticmethod
    def _clean_and_tokenize(token_list):
        if token_list == '':
            return []
        token_list = token_list.lower()
        token_list = token_list.replace('.', ' ')
        # string = string.translate({ord(ch): None for ch in '0123456789'})
        token_list = token_list.strip()
        tokens = word_tokenize(token_list)
        stop_words = set(stopwords.words('english'))
        stop_words.update(punctuation)
        token_list = list(set(w for w in tokens if w not in stop_words))
        return token_list


class TMDBQuery(DBQuery):
    TMDB_API_KEY = ""  # override key in file

    def __init__(self, parts: MediaNameParse = None):
        super().__init__()
        self.parts = parts
        self.movie_list = list()

    def query(self):
        def desc(r):
            return f'{[m.get("original_title") + " (" + m.get("release_date")[:4] + ")" for m in r.get("results")]}'

        tmdb.API_KEY = TMDBQuery.TMDB_API_KEY or config.TMDB_API_KEY
        logger.info('>>> Starting TMDB query...')

        if self.parts.movie_id:
            try:
                logger.debug(f'Query for movie ID {self.parts.movie_id}...')
                response = tmdb.Movies(self.parts.movie_id).info()
                logger.debug(f'TMDB returned {len(response.get("results"))} movies: {desc(response)}')
            except HTTPError as e:
                logger.debug(f'TMDB returned zero results. Error: {err_str(e)}')

        title = self.parts.title
        year = self.parts.year
        response = dict()
        try:
            logger.debug(f'Query for "{title}" and year "{year}"...')
            response = tmdb.Search().movie(query=title, year=year)
            logger.debug(f'TMDB returned {len(response.get("results"))} movies: {desc(response)}')
        except HTTPError as e:
            logger.debug(f'TMDB returned zero results. Error: {err_str(e)}')

        if 'results' not in response:
            try:
                logger.debug(f'Query for "{title}"...')
                response = tmdb.Search().movie(query=title)
                logger.debug(f'TMDB returned {len(response.get("results"))} movies: {desc(response)}')
            except HTTPError as e:
                logger.debug(f'TMDB returned zero results. Error: {err_str(e)}')

        add_unique_elements(self.movie_list, response.get('results'))

        self.exact_matches = [QueryResult(data=movie, media_type=MediaType.MOVIE) for movie in self.movie_list]

        logger.info(f'Found {len(self.movie_list)} matches.')
        logger.info('<<< Finished TMDB query')
        return self
