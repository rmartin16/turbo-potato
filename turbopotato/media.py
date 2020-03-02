from collections import namedtuple
from copy import copy
import logging
import os
from pathlib import Path, PurePosixPath
from typing import List, Union

import PyInquirer

from turbopotato.arguments import args
from turbopotato.exceptions import NoMediaFiles
from turbopotato.media_defs import clean_path_part
from turbopotato.media_defs import MediaNameParse
from turbopotato.media_defs import MediaType
from turbopotato.media_defs import QueryResult
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

FileGroup = namedtuple('FileGroup', 'success files name')


class File:
    def __init__(self, filepath: Path = None):
        self.filepath = filepath
        self.original_torrent = None
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

        if self._chosen_one is None:
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
        if not self.chosen_one:
            return None

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
        query_precedence = (TMDBQuery(), TVDBQuery())

        if self.parts.media_type is MediaType.SERIES:
            query_precedence = tuple(reversed(query_precedence))

        self.query = query_precedence[0].query(parts=self.parts)
        if not self.query.is_matches:
            self.query = query_precedence[1].query(parts=self.parts)


class Media:
    def __init__(self):
        self.files: Union[List[File], None] = list(map(File, args.files)) if args.files else None

        if args.torrents:
            self._find_torrent_for_each_file()

        if not self.files:
            raise NoMediaFiles
        else:
            logger.debug('Files to process:')
            for file_group in self.get_file_groups():
                logger.debug(f' {file_group.name}')
                for file in file_group.files:
                    logger.debug(f'  {file.filepath.name}')

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

            if torrents.is_transiting(torrent):
                logger.warning(f'Torrent "({torrent.name})" is already transiting. Skipping "{file.filepath}"')
                continue

            if torrent.category == 'skip upload' and not args.interactive:
                logger.warning(f'Torrent category is "{torrent.category}", Skipping "{file.filepath}"')
                continue

            logger.debug(f'Using torrent "{torrent.name}" for "{file.filepath}"')
            file.torrent_hash = torrent.hash
            file.original_torrent = torrent
            self.files.append(file)

    def get_file_groups(self) -> List[FileGroup]:
        file_groups = list()
        if args.torrents:
            for torrent_hash in set(f.torrent_hash for f in self.files):
                files = [f for f in self.files if f.torrent_hash == torrent_hash]
                file_groups.append(
                    FileGroup(
                        success=all(f.success for f in files),
                        files=files,
                        name=files[0].original_torrent.name
                    )
                )
        else:
            file_groups.append(
                FileGroup(
                    success=all(f.success for f in self.files),
                    files=self.files,
                    name=Path(os.path.commonprefix([str(f.filepath) for f in self.files])).name
                )
            )

        return file_groups

    def set_transiting(self):
        if args.torrents:
            for torrent in list({file.original_torrent.hash: file.original_torrent for file in self.files}.values()):
                logger.debug(f'Setting category to "transiting" for "{torrent.name}"')
                torrents.wrap_api_call(func=torrents.qbt_client.torrents_set_category,
                                       hashes=torrent.hash,
                                       category='transiting')

    def update_torrents(self):
        """
        follow rules to appropriately update category.
        if torrent is still marked transiting, restore back to original state.
        this is primarily to ensure torrents are not left in a transiting state when wrapping things up.
        """
        torrents_root_dir = '/home/user/torrents/'
        delete_categories = ('errored delete after upload', 'delete after upload')
        skip_update_categories = ('skip update after upload',)

        if args.torrents:
            update_torrents = not args.skip_torrent_updates
            if update_torrents and args.ask_for_torrent_updates:
                update_torrents = PyInquirer.prompt(questions={'type': 'confirm',
                                                               'name': 'update',
                                                               'message': 'Update torrents?'}).get('update', False)
            if update_torrents:
                for file_group in self.get_file_groups():
                    category = None
                    location = None
                    torrent = file_group.files[0].original_torrent
                    if torrent.category not in skip_update_categories:
                        if file_group.success:
                            if args.force_torrent_deletion or torrent.category in delete_categories:
                                logger.info(f'Deleting {torrent.name}')
                                torrents.wrap_api_call(torrents.qbt_client.torrents_delete,
                                                       delete_files=True,
                                                       hashes=torrent.hash)
                            else:
                                category = 'uploaded'
                                location = '1completed'
                        elif torrent.category in delete_categories:
                            category = 'errored delete after upload'
                            location = '2errored'
                        elif not torrent.category:
                            category = 'errored'
                            location = '2errored'
                        if location:
                            logger.info(f'Moving "{torrent.name}" to "{location}" directory')
                            torrents.wrap_api_call(torrents.qbt_client.torrents_set_location,
                                                   location=torrents_root_dir + location,
                                                   hashes=torrent.hash)
                        if category:
                            logger.info(f'Setting category to "{category}" for "{torrent.name}"')
                            torrents.wrap_api_call(torrents.qbt_client.torrents_set_category,
                                                   category=category,
                                                   hashes=torrent.hash)

            # one last roll through to ensure torrents are not left as 'transiting'
            for torrent in list({file.original_torrent.hash: file.original_torrent for file in self.files}.values()):
                if torrents.is_transiting(torrent_hash=torrent.hash):
                    logger.info(f'Resetting category back to "{torrent.category}" for "{torrent.name}"')
                    torrents.wrap_api_call(func=torrents.qbt_client.torrents_set_category,
                                           hashes=torrent.hash,
                                           category=torrent.category or '')

    def parse_filenames(self):
        for file in self.files:
            try:
                file.parts = parse(filepath=file.filepath)
            except Exception as e:
                file.failure_reason = f'Error during filename parsing: {e}'
                logger.exception(f'Error during filename parsing. Filename: {file.filepath.name}. Error: {e}')
            logger.debug(f'Parsed {file.filepath.name}: {file.parts}')
            if file.parts.parent_parts:
                logger.debug(f'Parsed parent {file.filepath.parent}: {file.parts.parent_parts}')

    def identify_media(self):
        for file in self.files:
            logger.info(f'')
            logger.info(f'>>> Starting identification for {file.filepath.name}...')
            file.identify_media()
            logger.info(f'<<< Finished identification for {file.filepath.name}.')

    def transit(self):
        for file in self.files:
            logger.info(f'')
            logger.info(f'>>> Starting transit for {file.filepath.name}...')
            if not file.chosen_one or file.skip:
                logger.warning(f'Cannot transit. Chosen one: {file.chosen_one}. Skip file: {file.skip}.')
                continue

            dest_dir = file.destination_directory
            dest_filename = file.destination_filename

            if not dest_dir or not dest_filename:
                file.failure_reason = f'Insufficient information to construct destination filepath.'
                logger.error(file.failure_reason)
                continue

            try:
                send_file(local_filepath=file.filepath, remote_filepath=dest_dir/dest_filename)
                logger.info('File successfully transited')
                file.success = True
            except Exception as e:
                file.failure_reason = f'Failed to transmit file. Error: {e}'
                logger.exception(file.failure_reason)

            logger.info(f'<<< Finished transit for {file.filepath.name}.')
