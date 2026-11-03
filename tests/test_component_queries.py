"""Both component views must classify the same distinct targets."""
import json
import sqlite3
from urllib.parse import urlencode

import pytest

import ids_parser
import server


@pytest.fixture
def database(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE characters (char, codepoint, tier, stroke_count, chise_ids,
                                 ja_on, ja_kun, grade, freq, sort_priority);
        CREATE TABLE component_closure (component, target_char, is_direct,
                                        via_char, min_depth, target_priority);
    ''')
    conn.executemany('INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [
        (char, f'U+{ord(char):04X}', '基本漢字', strokes, None, None, None, None, rank, 1)
        for char, strokes, rank in [('甲', 5, 1), ('乙', 1, 2), ('丙', 5, 3)]]
    )
    conn.executemany('INSERT INTO component_closure VALUES (?, ?, ?, ?, ?, ?)', [
        ('食', '甲', 0, '中', 2, 1), ('飠', '甲', 1, '', 1, 2),
        ('食', '甲', 1, '', 1, 1),  # Equivalent direct rows must yield one card.
        ('食', '乙', 0, '日', 3, 1), ('飠', '乙', 0, '中', 2, 1),
        ('食', '丙', 1, '', 1, 1),
        ('木', '甲', 1, '', 1, 1), ('木', '乙', 0, '中', 2, 1),
    ])
    monkeypatch.setattr(ids_parser, 'EQUIV_GROUPS', {'食': ['飠']})
    monkeypatch.setattr(server, 'get_db_connection', lambda: conn)
    yield conn
    conn.close()


def search(**params):
    statuses = []
    body = server.application({'REQUEST_METHOD': 'GET', 'PATH_INFO': '/api/ids-find',
                               'QUERY_STRING': urlencode({'components': '食', **params})},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['200 OK']
    return json.loads(b''.join(body))


def test_usage_and_search_share_classification(database):
    usage = server.query_component_closure_db(database, '食')
    all_results = search(limit=500)
    assert usage['total'] == all_results['total'] == 3
    assert usage['direct_total'] == all_results['direct_total'] == 2
    assert usage['indirect_total'] == all_results['indirect_total'] == 1
    for key, mode in [('direct', 'direct'), ('indirect', 'indirect')]:
        assert usage[key] == search(mode=mode)['results']
    assert [r['char'] for r in usage['direct']] == ['甲', '丙']
    assert [r['char'] for r in usage['indirect']] == ['乙']
    indirect = usage['indirect'][0]
    assert (indirect['via_char'], indirect['min_depth']) == ('中', 2)
    assert all(r['via_char'] == '' for r in usage['direct'])


@pytest.mark.parametrize('params,chars,total', [
    ({'components': '食 木'}, ['甲', '乙'], 2),
    ({'mode': 'transitive'}, ['乙'], 1),
    ({'min_strokes': 2}, ['甲', '丙'], 2),
    ({'max_strokes': 1}, ['乙'], 1),
    ({'limit': 1}, ['甲'], 3),
])
def test_shared_filters_and_limits(database, params, chars, total):
    result = search(**params)
    assert [r['char'] for r in result['results']] == chars
    assert result['total'] == total


def test_path_choice_does_not_depend_on_insertion_order(database):
    before = search()
    rows = database.execute('SELECT * FROM component_closure').fetchall()
    database.execute('DELETE FROM component_closure')
    database.executemany('INSERT INTO component_closure VALUES (?, ?, ?, ?, ?, ?)', reversed(rows))
    assert search() == before


@pytest.mark.parametrize('query,chars', [('たべる ショク', ['甲']),
                                       ('タベル しょく', ['甲']),
                                       ('たべる まったくでたらめ', [])])
def test_reading_search_honors_every_chip(database, query, chars):
    database.execute("UPDATE characters SET ja_kun='た.べる', ja_on='ショク' WHERE char='甲'")
    database.execute("UPDATE characters SET ja_kun='たべる', ja_on='エン' WHERE char='乙'")
    result = search(components=query)
    assert [r['char'] for r in result['results']] == chars
    assert result['total'] == len(chars)


def test_unavailable_reading_table_returns_service_unavailable(database):
    database.execute('DROP TABLE characters')
    statuses = []
    body = server.application({'REQUEST_METHOD':'GET', 'PATH_INFO':'/api/ids-find',
                               'QUERY_STRING':urlencode({'components':'たべる'})},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['503 Service Unavailable']
    assert 'error' in json.loads(b''.join(body))


@pytest.mark.parametrize('mode,total', [('all', 3), ('direct', 2), ('indirect', 1)])
def test_zero_limit_keeps_full_counts(database, mode, total):
    result = server.query_component_matches_db(database, ['食'], mode=mode, limit=0)
    assert result == {'total': total, 'direct_total': 2, 'indirect_total': 1, 'results': []}


def test_empty_category_and_empty_match_keep_counts(database):
    result = server.query_component_matches_db(database, ['木'], mode='indirect', min_strokes=5)
    assert result == {'total': 0, 'direct_total': 1, 'indirect_total': 0, 'results': []}
    usage = server.query_component_closure_db(database, '無')
    assert usage == {'total': 0, 'direct_total': 0, 'indirect_total': 0, 'transitive_total': 0,
                     'direct': [], 'indirect': [], 'transitive': []}


def test_usage_has_independent_category_limits_and_complete_counts(database):
    database.execute('DELETE FROM component_closure')
    database.execute('DELETE FROM characters')
    chars = [chr(0x4E00 + i) for i in range(324)]
    database.executemany('INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [
        (char, f'U+{ord(char):04X}', '基本漢字', 5, None, None, None, None, i, 1)
        for i, char in enumerate(chars)
    ])
    database.executemany('INSERT INTO component_closure VALUES (?, ?, ?, ?, ?, ?)', [
        ('食', char, i % 2, '' if i % 2 else '中', 1 if i % 2 else 2, 1)
        for i, char in enumerate(chars)
    ])
    usage = server.query_component_closure_db(database, '食')
    assert usage['total'] == 324
    assert usage['direct_total'] == usage['indirect_total'] == 162
    assert [item['char'] for item in usage['direct']] == chars[1:300:2]
    assert [item['char'] for item in usage['indirect']] == chars[:300:2]
    assert usage['transitive'] == usage['indirect']


@pytest.mark.parametrize('usage', [False, True])
def test_component_lookup_executes_one_ranked_statement(database, usage):
    statements = []
    database.set_trace_callback(statements.append)
    try:
        if usage:
            server.query_component_closure_db(database, '食')
        else:
            server.query_component_matches_db(database, ['食'])
    finally:
        database.set_trace_callback(None)
    queries = [sql for sql in statements if 'WITH ranked' in sql]
    assert len(queries) == 1
