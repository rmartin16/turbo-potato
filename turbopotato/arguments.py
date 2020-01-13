import argparse
import logging
import os
from pathlib import Path

from turbopotato.exceptions import NoMediaFiles
from turbopotato.extensions import extensions
from turbopotato.torrents import torrents

logger = logging.getLogger(__name__)


class Arguments:
    def __init__(self):
        self.args = None
        self.torrents = None
        self.force_torrent_deletion = None
        self.ask_for_torrent_updates = None
        self.skip_torrent_updates = None
        self.log_level = None
        self.interactive = None
        self.no_notification_on_failure = None
        self.paths = list()
        self.files = set()

        self._parser = argparse.ArgumentParser()
        self._parser.add_argument('-t', '--torrents',
                                  action='store_true',
                                  help='specify if media files are part of a torrent in qBittorrent')
        self._parser.add_argument('-f', '--force-torrent-deletion',
                                  action='store_true',
                                  help='automatically delete torrent data ')
        self._parser.add_argument('-a', '--ask-for-torrent-updates',
                                  action='store_true',
                                  help='ask to perform torrent updates else perform automatically')
        self._parser.add_argument('-u', '--skip-torrent-updates',
                                  action='store_true',
                                  help='don\'t update torrents (move/delete/update)')
        self._parser.add_argument('-l', '--log_level',
                                  action='store',
                                  type=str,
                                  help='log level to display on console')
        self._parser.add_argument('--non_interactive', '--non-interactive',
                                  action='store_true',
                                  help='pass if running without interactivity')
        self._parser.add_argument('-n', '--no-notification-on-failure', '--no_notification_on_failure',
                                  action='store_true',
                                  help='don\'t send notifications if processing is unsuccessful')
        self._parser.add_argument('paths',
                                  nargs='+',
                                  type=str,
                                  help='files or directories to transmit')

    def ingest_arguments(self, args_override: list = None):
        self.args = self._parser.parse_args(args=args_override)

        self.torrents = self.args.torrents or False
        self.force_torrent_deletion = self.args.force_torrent_deletion or False
        self.ask_for_torrent_updates = self.args.ask_for_torrent_updates or False
        self.skip_torrent_updates = self.args.skip_torrent_updates or False
        self.log_level = self.args.log_level
        self.interactive = not self.args.non_interactive
        self.no_notification_on_failure = self.args.no_notification_on_failure or False
        self.paths = self.args.paths

    def process_arguments(self):
        full_paths = [os.path.abspath(os.path.realpath(os.path.expanduser(path))) for path in self.paths]
        for path in full_paths:
            if os.path.isfile(path):
                self._add_media_file(Path(path))
            elif os.path.isdir(path):
                for dir, _, dir_files in os.walk(path):
                    for file in dir_files:
                        self._add_media_file(Path(dir, file))
            else:
                logger.warning(f'Invalid path argument: {path}')

        if self.files:
            logger.debug('Files to process:')
            [logger.debug(f' {path}') for path in self.files]
        else:
            raise NoMediaFiles

        if self.torrents:
            torrents.qbt_client.auth_log_in()

    def _add_media_file(self, path: Path = None):
        minimum_subtitle_file_size = 10240  # 10KB
        if path is None:
            return
        file_extension = path.suffix
        if extensions.is_video_extension(ext=file_extension):
            try:
                size = os.stat(str(path)).st_size
            except Exception as e:
                size = minimum_subtitle_file_size
                logger.error(f'Failed to stat file "{path}": {e}')
            if extensions.is_subtitle_extension(ext=file_extension) and (size < minimum_subtitle_file_size):
                logger.debug(f'Skipping subtitle file smaller than 10KB: {path}')
            else:
                self.files.add(path)


args = Arguments()
