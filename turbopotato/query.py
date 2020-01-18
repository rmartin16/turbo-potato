from functools import partial
import logging
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from multiprocessing.pool import ThreadPool
from requests import HTTPError
from string import punctuation
from typing import List, Tuple, Union

import tvdbsimple as tvdb
import tmdbsimple as tmdb

from turbopotato.config import config
from turbopotato.media_defs import MediaNameParse
from turbopotato.media_defs import QueryResult
from turbopotato.media_defs import MediaType

logger = logging.getLogger(__name__)
MAX_THREADS = 30
Q = '"'

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

    @staticmethod
    def calculate_match_score(source: list, target: list, target_aired_date: str = ''):
        def clean_and_tokenize(token_list) -> set:
            if token_list == '':
                return set()
            token_list = token_list.lower()
            token_list = token_list.replace('.', ' ')
            # string = string.translate({ord(ch): None for ch in '0123456789'})
            token_list = token_list.strip()
            tokens = word_tokenize(token_list)
            stop_words = set(stopwords.words('english'))
            stop_words.update(punctuation)
            tokens = set(w for w in tokens if w not in stop_words)
            return tokens

        def tokenize(input_list: Union[List[str], Tuple[str], str]) -> set:
            tokens = ''
            if isinstance(input_list, str):
                input_list = [input_list]
            assert isinstance(input_list, (List, Tuple))
            for token in input_list:
                ''' convert list to string '''
                if isinstance(token, (list, tuple)):
                    try:
                        token = ' '.join(token)
                    except TypeError:
                        logger.error(f'Input token could not be joined as a string: {type(token)}. Token: {token}')
                        continue
                tokens = tokens + ' ' + token
            return clean_and_tokenize(tokens)

        source_tokens = tokenize(source)
        target_tokens = tokenize(target)
        aired_date_tokens = tokenize(target_aired_date.replace('-', ' '))

        # only use numbers against the aired date
        intersection = {v for v in source_tokens if v.isnumeric() is False} & target_tokens
        intersection_aired_date = source_tokens & aired_date_tokens
        score = len(intersection) + len(intersection_aired_date)

        if score:
            logger.debug(f'Score: {score} '
                         f'Source tokens: {source_tokens} '
                         f'Target tokens: {target_tokens} '
                         f'{f"Aired date tokens: {aired_date_tokens} " if aired_date_tokens else ""}')

        return score

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

        parent_title = parent_parts.title if parent_parts else ''
        parent_year = parent_parts.year if parent_parts else ''
        ''' search for series with title '''
        for title, year in ((parts.title, parts.year), (parent_title, parent_year)):
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
            if series.get('seriesName').lower() in (parts.title.lower(), parent_title.lower()):
                add_unique_elements(self.series_exact_match_list, series)

    def _get_episodes_from_season_and_episode_no(self, series: dict = None, parts: MediaNameParse = None):
        if not parts:
            return
        season = parts.season
        episode = parts.episode
        if series is None or season == '' or episode == '':
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
        parse_tokens = [parts.title, parts.episode_name, parts.group, parts.excess]

        if parse_tokens:
            logger.debug(f'Fuzzy matching against {series["seriesName"]}')
            logger.debug(f'Search tokens: {parse_tokens}')

            all_episode_list = []
            try:
                logger.debug(f'Querying for all episodes for {series.get("seriesName")}...')
                all_episode_list = tvdb.Series_Episodes(id=series.get('id')).all()
                logger.debug(f'TVDB returned {len(all_episode_list)} episodes.')
            except HTTPError as e:
                logger.debug(f'TVDB returned zero episodes: Error: {err_str(e)}')

            for episode in (e for e in all_episode_list if e.get('episodeName')):
                score = self.calculate_match_score(source=parse_tokens,
                                                   target=episode.get('episodeName', ''),
                                                   target_aired_date=episode.get('firstAired', ''))
                if score > 0:
                    logger.debug(f'Found episode "{episode.get("episodeName")} for "{series.get("seriesName")}')
                    episode['_fuzzy_score'] = score
                    episode['_series'] = series
                    add_unique_elements(self.fuzzy_episode_matches, episode)


class TMDBQuery(DBQuery):
    TMDB_API_KEY = ""  # override key in file

    def __init__(self):
        super().__init__()
        self.exact_movie_list = list()
        self.fuzzy_movie_list = list()

    def query(self, parts: MediaNameParse = None):
        tmdb.API_KEY = TMDBQuery.TMDB_API_KEY or config.TMDB_API_KEY
        logger.info('>>> Starting TMDB query...')
        if not parts:
            logger.error('Query aborted. MediaNameParse is None.')
            return

        self._get_movies(parts=parts)

        self.print_query_summary()
        logger.info('<<< Finished TMDB query')
        return self

    def _get_movies(self, parts: MediaNameParse):
        def desc(r):
            return f'{[m.get("original_title") + " (" + m.get("release_date")[:4] + ")" for m in r]}'

        results = list()
        if parts.movie_id:
            try:
                results = tmdb.Movies(parts.movie_id).info().get("results")
            except HTTPError as e:
                logger.debug(f'Error: {err_str(e)}')
            logger.debug(f'TMDB returned {len(results)} movies for movie ID {parts.movie_id}: {desc(results)}')

        if results:
            return results

        search_terms = [(parts.title, parts.year)]
        if parts.parent_parts and parts.parent_parts.title:
            search_terms.append((parts.parent_parts.title, parts.parent_parts.year))
        for title, year in search_terms:
            if title and year:
                try:
                    results = tmdb.Search().movie(query=title, year=year).get('results')
                except HTTPError as e:
                    logger.debug(f'Error: {err_str(e)}')

            if not results:
                try:
                    results = tmdb.Search().movie(query=title).get('results')
                except HTTPError as e:
                    logger.debug(f'Error: {err_str(e)}')

            if results:
                for movie in results:
                    if title.lower() == movie['title'].lower().translate(str.maketrans('', '', punctuation)):
                        logger.debug(f'Found exact match for "{title}{f" ({year}){Q}" if year else f"{Q}"}.')
                        add_unique_elements(self.exact_movie_list, movie)
                    else:
                        score = self.calculate_match_score(source=title, target=movie['title'])
                        if score:
                            logger.debug(f'Found fuzzy match for "{title}": {movie["title"]}')
                            add_unique_elements(self.fuzzy_movie_list, movie)
                if self.exact_movie_list:
                    break
            else:
                logger.debug(f'TMDB returned zero results for "{title}{f" ({year}){Q}" if year else f"{Q}"}.')

        self.exact_matches = [QueryResult(data=movie, media_type=MediaType.MOVIE) for movie in self.exact_movie_list]
        self.fuzzy_matches = [QueryResult(data=movie, media_type=MediaType.MOVIE) for movie in self.fuzzy_movie_list]
