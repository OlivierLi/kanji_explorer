"""Repair source-derived metadata in place, preserving unrelated tables and word IDs.

Run from the repository root. Creates a SQLite-consistent backup and a packaged
asset backup under /tmp before editing, then atomically replaces the gzip asset.
"""
from contextlib import closing
from pathlib import Path
import gzip
import os
import re
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_db
from scripts.build_words_db import load_wiktionary_definitions


def repair(db_path=build_db.DB_PATH):
    db_path = Path(db_path)
    package = db_path.with_suffix(db_path.suffix + '.gz')
    backup_dir = Path(tempfile.mkdtemp(prefix='kanji-review-metadata-'))
    with closing(sqlite3.connect(db_path)) as conn:
        with closing(sqlite3.connect(backup_dir / db_path.name)) as backup:
            conn.backup(backup)
        if package.exists():
            shutil.copy2(package, backup_dir / package.name)
        before = {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                  for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        unihan = build_db.parse_unihan()
        wiki = load_wiktionary_definitions()
        reading_updates = []
        for char, on, kun in conn.execute('SELECT char, ja_on, ja_kun FROM characters'):
            if not re.search('[A-Za-z]', (on or '') + (kun or '')):
                continue
            source_on, source_kun = build_db.unihan_kana_readings(unihan.get(char, {}))
            if (re.search('[A-Za-z]', on or '') and source_on is None or
                    re.search('[A-Za-z]', kun or '') and source_kun is None):
                raise ValueError(f'読み資料が不足しています: {char}')
            # Only replace the invalid legacy column; preserve existing kana metadata.
            reading_updates.append((source_on if re.search('[A-Za-z]', on or '') else on,
                                    source_kun if re.search('[A-Za-z]', kun or '') else kun, char))
        pos_updates = [(entry['pos'], lemma) for lemma, entry in wiki.items()
                       if entry['pos'] in ('形容動詞', '感動詞')]
        with conn:
            conn.executemany('UPDATE characters SET ja_on=?, ja_kun=? WHERE char=?', reading_updates)
            old_changes = conn.total_changes
            for pos, lemma in pos_updates:
                conn.execute(
                    "UPDATE words SET pos=? WHERE lemma=? AND pos='動詞' AND source='Wiktionary'",
                    (pos, lemma),
                )
            word_changes = conn.total_changes - old_changes
        after = {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in before}
        assert before == after, (before, after)
        assert conn.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        # Package a consistent SQLite snapshot, including committed WAL content.
        snapshot = backup_dir / 'repaired.db'
        with closing(sqlite3.connect(snapshot)) as target:
            conn.backup(target)
    temporary_package = package.with_suffix(package.suffix + '.tmp')
    try:
        with snapshot.open('rb') as src, temporary_package.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as dst:
                shutil.copyfileobj(src, dst)
        os.replace(temporary_package, package)
    finally:
        temporary_package.unlink(missing_ok=True)
    result = {'backup': str(backup_dir), 'reading_rows': len(reading_updates),
              'word_rows': word_changes, 'table_counts': after, 'package': str(package)}
    print(result)
    return result


if __name__ == '__main__':
    repair()
