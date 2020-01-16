import logging
from pathlib import Path
from string import printable, digits

import PTN

from turbopotato.helpers import MediaNameParse
from turbopotato.helpers import MediaType

logger = logging.getLogger(__name__)


def parse(filepath: Path = None):
    ptn_results = PTN.parse(filepath.name)

    # if a season wasn't parsed from the filename, see if the directory name contains a season number
    found_season_in_dir_name = False
    dir = filepath.parent.name
    if dir and dir.lower().startswith('season'):
        season_no = dir[6:].strip().rstrip(''.join(set(printable) - set(digits)))
        try:
            season_in_dir = int(season_no)
        except ValueError:
            pass
        else:
            found_season_in_dir_name = True
            if not ptn_results.get('season'):
                ptn_results['season'] = season_in_dir

    media_type = MediaType.SERIES if ptn_results.get('season') else MediaType.MOVIE

    # these parser results may be considered when querying the databases
    # if the filename alone didn't provide enough information
    if found_season_in_dir_name:
        # if the first directory had a season name, got up another level to maybe find a series name
        parent_ptn_results = PTN.parse(filepath.parent.parent.name)
    else:
        # if the directory didn't contain a season number, then it probably contains a movie or show title
        parent_ptn_results = PTN.parse(filepath.parent.name)

    parts = MediaNameParse(media_type=media_type,
                           parent_parts=MediaNameParse(media_type=media_type, **parent_ptn_results),
                           **ptn_results)
    parse_tweak(parts=parts)
    return parts


def parse_tweak(parts: MediaNameParse = None):
    if parts is None:
        return

    if 'the daily show' in parts.title:
        parts.series_id = 71256
