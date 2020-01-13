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
    qbittorrent_host = get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 1)[len('HOST:'):]
    qbittorrent_port = get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 2)[len('PORT:'):]
    qbittorrent_username = get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 3)[len('USERNAME:'):]
    qbittorrent_password = get_line(Path(resource_filename(__name__, 'QBITTORRENT_CONFIG')), 4)[len('PASSWORD:'):]

    TVDB_API_KEY = get_line(Path(resource_filename(__name__, 'TVDB_API_KEY')))
    TMDB_API_KEY = get_line(Path(resource_filename(__name__, 'TMDB_API_KEY')))
    GMAIL_APP_PASSWORD = get_line(Path(resource_filename(__name__, 'GMAIL_APP_PASSWORD')))


config = Config()
