"""Glyph names must never turn cache lookup into an arbitrary file lookup."""
from pathlib import Path

import pytest

import glyph_service


@pytest.mark.parametrize('kind', ['parent', 'absolute', 'symlink'])
def test_glyph_cache_stays_inside_its_directory(tmp_path, monkeypatch, kind):
    root = tmp_path / 'cache'
    root.mkdir()
    outside = tmp_path / 'secret.svg'
    outside.write_text('<svg><text>outside-cache-marker</text></svg>')
    monkeypatch.setattr(glyph_service, 'GLYPHWIKI_CACHE_DIR', root)
    if kind == 'parent':
        slug = '../secret'
    elif kind == 'absolute':
        slug = str(outside.with_suffix(''))
    else:
        (root / 'escape.svg').symlink_to(outside)
        slug = 'escape'
    assert 'outside-cache-marker' not in glyph_service.get_glyph_svg('&' + slug + ';')


def test_normal_glyph_cache_lookup_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(glyph_service, 'GLYPHWIKI_CACHE_DIR', tmp_path)
    content = '<svg><path d="M0 0H1V1Z"/></svg>'
    (tmp_path / 'unknown-glyph.svg').write_text(content)
    assert glyph_service.get_glyph_svg('&unknown-glyph;') == content
