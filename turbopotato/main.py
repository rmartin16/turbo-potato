import logging

from turbopotato.arguments import args
from turbopotato.exceptions import NoMediaFiles
from turbopotato.log import Log
from turbopotato.media import Media
from turbopotato.notify import notify
from turbopotato.prompt import prompt
from turbopotato.torrents import qBittorrentError

logger = logging.getLogger(__name__)


def main():
    args.ingest_arguments()
    logs = Log()
    try:
        args.process_arguments()
        media = Media(files=args.files, handle_torrents=args.torrents)
        media.set_transiting()
        media.parse_filenames()
        media.identify_media()
        prompt(media=media)
        media.transit()
        notify(media=media, logs=logs)
    except NoMediaFiles as e:
        logger.error(f'No media files to process. Aborting.')
    except qBittorrentError as e:
        logger.error(f'Error communicating with qBittorrent: {e}')
    except Exception as e:
        logger.error(f'Unhandled exception: {e}', exc_info=True)
    finally:
        if 'media' in locals():
            media.unset_transiting()
        logs.delete_logs()


if __name__ == '__main__':
    main()
