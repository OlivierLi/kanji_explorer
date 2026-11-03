"""Structural stroke ownership and isolation of rendering geometry."""
import copy
import json
from urllib.parse import urlencode

import pytest

import glyph_service
import ids_parser
import server


# The two inner strokes of 目, as numbered in the bundled KanjiVG XML.
@pytest.mark.parametrize('char,path,first', [
    ('睡', '0.0.1', 3), ('眺', '0.0.1', 3), ('眼', '0.0.1', 3),
    ('睦', '0.0.1', 3), ('瞭', '0.0.1', 3), ('眠', '0.0.1', 3),
    ('賂', '0.0.0.1', 3), ('購', '0.0.0.1', 3), ('敗', '0.0.0.1', 3),
    ('貯', '0.0.0.1', 3), ('賄', '0.0.0.1', 3), ('贈', '0.0.0.1', 3),
    ('則', '0.0.0.1', 3), ('賑', '0.0.0.1', 3), ('賊', '0.0.0.1', 3),
    ('賠', '0.0.0.1', 3), ('貼', '0.0.0.1', 3), ('賭', '0.0.0.1', 3),
    ('債', '0.1.1.0.1', 9), ('覚', '0.1.0.1', 8),
])
def test_nested_counter_bars_own_only_their_source_strokes(char, path, first):
    strokes = glyph_service.extract_kanjivg_stroke_layers(char)['layer_strokes']
    expected = [f'kvg:{ord(char):05x}-s{n}' for n in (first, first + 1)]
    assert strokes[path] == expected
    assert strokes[path + '.0'] == expected[:1]
    assert strokes[path + '.1'] == expected[1:]


@pytest.mark.parametrize('char', ['睡', '麟', '弱', '織'])
def test_kanjivg_is_independent_of_print_rendering_order(char):
    tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
    original = copy.deepcopy(tree)
    before = glyph_service.extract_kanjivg_stroke_layers(char, tree)
    assert tree == original

    glyph_service.build_interactive_ids_svg(tree)
    rendered = copy.deepcopy(tree)

    after = glyph_service.extract_kanjivg_stroke_layers(char, tree)
    assert after == before
    assert tree == rendered


def test_character_api_preserves_both_counter_bars():
    statuses = []
    body = server.application({'REQUEST_METHOD': 'GET', 'PATH_INFO': '/api/char',
                               'QUERY_STRING': urlencode({'q': '睡'})},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['200 OK']
    data = json.loads(b''.join(body))
    strokes = data['visual']['layer_strokes']
    assert strokes['0.0.1.0'] == ['kvg:07761-s3']
    assert strokes['0.0.1.1'] == ['kvg:07761-s4']


@pytest.mark.parametrize('char,last', [('日', 4), ('目', 5), ('回', 6),
                                      ('困', 7), ('国', 8)])
def test_closed_frames_follow_source_stroke_order(char, last):
    strokes = glyph_service.extract_kanjivg_stroke_layers(char)['layer_strokes']
    prefix = f'kvg:{ord(char):05x}-s'
    assert strokes['0.0'] == [prefix + str(n) for n in (1, 2, last)]
    assert strokes['0.1'] == [prefix + str(n) for n in range(3, last)]
    assert set(strokes['0.0']).isdisjoint(strokes['0.1'])
    assert set(strokes['0.0'] + strokes['0.1']) == set(strokes['0'])


@pytest.mark.parametrize('char', list('突斯怨舎茨溢眞究灸雰葡欺恩瀧忽想雪霊沖仲'))
def test_print_rendering_is_repeatable_and_does_not_mutate_structure(char):
    tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
    original = copy.deepcopy(tree)
    first = glyph_service.build_interactive_ids_svg(tree)
    assert tree == original
    assert glyph_service.build_interactive_ids_svg(tree) == first
    # Returned geometry must not alias the parsed tree or later render results.
    first['component_layers'][0]['bbox'][0] = -100
    assert tree == original
    assert glyph_service.build_interactive_ids_svg(tree) != first
