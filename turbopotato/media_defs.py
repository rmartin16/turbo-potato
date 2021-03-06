from enum import Enum
import logging
import string
import unidecode

logger = logging.getLogger('defs')


class MediaType(Enum):
    MOVIE = 1
    SERIES = 2


def clean_path_part(part: str = None,
                    whitelist=f'[]\'!-_.() {string.ascii_letters}{string.digits}',
                    replace: str = ''):
    """
    Sanitize part of a filepath to prevent upsetting the OS.

        1) Convert all characters to ASCII through transliteration
        2) Replace any provided 'replace' characters (likely spaces) with underscores
        3) Remove all non-whitelisted characters
        4) Trim leading and trailing whitespace

    :param part: string to be included in a filepath
    :param whitelist: allowed characters; other characters are simply omitted
    :param replace: list of characters to replace with an underscore
    :return: sanitized string
    """
    # downconvert characters to ascii
    part = str(part)
    part = unidecode.unidecode(part)

    # replace chars with underscores
    for r in replace:
        part = part.replace(r, '_')

    # keep only valid ascii chars
    # part = unicodedata.normalize('NFKD', unicode(part)).encode('ASCII', 'ignore').decode()

    # keep only whitelisted chars
    return ''.join(c for c in part if c in whitelist).strip()


class MediaName:
    def __init__(self, media_type: MediaType):
        self.media_type = media_type

        # minimum for transiting files
        self.title = ''
        self.year = ''
        self.episode_name = ''
        self.episode = ''
        self.season = ''

        # filename parser properties
        self.audio = ''
        self.codec = ''
        self.container = ''
        self.day = ''
        self.encoder = ''
        self.excess = ''
        self.extended = ''
        self.garbage = ''
        self.group = ''
        self.hardcoded = ''
        self.language = ''
        self.month = ''
        self.proper = ''
        self.quality = ''
        self.region = ''
        self.repack = ''
        self.resolution = ''
        self.website = ''
        self.widescreen = ''

        # TVDB and TMDB query results
        self.id = ''
        self.aliases = ''
        self.genre_ids = set()
        self.network = ''
        self.status = ''
        self.first_aired = ''

        # these can be used to force the query to find a specific
        # series or movie if name-based lookup is unreliable.
        self.series_id = None
        self.movie_id = None

        self.fuzzy_match_score = -1

    def __hash__(self):
        if self.media_type is MediaType.MOVIE:
            return hash(''.join((self.title, self.year)))
        elif self.media_type is MediaType.SERIES:
            return hash(''.join(map(str, (self.title, self.season, self.episode, self.episode_name))))
        else:
            return super().__hash__()

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            isinstance(self.media_type, MediaType) and isinstance(getattr(other, 'media_type'), MediaType) and
            self.media_type is getattr(other, 'media_type') and
            all(getattr(self, a) == getattr(other, a) for a in ('title', 'year', 'season', 'episode', 'episode_name'))
        )

    def is_documentary(self):
        return 99 in getattr(self, 'genre_ids', set())

    def is_comedy(self):
        return all(x in (getattr(self, 'genre_ids', set())) for x in [35, 99])

    def __repr__(self):
        return f'<{type(self).__name__}: {vars(self)}>'

    def __str__(self):
        if self.media_type is MediaType.SERIES:
            media_type_s = 'episode'
            name_s = f'{self.title}'
            name_s += f' ({self.network})' if self.network else ''
            try:
                season_s = f'{int(self.season):02d}'
            except (ValueError, TypeError):
                season_s = self.season
            try:
                episode_s = f'{int(self.episode):02d}'
            except (ValueError, TypeError):
                episode_s = self.episode
            name_s += f' - S{season_s}E{episode_s}' if season_s else ''
            name_s += f': {self.episode_name}' if self.episode_name else ''
        else:
            media_type_s = 'movie'
            name_s = f'{self.title}'
            name_s += f' ({self.year})' if self.year else ''

        group = self.group if isinstance(self.group, (list, tuple)) else [self.group]
        excess = self.excess if isinstance(self.excess, (list, tuple)) else [self.excess]
        extra = ', '.join(x for x in (list(map(str, group)) + list(map(str, excess))) if x)
        name_s += f' ({extra})' if extra else ''

        name_s += f' ({self.fuzzy_match_score})' if self.fuzzy_match_score != -1 else ''

        return f'({media_type_s.capitalize()}) {name_s}'


class MediaNameParse(MediaName):
    def __init__(self, media_type: MediaType, parent_parts=None, **data):
        super().__init__(media_type)
        self.parent_parts: MediaNameParse = parent_parts

        self.raw_parse = data

        key_map = {'episodeName': 'episode_name'}

        for key, value in data.items():
            key = key_map.get(key, key)
            if not hasattr(self, key):
                logger.error(f'Parsed attribute "{key}" not defined in {type(self).__name__}.')
            setattr(self, key, value)


class QueryResult(MediaName):
    def __init__(self, data: dict = None, media_type: MediaType = None):
        super().__init__(media_type)

        self.fuzzy_match_score = data.get('_fuzzy_score', -1)

        if self.media_type is MediaType.MOVIE:
            self.title = data['title']
            self.genre_ids = set(data.get('genre_ids') or set())
            self.genre_ids.update([gid for gid in data.get('genres', [])])
            self.year = data.get('release_date', '')[:4]
        elif self.media_type is MediaType.SERIES:
            series = data.get('_series', '')
            self.title = series.get('seriesName', '')
            self.series_id = series.get('id', '')
            self.episode = data.get('airedEpisodeNumber', '')
            self.season = data.get('airedSeason', '')
            self.episode_name = data.get('episodeName', '')
            self.first_aired = data.get('firstAired')
            self.network = series.get('network')
            self.aliases = series.get('aliases')
            self.status = series.get('status')
