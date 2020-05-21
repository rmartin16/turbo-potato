from pathlib import Path

import pytest

from turbopotato.parser import parse
from turbopotato.media_defs import MediaType


def test_parser():
    filename = Path('What.We.Do.in.the.Shadows.S02E05.720p.HDTV.x264-CROOKS.mkv')
    parsed = parse(filename)
    assert parsed.codec == 'x264'
    assert parsed.container == 'mkv'
    assert parsed.episode == 5
    assert parsed.group == 'CROOKS.mkv'
    assert parsed.media_type is MediaType.SERIES
    assert parsed.quality == 'HDTV'
    assert parsed.resolution == '720p'
    assert parsed.season == 2
    assert parsed.title == 'What We Do in the Shadows'
