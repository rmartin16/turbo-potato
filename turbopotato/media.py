from copy import copy
import logging
from pathlib import Path, PurePosixPath
from typing import List, Union

from turbopotato.exceptions import NoMediaFiles
from turbopotato.helpers import clean_path_part
from turbopotato.helpers import MediaNameParse
from turbopotato.helpers import MediaType
from turbopotato.helpers import QueryResult
from turbopotato.parser import parse
from turbopotato.query import DBQuery
from turbopotato.query import TMDBQuery
from turbopotato.query import TVDBQuery
from turbopotato.torrents import torrents
from turbopotato.transit import send_file

logger = logging.getLogger(__name__)

MEDIA_ROOT = PurePosixPath("/volume1/Media/")
DOCUMENTARY_SINGLES_PATH = MEDIA_ROOT / "Documentaries (Singles)"
DOCUMENTARY_SERIES_PATH = MEDIA_ROOT / "Documentaries (Series)"
COMEDY_PATH = MEDIA_ROOT / "Comedy"
MOVIES_PATH = MEDIA_ROOT / "Movies"
TV_SHOWS_PATH = MEDIA_ROOT / "TV Shows"


class File:
    def __init__(self, filepath: Path = None):
        self.filepath = filepath
        self.original_torrent_state = None
        self.torrent_hash = None

        self.success = False
        self.skip = False
        self.failure_reason = ''

        self._parts: MediaNameParse = None
        self.query: DBQuery = None
        self._chosen_one: QueryResult = None

    @property
    def parts(self):
        return self._parts

    @parts.setter
    def parts(self, v: MediaNameParse):
        self.chosen_one = None
        self._parts = v

    @property
    def chosen_one(self) -> Union[QueryResult, None]:
        if self._chosen_one:
            return self._chosen_one

        if self.query and len(self.query.exact_matches) == 1:
            self._chosen_one = self.query.exact_matches[0]

        max_score_list = [r for r in self.query.fuzzy_matches
                          if r.fuzzy_match_score == max([r.fuzzy_match_score for r in self.query.fuzzy_matches])]
        if len(max_score_list) == 1:
            self._chosen_one = max_score_list[0]

        return self._chosen_one

    @chosen_one.setter
    def chosen_one(self, v: QueryResult):
        self._chosen_one = v

    @property
    def destination_directory(self) -> Union[PurePosixPath, None]:
        if not self.chosen_one:
            return None

        if self.chosen_one.media_type is MediaType.MOVIE:
            if self.chosen_one.title and self.chosen_one.year:
                top_directory = f'{self.chosen_one.title} ({self.chosen_one.year})'

                if self.chosen_one.is_comedy():
                    root = COMEDY_PATH
                elif self.chosen_one.is_documentary():
                    root = DOCUMENTARY_SINGLES_PATH
                else:
                    root = MOVIES_PATH

                return PurePosixPath(root, clean_path_part(top_directory))

        elif self.chosen_one.media_type is MediaType.SERIES:
            if self.chosen_one.title and self.chosen_one.season != '':
                show_directory = self.chosen_one.title
                season_directory = f'Season {self.chosen_one.season}'

                if self.chosen_one.is_documentary():
                    root = DOCUMENTARY_SERIES_PATH
                else:
                    root = TV_SHOWS_PATH

                return PurePosixPath(root, clean_path_part(show_directory), clean_path_part(season_directory))

        return None

    @property
    def destination_filename(self) -> Union[str, None]:
        if self.chosen_one.media_type is MediaType.MOVIE:
            return clean_path_part(self.filepath.name)
        else:
            if all(getattr(self.chosen_one, a) != '' for a in ('title', 'season', 'episode', 'episode_name')):
                return '%s - S%02dE%02d - %s%s' % (
                    clean_path_part(self.chosen_one.title),
                    int(clean_path_part(self.chosen_one.season)),
                    int(clean_path_part(self.chosen_one.episode)),
                    clean_path_part(self.chosen_one.episode_name),
                    clean_path_part(self.filepath.suffix)
                )
        return None

    def identify_media(self):
        query_precedence = (TMDBQuery(parts=self.parts), TVDBQuery(parts=self.parts))

        if self.parts.media_type is MediaType.SERIES:
            query_precedence = tuple(reversed(query_precedence))

        self.query = query_precedence[0].query()
        if not self.query.is_matches:
            self.query = query_precedence[1].query()

        for count, result in enumerate(self.query.exact_matches):
            logger.info(f'{count} {result}')


class Media:
    def __init__(self, files: set = None, handle_torrents: bool = False):
        self.files: Union[List[File], None] = list(map(File, files)) if files else None
        self.handle_torrents = handle_torrents

        if self.handle_torrents:
            self._find_torrent_for_each_file()

        if not self.files:
            raise NoMediaFiles

    def __iter__(self):
        return iter(self.files)

    def _find_torrent_for_each_file(self):
        files_copy = copy(self.files)
        self.files = list()

        for file in files_copy:
            # traverse the filepath parts backwards trying to find the torrent by name.
            # as long as a torrent name isn't changed, torrents will be the name of the file or one of its parent dirs
            torrent = next(filter(None, map(torrents.get_torrent, reversed(file.filepath.parts))), None)

            if torrent is None:
                logger.warning(f'Torrent not found. Skipping "{file.filepath}"')
                continue

            if torrents.is_already_transiting(torrent):
                logger.warning(f'Torrent ({torrent.name}) is already transiting. Skipping "{file.filepath}".')
                continue

            logger.debug(f'Using torrent "{torrent.name}" for "{file.filepath}"')
            file.torrent_hash = torrent.hash
            file.original_torrent_state = torrent
            self.files.append(file)

    def _unique_torrent_list(self):
        return list({file.original_torrent_state.hash: file.original_torrent_state for file in self.files}.values())

    def set_transiting(self):
        if self.handle_torrents:
            for torrent in self._unique_torrent_list():
                logger.debug(f'Setting category to "transiting" for "{torrent.name}"')
                torrents.wrap_api_call(func=torrents.qbt_client.torrents_set_category,
                                       _hash=torrent.hash,
                                       hashes=torrent.hash,
                                       category='transiting')

    def unset_transiting(self):
        """
        if torrent is still marked transiting, restore back to original state.
        this is primarily to ensure torrents are not left in a transiting state when wrapping things up.
        """
        if self.handle_torrents:
            for torrent in self._unique_torrent_list():
                if torrents.is_already_transiting(torrents.get_torrent(torrent_hash=torrent.hash)):
                    logger.debug(f'Resetting category back to "{torrent.category}" for "{torrent.name}"')
                    torrents.wrap_api_call(func=torrents.qbt_client.torrents_set_category,
                                           _hash=torrent.hash,
                                           hashes=torrent.hash,
                                           category=torrent.category or '')

    def parse_filenames(self):
        for file in self.files:

            try:
                file.parts = parse(filepath=file.filepath)
            except Exception as e:
                file.failure_reason = f'Error during filename parsing: {e}'
                logger.exception(f'Error during filename parsing. Filename: {file.filepath.name}. Error: {e}')
            logger.debug(f'Parsed {file.filepath.name}: {file.parts.raw_parse}')

    def identify_media(self):
        for file in self.files:
            logger.info(f'')
            logger.info(f'>>> Starting identification for {file.filepath.name}...')
            file.identify_media()
            logger.info(f'<<< Finished identification for {file.filepath.name}.')

    def transit(self):
        for file in self.files:
            if not file.chosen_one or file.skip:
                continue

            logger.info(f'')
            logger.info(f'>>> Starting transit for {file.filepath.name}...')

            dest_dir = file.destination_directory
            dest_filename = file.destination_filename

            if not dest_dir or not dest_filename:
                file.failure_reason = f'Insufficient information to construct destination filepath.'
                logger.error(file.failure_reason)
                continue

            try:
                send_file(local_filepath=file.filepath, remote_filepath=dest_dir/dest_filename)
                file.success = True
            except Exception as e:
                file.failure_reason = f'Failed to transmit file. Error: {e}'
                logger.exception(file.failure_reason)

            logger.info(f'<<< Finished transit for {file.filepath.name}.')
