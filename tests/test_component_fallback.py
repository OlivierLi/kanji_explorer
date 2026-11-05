"""Fallback lookup uses exact tokens, complete counts, and real graph paths."""
import json
from urllib.parse import urlencode

import pytest

import ids_parser
import server


@pytest.fixture
def ids_source(monkeypatch):
    source = {'甲': '⿰木乙', '乙': '⿱木丙', '丙': '一',
              '丁': '⿰&CDP-1234;二', '戊': '⿰甲二', '己': '⿰木木'}
    monkeypatch.setattr(ids_parser, 'get_ids_dict', lambda: source)
    monkeypatch.setattr(ids_parser, 'ATOMIC_SUBDECOMPOSITIONS', {})
    monkeypatch.setattr(ids_parser, 'EQUIV_GROUPS', {})
    monkeypatch.setattr(server, 'get_db_connection', lambda: None)
    return source


def test_counts_are_not_truncated_and_categories_are_exclusive(ids_source):
    result = server.query_component_matches_fallback(['木'], limit=1)
    assert len(result['results']) == 1
    assert result['total'] == 4
    assert result['direct_total'] == 3
    assert result['indirect_total'] == 1
    usage = server.query_component_closure_fallback('木')
    assert usage['total'] == result['total']
    assert {r['char'] for r in usage['direct']} == {'甲', '乙', '己'}
    assert usage['indirect'][0]['char'] == '戊'
    assert usage['indirect'][0]['via_char'] == '甲'
    assert usage['indirect'][0]['min_depth'] == 2


def test_exact_tokens_and_and_matching(ids_source):
    assert server.query_component_matches_fallback(['CDP'])['total'] == 0
    assert server.query_component_matches_fallback(['&CDP-1234;'])['total'] == 1
    assert [r['char'] for r in server.query_component_matches_fallback(['木', '二'])['results']] == ['戊']


def test_replacing_source_dictionary_replaces_cached_index(ids_source, monkeypatch):
    assert server.query_component_matches_fallback(['木'])['total'] == 4
    monkeypatch.setattr(ids_parser, 'get_ids_dict', lambda: {'森': '⿰木木'})
    assert [r['char'] for r in server.query_component_matches_fallback(['木'])['results']] == ['森']


@pytest.mark.parametrize('params', [{'components': 'たべる'},
                                  {'components': '木', 'min_strokes': 1},
                                  {'components': '木', 'tier': 'joyo'}])
def test_missing_metadata_is_unavailable_not_zero_or_unfiltered_results(ids_source, params):
    statuses = []
    body = server.application({'REQUEST_METHOD': 'GET', 'PATH_INFO': '/api/ids-find',
                               'QUERY_STRING': urlencode(params)},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['503 Service Unavailable']
    assert 'error' in json.loads(b''.join(body))


def test_fallback_excludes_synthetic_alias_keys_and_includes_atomic_targets(monkeypatch):
    source = {
        '蛍': '⿱𰃮虫',
        '&U+86CD;': '⿱𰃮虫',
        '&J90-3756;': '⿱𰃮虫',
        '&UNMAPPED-ENT;': '⿰虫中',
    }
    monkeypatch.setattr(ids_parser, 'get_ids_dict', lambda: source)
    monkeypatch.setattr(ids_parser, 'ATOMIC_SUBDECOMPOSITIONS', {'𭕄': '⿲丶丶丿'})
    monkeypatch.setattr(ids_parser, 'EQUIV_GROUPS', {})
    monkeypatch.setattr(server, 'get_db_connection', lambda: None)

    bug_res = server.query_component_matches_fallback(['虫'])
    assert [r['char'] for r in bug_res['results']] == ['蛍', '&UNMAPPED-ENT;']

    stroke_res = server.query_component_matches_fallback(['丿'])
    assert [r['char'] for r in stroke_res['results']] == ['𭕄']
    assert stroke_res['results'][0]['chise_ids'] == '⿲丶丶丿'


def test_fallback_multi_component_search_is_order_independent(ids_source):
    for mode in ('all', 'direct', 'indirect'):
        ab = server.query_component_matches_fallback(['木', '二'], mode=mode)
        ba = server.query_component_matches_fallback(['二', '木'], mode=mode)
        assert ab == ba
    all_ab = server.query_component_matches_fallback(['木', '二'], mode='all')
    assert all_ab['total'] == 1
    assert all_ab['direct_total'] == 0
    assert all_ab['indirect_total'] == 1
    assert all_ab['results'][0]['char'] == '戊'
    assert all_ab['results'][0]['is_direct'] == 0
    assert all_ab['results'][0]['min_depth'] == 2
    assert all_ab['results'][0]['via_char'] == '甲'


def test_real_corpus_fallback_matches_db_for_tsuduri_and_hotaru():
    res_ab = server.query_component_matches_fallback(['𭕄', '虫'])
    res_ba = server.query_component_matches_fallback(['虫', '𭕄'])
    assert res_ab == res_ba
    assert res_ab['total'] == 6
    chars = [r['char'] for r in res_ab['results']]
    assert '蛍' in chars
    assert '&U+86CD;' not in chars
    assert '&J90-3756;' not in chars
    hotaru = next(r for r in res_ab['results'] if r['char'] == '蛍')
    assert hotaru['is_direct'] == 1
    assert hotaru['min_depth'] == 1
    assert hotaru['via_char'] == ''
