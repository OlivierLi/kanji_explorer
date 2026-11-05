"""Notation semantics must agree across parser, renderer, and HTTP routes."""
import json
from urllib.parse import urlencode

import pytest

import glyph_service
import ids_parser
import server
import view_renderer


def _collect_tree_chars(node: dict) -> list[str]:
    chars: list[str] = []
    if "char" in node and node["char"] is not None:
        chars.append(node["char"])
    if "raw_char" in node and node["raw_char"] is not None:
        chars.append(node["raw_char"])
    for child in node.get("children", []):
        chars.extend(_collect_tree_chars(child))
    return chars


@pytest.mark.parametrize('token,char', [('U+86CD','蛍'), ('u86cd','蛍'), ('U 86CD','蛍'),
                                       ('0x86CD','蛍'), ('86cd','蛍'), ('u2d544','𭕄'),
                                       ('U+41','A'), ('U+86CD\uFE00','蛍'),
                                       ('0x86CD\U000E0100','蛍')])
def test_codepoint_notation_is_shared(token, char):
    assert ids_parser.resolve_codepoint_notation(token) == char
    assert server.resolve_query(token)[0] == char
    tree = ids_parser.decompose_character(token, ids_dict={}, max_depth=1, use_atomic=False)
    assert tree['char'] == char
    assert glyph_service.get_glyph_svg(token) == glyph_service.get_glyph_svg(char)


@pytest.mark.parametrize('token', ['U+110000', '0x110000', '110000', 'U+D800', 'U+ZZZZ',
                                  'U+110000\uFE00', '&', '&;', '&\uFE00', '&\uFE00;',
                                  '&\U000E0100', '&CDP-8BD9;X', '&CDP-8BD9;;'])
def test_invalid_scalars_are_not_reinterpreted_as_text(token):
    with pytest.raises(ValueError):
        ids_parser.decompose_character(token)
    assert server.resolve_query(token)[0] == ''


@pytest.mark.parametrize('path,key', [('/api/char','q'), ('/api/glyph','c'),
                                    ('/api/ids-find','components'), ('/api/words','kanji'),
                                    ('/view','char')])
@pytest.mark.parametrize('invalid_token', ['U+110000', '&', '&;', '&\uFE00', '&\uFE00;', 'U+110000\uFE00'])
def test_routes_reject_invalid_codepoint_notation(path, key, invalid_token):
    statuses = []
    body = server.application({'REQUEST_METHOD':'GET', 'PATH_INFO':path,
                               'QUERY_STRING':urlencode({key:invalid_token})},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['400 Bad Request']
    assert 'error' in json.loads(b''.join(body))


@pytest.mark.parametrize('path,key', [('/api/char','q'), ('/api/glyph','c'),
                                    ('/api/ids-find','components'), ('/api/words','kanji'),
                                    ('/view','char')])
def test_routes_accept_variation_selector_codepoint_notation(path, key):
    statuses = []
    body = server.application({'REQUEST_METHOD':'GET', 'PATH_INFO':path,
                               'QUERY_STRING':urlencode({key:'U+86CD\uFE00'})},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['200 OK']
    assert b''.join(body)


@pytest.mark.parametrize('token', ['CDP-8BD9', 'cdp-8bd9', '&cdp-8bd9;', '&CDP-8BD9',
                                  'CDP-v001-8BD9', '&CDP-8BD9\uFE00;', 'CDP-8BD9\uFE00'])
def test_entity_notation_is_shared(token):
    entity = ids_parser.resolve_entity_notation(token)
    assert server.resolve_query(token)[0] == entity
    tree = ids_parser.decompose_character(token, ids_dict={}, max_depth=1, use_atomic=False)
    assert tree['char'] == '甲'
    assert glyph_service.get_glyph_svg(token) == glyph_service.get_glyph_svg('甲')


@pytest.mark.parametrize(
    'kanji,ids_str,expected_op',
    [
        ('幾', '&U-i002+2FF1;𢆶戍', '⿱'),
        ('爽', '&U-i001+2FFB;大㸚', '⿻'),
        ('坐', '&U-i002+2FF1;从土', '⿱'),
        ('亦', '&U-i001+2FF1;亣八', '⿱'),
        ('巫', '&U-i001+2FFB;工从', '⿻'),
        ('乖', '&U-i001+2FF1;千北', '⿱'),
        ('齊', '&U-i001+2FF1;⿱亠丫⿱⿰刀𱍸&CDP-89C6;', '⿱'),
    ],
)
def test_multi_token_ids_starting_with_entity_are_not_corrupted(kanji, ids_str, expected_op):
    assert ids_parser.resolve_entity_notation(ids_str) is None
    assert ids_parser.resolve_entity_notation('CDP-8BD9;一') is None

    tree = ids_parser.decompose_character(ids_str, max_depth=8, use_atomic=True, compute_bbox=True)
    assert tree['type'] == 'op'
    assert tree['op'] == expected_op
    assert 'implicit' not in tree
    assert tree.get('char') is None
    assert ';' not in _collect_tree_chars(tree)

    statuses = []
    body = server.application(
        {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/api/char', 'QUERY_STRING': urlencode({'q': kanji})},
        lambda status, headers: statuses.append(status),
    )
    assert statuses == ['200 OK']
    payload = json.loads(b''.join(body))
    api_tree = payload['tree']
    assert api_tree['type'] == 'op'
    assert api_tree['op'] == expected_op
    assert api_tree['char'] == kanji
    assert 'implicit' not in api_tree
    assert ';' not in _collect_tree_chars(api_tree)


def test_view_renderer_handles_unparseable_canonical_char_gracefully():
    meta = server.get_fallback_character_meta('&;', '&;')
    rendered = view_renderer.render_side_by_side_html('&;', meta, {})
    assert '<!DOCTYPE html>' in rendered
    assert '&amp;;' in rendered
