"""Unavailable data must not be cached as permanent metadata."""
import sqlite3

import pytest

import glyph_service
import server


@pytest.fixture
def metadata_database(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE characters (char, codepoint, tier, stroke_count, ja_on,
                                 ja_kun, chise_ids, grade, sort_priority);
        INSERT INTO characters VALUES ('仮','U+4EEE','基本漢字',6,'カ','かり',NULL,5,1);
    ''')
    available = [None]
    monkeypatch.setattr(server, 'get_db_connection', lambda: available[0])
    yield conn, available
    conn.close()


def test_metadata_and_navigation_recover_after_unavailable_database(metadata_database):
    conn, available = metadata_database
    assert server.get_meta_summary('仮')['stroke_count'] is None
    assert server.get_joyo_characters() == []
    available[0] = conn
    assert server.get_meta_summary('仮')['stroke_count'] == 6
    assert server.get_joyo_characters() == ['仮']
    conn.execute("UPDATE characters SET stroke_count=7, ja_on='ケ' WHERE char='仮'")
    assert server.get_meta_summary('仮')['stroke_count'] == 7
    assert server.get_meta_summary('仮')['ja_on'] == ['ケ']


def test_tree_metadata_is_deduplicated_per_request_but_not_shared_mutably(metadata_database, monkeypatch):
    conn, available = metadata_database
    available[0] = conn
    read_summary = server.get_meta_summary
    calls = []

    def read(char):
        calls.append(char)
        return read_summary(char)

    monkeypatch.setattr(server, 'get_meta_summary', read)
    tree = {'children': [{'char': '仮'}, {'char': '仮'}]}
    server.enrich_tree_with_meta(tree)
    assert calls == ['仮']
    first, second = tree['children']
    first['meta_summary']['ja_on'].append('不正')
    assert second['meta_summary']['ja_on'] == ['カ']
    server.enrich_tree_with_meta(tree)
    assert calls == ['仮', '仮']
    assert first['meta_summary']['ja_on'] == ['カ']


def test_stroke_count_recovers_after_missing_or_incomplete_database(tmp_path, monkeypatch):
    monkeypatch.setattr(glyph_service, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(glyph_service, '_STROKE_COUNT_CACHE', None)
    assert glyph_service._get_stroke_count('仮') is None
    path = tmp_path / 'kanji_explorer.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE unrelated (value)')
    assert glyph_service._get_stroke_count('仮') is None
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE characters (char, stroke_count)')
        conn.execute("INSERT INTO characters VALUES ('仮',6)")
    assert glyph_service._get_stroke_count('仮') == 6
