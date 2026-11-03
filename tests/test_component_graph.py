"""Reachability must prefer direct edges and globally shortest paths."""
from component_graph import ComponentGraph, ComponentPath


def test_alternative_direct_edge_precedes_indirect_primary_path():
    graph = ComponentGraph({'甲': ['乙'], '乙': ['丙'], '丙': ['丁']}, {'甲': ['丙']})
    assert graph.closure('甲') == {
        '乙': ComponentPath(1, 1, ''), '丙': ComponentPath(1, 1, ''),
        '丁': ComponentPath(2, 0, '丙'),
    }


def test_short_alternative_route_is_not_truncated_by_long_primary_route():
    graph = ComponentGraph({'甲': ['乙'], '乙': ['丙'], '丙': ['丁'], '丁': ['戊']},
                           {'甲': ['丁']})
    assert graph.closure('甲', max_depth=2)['戊'] == ComponentPath(2, 0, '丁')


def test_cycles_self_edges_and_depth_boundaries():
    graph = ComponentGraph({'甲': ['甲', '乙'], '乙': ['甲', '丙'], '丙': ['乙', '丁']})
    assert graph.closure('甲', 0) == {}
    assert graph.closure('甲', 1) == {'乙': ComponentPath(1, 1, '')}
    assert graph.closure('甲', 2) == {'乙': ComponentPath(1, 1, ''), '丙': ComponentPath(2, 0, '乙')}
    assert '甲' not in graph.closure('甲')


def test_only_first_level_uses_alternatives_and_input_order_is_irrelevant():
    primary = {'甲': ['丙', '乙'], '丙': ['丁'], '乙': ['丁']}
    graph = ComponentGraph(primary, {'乙': ['戊']})
    primary['甲'].clear()
    assert graph.closure('甲')['丁'] == ComponentPath(2, 0, '丙')
    assert '戊' not in graph.closure('甲')
    assert graph.closure('不存在') == {}


def test_repair_updates_only_derived_paths_and_is_idempotent(tmp_path):
    import gzip
    import shutil
    import sqlite3
    from scripts.repair_component_closure import repair, repair_closure

    path = tmp_path / 'test.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            CREATE TABLE characters (char, sort_priority, stroke_count, freq);
            CREATE TABLE component_edges (parent_char, child_char, source);
            CREATE TABLE component_closure (component, target_char, min_depth,
                is_direct, via_char, target_priority, target_strokes, target_freq,
                PRIMARY KEY(component, target_char));
            CREATE INDEX closure_target ON component_closure(target_char);
            CREATE TABLE words (word_id, lemma);
            INSERT INTO words VALUES (42, '保持');
            INSERT INTO characters VALUES ('甲',1,5,1),('乙',1,1,2),('丙',1,5,3),('丁',1,2,4);
            INSERT INTO component_edges VALUES ('甲','乙','chise'),('乙','丙','chise'),
                ('丙','丁','chise'),('甲','丙','cjkvi');
            INSERT INTO component_closure VALUES ('丙','甲',2,0,'乙',1,5,1);
        ''')
    stats = repair(path)
    assert stats['updated'] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT min_depth,is_direct,via_char FROM component_closure WHERE target_char='甲' AND component='丙'").fetchone() == (1, 1, '')
        assert conn.execute("SELECT min_depth,is_direct,via_char FROM component_closure WHERE target_char='甲' AND component='丁'").fetchone() == (2, 0, '丙')
        assert conn.execute('SELECT * FROM words').fetchall() == [(42, '保持')]
        assert repair_closure(conn) == {'updated': 0, 'inserted': 0, 'deleted': 0}
    extracted = tmp_path / 'packaged.db'
    with gzip.open(path.with_suffix('.db.gz'), 'rb') as source, extracted.open('wb') as target:
        shutil.copyfileobj(source, target)
    with sqlite3.connect(extracted) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert conn.execute('SELECT * FROM words').fetchall() == [(42, '保持')]
        assert conn.execute("SELECT min_depth,is_direct FROM component_closure WHERE target_char='甲' AND component='丙'").fetchone() == (1, 1)



def test_packaged_closure_promotes_alternative_direct_components():
    import gzip
    import shutil
    import sqlite3
    import tempfile
    from pathlib import Path
    import build_db

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'database.db'
        with gzip.open(build_db.DB_PATH.with_suffix('.db.gz'), 'rb') as source, path.open('wb') as target:
            shutil.copyfileobj(source, target)
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT min_depth,is_direct,via_char FROM component_closure WHERE target_char='蛍' AND component='𭕄'").fetchone() == (1, 1, '')
            assert conn.execute("SELECT count(*) FROM component_edges e JOIN component_closure c ON c.target_char=e.parent_char AND c.component=e.child_char WHERE c.is_direct=0").fetchone()[0] == 0
