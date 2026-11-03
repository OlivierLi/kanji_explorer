"""Totals and rows must describe one SQLite snapshot, including during repairs."""
import sqlite3

import pytest

import server


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'database.db'
    writer = sqlite3.connect(path)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.executescript('''
        CREATE TABLE characters (char, codepoint, tier, stroke_count, chise_ids,
                                 ja_on, ja_kun, grade, freq, sort_priority);
        INSERT INTO characters VALUES ('甲','U+7532','基本漢字',5,NULL,NULL,'たべる',NULL,1,1),
                                      ('乙','U+4E59','基本漢字',1,NULL,NULL,'たべる',NULL,2,1);
        CREATE TABLE component_closure (component, target_char, is_direct,
                                        via_char, min_depth, target_priority);
        INSERT INTO component_closure VALUES ('木','甲',1,'',1,1),('木','乙',1,'',1,1);
        CREATE TABLE words (word_id, lemma, reading, pos, definition, frequency_rank,
                            frequency_tier, source);
        INSERT INTO words VALUES (1,'甲木','','名詞','[]',1,'最頻出','資料'),
                                 (2,'乙木','','名詞','[]',2,'最頻出','資料');
        CREATE TABLE word_kanji (word_id, kanji, position_type);
        INSERT INTO word_kanji VALUES (1,'木','tail'),(2,'木','tail');
    ''')

    class Cursor(sqlite3.Cursor):
        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            callback = self.connection.after_count
            if callback is not None and 'COUNT(' in sql.upper():
                self.connection.after_count = None
                callback()
            return result

    class Connection(sqlite3.Connection):
        after_count = None

        def cursor(self, factory=Cursor):
            return super().cursor(factory)

        def execute(self, sql, parameters=()):
            return self.cursor().execute(sql, parameters)

    reader = sqlite3.connect(path, factory=Connection)
    reader.row_factory = sqlite3.Row
    yield reader, writer
    reader.close()
    writer.close()


@pytest.mark.parametrize('kind', ['components', 'readings', 'words'])
def test_count_and_rows_use_one_snapshot(database, kind):
    reader, writer = database

    def repair_during_query():
        writer.execute("DELETE FROM characters WHERE char='乙'")
        writer.execute('DELETE FROM words WHERE word_id=2')
        writer.commit()

    reader.after_count = repair_during_query
    if kind == 'components':
        result = server.query_component_matches_db(reader, ['木'])
    elif kind == 'readings':
        result = server.query_reading_matches_db(reader, ['たべる'])
    else:
        result = server.query_words_db(reader, '木', scope='direct')
    assert writer.execute('SELECT COUNT(*) FROM characters').fetchone()[0] == 1
    assert result['total'] == len(result['results']) == 2
    assert not reader.in_transaction


def test_query_snapshot_does_not_commit_callers_transaction(database):
    reader, _ = database
    reader.execute('BEGIN')
    server.query_component_matches_db(reader, ['木'])
    assert reader.in_transaction
    reader.rollback()


def test_failed_query_releases_its_snapshot(database):
    reader, _ = database

    def fail():
        raise ValueError('failed while reading')

    reader.after_count = fail
    with pytest.raises(ValueError):
        server.query_component_matches_db(reader, ['木'])
    assert not reader.in_transaction
    assert server.query_component_matches_db(reader, ['木'])['total'] == 2



def test_usage_categories_share_the_outer_snapshot(database):
    reader, writer = database

    def reclassify_during_query():
        writer.execute("UPDATE component_closure SET is_direct=0, min_depth=2, via_char='甲' WHERE target_char='乙'")
        writer.commit()

    reader.after_count = reclassify_during_query
    usage = server.query_component_closure_db(reader, '木')
    assert usage['total'] == usage['direct_total'] == 2
    assert usage['indirect_total'] == 0
    assert {item['char'] for item in usage['direct']} == {'甲', '乙'}
    assert usage['indirect'] == []
