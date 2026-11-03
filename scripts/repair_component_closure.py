"""Repair derived component paths from stored edges without rebuilding metadata.

Run from the repository root. Back up the database/package under /tmp, update
only component_closure in one transaction, and package a consistent snapshot.
"""
from collections import defaultdict
import gzip
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from component_graph import ComponentGraph
import build_db


def repair_closure(conn: sqlite3.Connection) -> dict[str, int]:
    primary, alternatives = defaultdict(list), defaultdict(list)
    for parent, child, source in conn.execute('SELECT * FROM component_edges'):
        edges = primary if source in ('chise', 'atomic') else alternatives
        edges[parent].append(child)
    graph = ComponentGraph(primary, alternatives)
    stats = {'updated': 0, 'inserted': 0, 'deleted': 0}
    characters = conn.execute('SELECT char, sort_priority, stroke_count, freq FROM characters').fetchall()
    with conn:
        for char, priority, strokes, freq in characters:
            expected = graph.closure(char)
            previous = {row[0]: tuple(row[1:]) for row in conn.execute('''
                SELECT component, min_depth, is_direct, via_char
                FROM component_closure WHERE target_char=?
            ''', (char,))}
            updates, inserts = [], []
            for component, path in expected.items():
                if component not in previous:
                    inserts.append((component, char, *path, priority, strokes, freq))
                elif previous[component] != path:
                    updates.append((*path, component, char))
            deletes = [(component, char) for component in previous.keys() - expected.keys()]
            conn.executemany('''UPDATE component_closure SET min_depth=?, is_direct=?, via_char=?
                                WHERE component=? AND target_char=?''', updates)
            conn.executemany('INSERT INTO component_closure VALUES (?, ?, ?, ?, ?, ?, ?, ?)', inserts)
            conn.executemany('DELETE FROM component_closure WHERE component=? AND target_char=?', deletes)
            stats['updated'] += len(updates)
            stats['inserted'] += len(inserts)
            stats['deleted'] += len(deletes)
    return stats


def repair(db_path=build_db.DB_PATH):
    db_path = Path(db_path)
    package = db_path.with_suffix(db_path.suffix + '.gz')
    backup_dir = Path(tempfile.mkdtemp(prefix='kanji-component-closure-'))
    with sqlite3.connect(db_path) as conn:
        with sqlite3.connect(backup_dir / db_path.name) as target:
            conn.backup(target)
        if package.exists():
            shutil.copy2(package, backup_dir / package.name)
        stats = repair_closure(conn)
        if conn.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise RuntimeError('データベース整合性検査に失敗しました')
        snapshot = backup_dir / 'repaired.db'
        with sqlite3.connect(snapshot) as target:
            conn.backup(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=package.parent, prefix=package.name + '.',
                                         suffix='.tmp', delete=False) as raw:
            temporary = Path(raw.name)
            with snapshot.open('rb') as source:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as target:
                    shutil.copyfileobj(source, target)
        temporary.replace(package)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print({'backup': str(backup_dir), **stats, 'package': str(package)}, flush=True)
    return stats


if __name__ == '__main__':
    repair()
