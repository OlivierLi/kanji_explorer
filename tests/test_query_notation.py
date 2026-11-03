"""Notation semantics must agree across parser, renderer, and HTTP routes."""
import json
from urllib.parse import urlencode

import pytest

import glyph_service
import ids_parser
import server


@pytest.mark.parametrize('token,char', [('U+86CD','蛍'), ('u86cd','蛍'), ('U 86CD','蛍'),
                                       ('0x86CD','蛍'), ('86cd','蛍'), ('u2d544','𭕄'),
                                       ('U+41','A')])
def test_codepoint_notation_is_shared(token, char):
    assert ids_parser.resolve_codepoint_notation(token) == char
    assert server.resolve_query(token)[0] == char
    tree = ids_parser.decompose_character(token, ids_dict={}, max_depth=1, use_atomic=False)
    assert tree['char'] == char
    assert glyph_service.get_glyph_svg(token) == glyph_service.get_glyph_svg(char)


@pytest.mark.parametrize('token', ['U+110000', '0x110000', '110000', 'U+D800', 'U+ZZZZ'])
def test_invalid_scalars_are_not_reinterpreted_as_text(token):
    with pytest.raises(ValueError):
        ids_parser.decompose_character(token)
    assert server.resolve_query(token)[0] == ''


@pytest.mark.parametrize('path,key', [('/api/char','q'), ('/api/glyph','c'),
                                    ('/api/ids-find','components'), ('/api/words','kanji'),
                                    ('/view','char')])
def test_routes_reject_invalid_codepoint_notation(path, key):
    statuses = []
    body = server.application({'REQUEST_METHOD':'GET', 'PATH_INFO':path,
                               'QUERY_STRING':urlencode({key:'U+110000'})},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['400 Bad Request']
    assert 'error' in json.loads(b''.join(body))


@pytest.mark.parametrize('token', ['CDP-8BD9', 'cdp-8bd9', '&cdp-8bd9;', '&CDP-8BD9',
                                  'CDP-v001-8BD9'])
def test_entity_notation_is_shared(token):
    entity = ids_parser.resolve_entity_notation(token)
    assert server.resolve_query(token)[0] == entity
    tree = ids_parser.decompose_character(token, ids_dict={}, max_depth=1, use_atomic=False)
    assert tree['char'] == '甲'
    assert glyph_service.get_glyph_svg(token) == glyph_service.get_glyph_svg('甲')
