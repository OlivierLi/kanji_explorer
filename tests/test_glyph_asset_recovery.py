"""Restoring unavailable assets must work without restarting the process."""
import gzip

import pytest

import glyph_service


@pytest.mark.parametrize('payload', [None, b'invalid gzip', gzip.compress(b'partial')[:-4], gzip.compress(b'')])
def test_kanjivg_recovers_after_missing_or_damaged_archive(tmp_path, payload):
    path = tmp_path / 'kanjivg.xml.gz'
    if payload is not None:
        path.write_bytes(payload)
    service = glyph_service.KanjiVGService(kanjivg_path=path)
    assert service.get_kanji_xml('日') is None
    xml = '<kanji id="kvg:kanji_065e5"><g /></kanji>'
    with gzip.open(path, 'wt', encoding='utf-8') as target:
        target.write(xml)
    assert service.get_kanji_xml('日') == xml


def test_missing_fonts_do_not_cache_absent_paths(tmp_path, monkeypatch):
    class Glyph:
        def draw(self, pen):
            pen.moveTo((0, 0))
            pen.lineTo((1, 1))
            pen.closePath()

    class Font:
        def __init__(self, *args, **kwargs):
            pass

        def getBestCmap(self):
            return {ord('日'): 'sun'}

        def getGlyphSet(self):
            return {'sun': Glyph()}

    monkeypatch.setattr(glyph_service, 'TTFont', Font)
    manager = glyph_service._JigmoFontManager(tmp_path)
    assert manager.get_path('日') is None
    (tmp_path / 'Jigmo.ttf').touch()
    assert manager.get_path('日')
