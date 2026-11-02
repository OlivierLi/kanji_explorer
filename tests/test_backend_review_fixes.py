"""Regressions for review findings 8–12, including deployed database metadata."""
import gzip
import json
import shutil
import sqlite3
from urllib.parse import urlencode

import pytest

import build_db
import server
import view_renderer
from scripts.build_words_db import map_pos_title


def get(path, **params):
    statuses = []
    body = server.application({'REQUEST_METHOD': 'GET', 'PATH_INFO': path,
                               'QUERY_STRING': urlencode(params)},
                              lambda status, headers: statuses.append(status))
    assert statuses == ['200 OK']
    text = b''.join(body).decode()
    return json.loads(text) if path.startswith('/api/') else text


@pytest.mark.parametrize('reading,char', [('たべる', '食'), ('タベル', '食'),
                                         ('よむ', '読'), ('ヨム', '読'), ('しこめ', '嫫')])
def test_ordinary_reading_lookup(reading, char):
    result = get('/api/ids-find', components=reading, limit=500)
    assert char in {item['char'] for item in result['results']}


def test_reading_notation_preserves_separate_reading_boundaries(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE characters (char, codepoint, tier, stroke_count,
        chise_ids, ja_on, ja_kun, grade, freq, sort_priority)""")
    conn.execute("INSERT INTO characters VALUES ('仮','U+4EEE','基本漢字',6,NULL,NULL,'あ.い, う.え',NULL,NULL,1)")
    monkeypatch.setattr(server, 'get_db_connection', lambda: conn)
    assert get('/api/ids-find', components='いう')['results'] == []
    assert [item['char'] for item in get('/api/ids-find', components='あい')['results']] == ['仮']
    conn.close()


def test_unihan_source_readings_preserve_kana_and_legacy_additions():
    assert build_db.unihan_kana_readings({'kJapanese': 'モ ボ しこめ',
        'kJapaneseOn': 'BO MO', 'kJapaneseKun': 'SHIKOME'}) == ('モ, ボ', 'しこめ')
    assert build_db.unihan_kana_readings({'kJapanese': 'モ', 'kJapaneseOn': 'MO BOU',
        'kJapaneseKun': 'MOPPARA'}) == ('モ, ボウ', 'もっぱら')
    assert build_db.romanized_reading_to_kana('SHYUU') == 'しゅう'
    assert build_db.romanized_reading_to_kana('FIITO') == 'ふぃいと'


def test_persisted_unihan_metadata():
    meta = get('/api/char', q='嫫')['meta']
    assert set(meta['on_readings']) == {'モ', 'ボ'}
    assert meta['kun_readings'] == ['しこめ']


@pytest.mark.parametrize('label', ['形容動詞', '感動詞', '動詞'])
def test_specific_pos_mapping(label):
    assert map_pos_title(label) == label


def test_adjective_and_interjection_api():
    words = get('/api/words', kanji='大', keyword='大切', scope='direct')['results']
    assert any(word['lemma'] == '大切' and word['pos'] == '形容動詞' for word in words)
    conn = server.get_db_connection()
    lemma = conn.execute("SELECT lemma FROM words WHERE pos='感動詞' ORDER BY length(lemma), lemma LIMIT 1").fetchone()[0]
    words = get('/api/words', kanji=lemma[0], keyword=lemma, scope='direct')['results']
    assert any(word['lemma'] == lemma and word['pos'] == '感動詞' for word in words)


@pytest.mark.parametrize('grade,expected', [(1, '小学1年'), (6, '小学6年'),
    (8, '常用漢字'), (9, '人名用漢字'), (10, '人名用漢字'), (None, '漢字')])
def test_audit_grade_html(grade, expected):
    html = view_renderer.render_side_by_side_html('一', {'grade': grade}, {'mode': ['mincho']})
    assert expected in html
    for impossible in ('小学8年', '小学9年', '小学10年'):
        assert impossible not in html


def test_indirect_classification_is_consistent_after_equivalence():
    all_results = get('/api/ids-find', components='食', limit=500)
    indirect = get('/api/ids-find', components='食', mode='indirect', limit=500)
    direct = get('/api/ids-find', components='食', mode='direct', limit=500)
    assert indirect['total'] == len(indirect['results'])
    assert direct['total'] == all_results['direct_total']
    assert all_results['total'] == direct['total'] + indirect['total']
    indirect_chars = {item['char'] for item in indirect['results']}
    direct_chars = {item['char'] for item in direct['results']}
    assert not indirect_chars & direct_chars
    assert all(item['is_direct'] == (item['char'] not in indirect_chars)
               for item in all_results['results'])
    assert all(item['is_direct'] == 0 for item in indirect['results'])


def test_packaged_database_contains_repairs(tmp_path):
    path = tmp_path / 'packaged.db'
    with gzip.open(build_db.DB_PATH.with_suffix('.db.gz'), 'rb') as src, path.open('wb') as dst:
        shutil.copyfileobj(src, dst)
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        on, kun = conn.execute("SELECT ja_on, ja_kun FROM characters WHERE char='嫫'").fetchone()
        assert set(on.split(', ')) == {'モ', 'ボ'}
        assert kun == 'しこめ'
        assert conn.execute("SELECT pos FROM words WHERE lemma='大切'").fetchone()[0] == '形容動詞'
        assert conn.execute("SELECT count(*) FROM words WHERE pos='感動詞'").fetchone()[0] > 0
        assert conn.execute('SELECT count(*) FROM component_closure').fetchone()[0] > 0
