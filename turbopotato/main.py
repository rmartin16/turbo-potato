import logging
from typing import Union, List, Tuple, AnyStr

from tvdbsimple.base import AuthenticationError

from turbopotato.arguments import args
from turbopotato.exceptions import NoMediaFiles
from turbopotato.log import Log
from turbopotato.media import Media
from turbopotato.notify import notify
from turbopotato.prompt import prompt
from turbopotato.torrents import qBittorrentError

logger = logging.getLogger('main')


def main(args_override: list = None):
    args.ingest_arguments(args_override=args_override)
    logs = Log()
    try:
        args.process_arguments()
        media = Media()
        media.set_transiting()
        media.parse_filenames()
        media.identify_media()
        prompt(media=media)
        media.transit()
        notify(media=media, logs=logs)
    except NoMediaFiles:
        logger.error(f'No media files to process. Aborting.')
    except qBittorrentError as e:
        logger.error(f'Error communicating with qBittorrent: {e}')
    except AuthenticationError as e:
        logger.error(f'Error communicating with theTVDB: {e}')
    except Exception as e:
        logger.error(f'Unhandled exception: {e}', exc_info=True)
    except KeyboardInterrupt:
        logger.info(f'KeyboardInterrupt. Exiting.')
    finally:
        if 'media' in locals():
            media.update_torrents()
        logs.delete_logs()


def run(paths: Union[List, Tuple, AnyStr] = None, torrents: bool = False, force_torrent_deletion: bool = False,
        ask_for_torrent_update: bool = False, skip_torrent_updates: bool = False, log_level: str = None,
        interactive: bool = True, no_notification_on_failure: bool = False):
    args_override = list()
    if torrents:
        args_override.append('--torrents')
    if force_torrent_deletion:
        args_override.append('--force-torrent-deletion')
    if ask_for_torrent_update:
        args_override.append('--ask-for-torrent-updates')
    if skip_torrent_updates:
        args_override.append('--skip-torrent-updates')
    if log_level:
        args_override.append('--log_level')
        args_override.append(log_level)
    if not interactive:
        args_override.append('--non-interactive')
    if no_notification_on_failure:
        args_override.append('--no-notification-on-failure')
    if paths:
        if isinstance(paths, (list, tuple)):
            args_override.extend(paths)
        else:
            args_override.append(paths)

    main(args_override=args_override or None)


if __name__ == '__main__':
    main()

