import logging
from pathlib import Path
from string import printable, digits

import PTN

from turbopotato.media_defs import MediaNameParse
from turbopotato.media_defs import MediaType

logger = logging.getLogger(__name__)


def parse(filepath: Path = None):
    ptn_results = PTN.parse(filepath.name)

    # determine which parent directory should be considered the real parent
    parent_path = filepath.parent
    if parent_path:
        # season is important because parsing out a season number means we're dealing with a series
        if parent_path.name.lower().startswith('season'):
            season_no = parent_path[6:].strip().rstrip(''.join(set(printable) - set(digits)))
            try:
                season_in_dir = int(season_no)
            except ValueError:
                pass
            else:
                parent_path = filepath.parent.parent
                if not ptn_results.get('season'):
                    ptn_results['season'] = season_in_dir
        elif parent_path.name.lower() in ('subs', 'subtitles', 'subtitle'):
            parent_path = filepath.parent.parent

    media_type = MediaType.SERIES if ptn_results.get('season') else MediaType.MOVIE

    # these parser results may be considered when querying the databases
    # if the filename alone didn't provide enough information
    parent_ptn_results = {}
    if parent_path:
        parent_ptn_results = PTN.parse(parent_path.name)

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
