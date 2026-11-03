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
