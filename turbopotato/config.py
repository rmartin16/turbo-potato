from os import environ
from pkg_resources import resource_filename
from pathlib import Path


def get_line(file: Path, line: int = 1):
    contents = None
    try:
        with open(file, 'r') as f:
            for _ in range(line):
                contents = f.readline().rstrip()
    except (IOError, OSError) as e:
        print(f'ERROR: Failed to read "{file}": {e}')
    return contents


class Config:
    host = environ.get('TP_QBITTORRENT_CONFIG_HOST')
    qbittorrent_host = host or get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 1)[len('HOST:'):]

    port = environ.get('TP_QBITTORRENT_CONFIG_PORT')
    qbittorrent_port = port or get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 2)[len('PORT:'):]

    username = environ.get('TP_QBITTORRENT_CONFIG_USERNAME')
    qbittorrent_username = username or get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 3)[len('USERNAME:'):]

    password = environ.get('TP_QBITTORRENT_CONFIG_PASSWORD')
    qbittorrent_password = password or get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 4)[len('PASSWORD:'):]

    tvdb_key = environ.get('TP_TVDB_API_KEY')
    TVDB_API_KEY = tvdb_key or get_line(Path(resource_filename(__name__, 'TVDB_API_KEY')))

    tmdb_key = environ.get('TP_TMDB_API_KEY')
    TMDB_API_KEY = tmdb_key or get_line(Path(resource_filename(__name__, 'TMDB_API_KEY')))

    gmail_password = environ.get('TP_GMAIL_APP_PASSWORD')
    GMAIL_APP_PASSWORD = gmail_password or get_line(Path(resource_filename(__name__, 'GMAIL_APP_PASSWORD')))


config = Config()
