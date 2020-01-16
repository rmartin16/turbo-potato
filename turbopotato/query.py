from functools import partial
import logging
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from multiprocessing.pool import ThreadPool
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
MAX_THREADS = 30


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

    def print_query_summary(self):
        total_exact_matches = len(self.exact_matches)
        total_fuzzy_matches = len(self.fuzzy_matches)
        logger.info(f'Found {total_exact_matches} exact matches and {total_fuzzy_matches} fuzzy matches.')
        total = total_exact_matches + total_fuzzy_matches
        done = False
        for name, matches in {'Exact matches': self.exact_matches, 'Fuzzy matches': self.fuzzy_matches_sorted}.items():
            if matches:
                logger.info(f'{name}:')
                pad = len(str(len(matches)))
                for count, result in enumerate(matches):
                    if count > 9:
                        logger.info(f'{total - count} matches not printed...')
                        done = True
                        break
                    logger.info(f' {count + 1:{pad}d} {result}')
                if done:
                    break


class TVDBQuery(DBQuery):
    TVDB_API_KEY = ""  # override key in file

    def __init__(self):
        super().__init__()
        self.series_list = list()
        self.series_exact_match_list = list()
        self.exact_episode_matches = list()
        self.fuzzy_episode_matches = list()

    def query(self, parts: MediaNameParse = None):
        tvdb.KEYS.API_KEY = TVDBQuery.TVDB_API_KEY or config.TVDB_API_KEY
        logger.info('>>> Starting TVDB query...')
        if not parts:
            logger.error('Query aborted. MediaNameParse is None.')
            return

        self._get_series(parts=parts, parent_parts=parts.parent_parts)

        for series_list in (self.series_exact_match_list, self.series_list):
            if not series_list:
                continue
            threads = MAX_THREADS if len(series_list) > MAX_THREADS else len(series_list)
            with ThreadPool(processes=threads) as pool:
                if parts.season != '' and parts.episode != '':
                    pool.map(partial(self._get_episodes_from_season_and_episode_no, parts=parts), series_list)
                if not self.exact_episode_matches:
                    pool.map(partial(self._get_episodes_from_episode_title, parts=parts), series_list)
            if self.exact_episode_matches or self.fuzzy_episode_matches:
                break

        self.exact_matches = [QueryResult(data=e, media_type=MediaType.SERIES) for e in self.exact_episode_matches]
        self.fuzzy_matches = [QueryResult(data=e, media_type=MediaType.SERIES) for e in self.fuzzy_episode_matches]

        self.print_query_summary()
        logger.info('<<< Finished TVDB query')
        return self

    @staticmethod
    def query_for_series(title: str = None):
        if not title:
            return
        try:
            return tvdb.Search().series(name=title)
        except HTTPError:
            return {}

    def _get_series(self, parts: MediaNameParse, parent_parts: MediaNameParse):
        ''' use defaulted series ID '''
        if parts.series_id:
            try:
                results = tvdb.Series(id=parts.series_id).info()
                add_unique_elements(self.series_list, results)
                logger.debug(f'Found "{results["seriesName"]}" for series ID "{parts.series_id}"')
            except HTTPError as e:
                logger.error(f'TVDB did not find series using defaulted series ID "{parts.series_id}". Error: {err_str(e)}')

        if self.series_list:
            return

        ''' search for series with title '''
        for title, year in ((parts.title, parts.year), (parent_parts.title, parent_parts.year)):
            results = None
            if title and year:
                try:
                    results = tvdb.Search().series(name=f'{title} {year}')
                    add_unique_elements(self.series_list, results)
                    logger.debug(f'Found {len(results)} series using "{title} {year}": {[s["seriesName"] for s in results]}')
                except HTTPError as e:
                    logger.debug(f'TVDB returned zero series\' using "{title} {year}". Error: {err_str(e)}')
            if title and not results:
                try:
                    results = tvdb.Search().series(name=title)
                    add_unique_elements(self.series_list, results)
                    logger.debug(f'Found {len(results)} series using "{title}": {[s["seriesName"] for s in results]}')
                except HTTPError as e:
                    logger.debug(f'TVDB returned zero series\' using "{title}". Error: {err_str(e)}')

        for series in self.series_list:
            if series.get('seriesName') in (parts.title, parts.parent_parts.title):
                add_unique_elements(self.series_exact_match_list, series)

    def _get_episodes_from_season_and_episode_no(self, series: dict = None, parts: MediaNameParse = None):
        if not parts:
            return
        season = parts.season
        episode = parts.episode
        if series is None or season is '' or episode is '':
            return

        try:
            results = tvdb.Series_Episodes(id=series.get('id'), airedSeason=season, airedEpisode=episode).all()
            results = list(map(lambda r: dict(r, _series=series), results))
            add_unique_elements(self.exact_episode_matches, results)
            logger.debug(f'Found {len(results)} episodes for "{series.get("seriesName")}" using season '
                         f'{season} and episode {episode}: {[e.get("episodeName") for e in results]}')
        except HTTPError as e:
            logger.debug(f'TVDB returned zero episodes for "{series.get("seriesName")}" using season '
                         f'{season} and episode {episode}. Error: {err_str(e)}')

    def _get_episodes_from_episode_title(self, series: dict = None, parts: MediaNameParse = None):
        if series is None or parts is None:
            return
        ''' use free-text output from parser to match against episode titles '''
        fn_tokens = ''
        for fn_part in ['title', 'episode_name', 'group', 'excess']:
            token = getattr(parts, fn_part, None)
            ''' convert list to string '''
            if isinstance(token, list):
                token = ' '.join(token)
            if not isinstance(token, str):
                logger.error(
                    f'Episode filename token is not a string: Name: {fn_part}. Type: {type(token)}. Token: {token}')
                continue
            fn_tokens = fn_tokens + ' ' + token
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
                    logger.debug(f'Found episode "{episode.get("episodeName")} for "{series.get("seriesName")}" '
                                 f'using "{fn_tokens}"')
                    logger.debug(
                        f'Intersection: {intersection} Episode tokens: {episode_title_tokens} Episode name: {episode.get("episodeName")}')
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

    def __init__(self):
        super().__init__()
        self.movie_list = list()

    def query(self, parts: MediaNameParse = None):
        def desc(r):
            return f'{[m.get("original_title") + " (" + m.get("release_date")[:4] + ")" for m in results]}'

        tmdb.API_KEY = TMDBQuery.TMDB_API_KEY or config.TMDB_API_KEY
        logger.info('>>> Starting TMDB query...')
        if not parts:
            logger.error('Query aborted. MediaNameParse is None.')
            return

        if parts.movie_id:
            try:
                results = tmdb.Movies(parts.movie_id).info().get("results")
                logger.debug(f'TMDB returned {len(results)} movies for movie ID {parts.movie_id}: {desc(results)}')
            except HTTPError as e:
                logger.debug(f'TMDB returned zero results for movie ID {parts.movie_id}. Error: {err_str(e)}')

        results = dict()
        if parts.title and parts.year:
            try:
                results = tmdb.Search().movie(query=parts.title, year=parts.year).get('results')
                logger.debug(
                    f'TMDB returned {len(results)} movies for "{parts.title}" and year "{parts.year}": {desc(results)}')
            except HTTPError as e:
                logger.debug(
                    f'TMDB returned zero results for "{parts.title}" and year "{parts.year}". Error: {err_str(e)}')

        if not results:
            try:
                results = tmdb.Search().movie(query=parts.title).get('results')
                logger.debug(f'TMDB returned {len(results)} movies for "{parts.title}": {desc(results)}')
            except HTTPError as e:
                logger.debug(f'TMDB returned zero results for "{parts.title}". Error: {err_str(e)}')

        add_unique_elements(self.movie_list, results)
        self.exact_matches = [QueryResult(data=movie, media_type=MediaType.MOVIE) for movie in self.movie_list]

        self.print_query_summary()
        logger.info('<<< Finished TMDB query')
        return self
