"""First-start extraction publishes complete snapshots and cleans failures."""
from concurrent.futures import ThreadPoolExecutor
import gzip
import sqlite3
import threading

import pytest

import server


@pytest.fixture
def packaged_database(tmp_path, monkeypatch):
    path = tmp_path / 'kanji.db'
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE example (value)')
        conn.execute("INSERT INTO example VALUES ('完成')")
    with gzip.open(path.with_suffix('.db.gz'), 'wb') as target:
        target.write(source.read_bytes())
    monkeypatch.setattr(server, 'DB_PATH', path)
    monkeypatch.setattr(server, '_thread_local', threading.local())
    return path, source.read_bytes()


def test_concurrent_first_connections_publish_complete_database(packaged_database, monkeypatch):
    path, expected = packaged_database
    barrier = threading.Barrier(2)
    copy_file = server.shutil.copyfileobj
    targets = []

    def concurrent_copy(source, target):
        targets.append(target.name)
        barrier.wait(timeout=10)
        copy_file(source, target)
        # Neither worker publishes until both copies are complete.
        barrier.wait(timeout=10)
        assert not path.exists()
        barrier.wait(timeout=10)

    monkeypatch.setattr(server.shutil, 'copyfileobj', concurrent_copy)

    def connect():
        try:
            return server.get_db_connection().execute('SELECT value FROM example').fetchone()[0]
        finally:
            server.close_db_connection()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(connect) for _ in range(2)]
        assert [f.result(timeout=15) for f in futures] == ['完成', '完成']
    assert targets[0] != targets[1]
    assert path.read_bytes() == expected
    assert not list(path.parent.glob('*.tmp'))


@pytest.mark.parametrize('payload', [b'not gzip', gzip.compress(b'partial')[:-4]])
def test_failed_extraction_leaves_no_database_or_temporary_files(packaged_database, payload):
    path, _ = packaged_database
    path.with_suffix('.db.gz').write_bytes(payload)
    assert server.get_db_connection() is None
    assert not path.exists()
    assert not list(path.parent.glob('*.tmp'))


def test_existing_database_needs_no_package(packaged_database):
    path, expected = packaged_database
    path.write_bytes(expected)
    path.with_suffix('.db.gz').unlink()
    try:
        assert server.get_db_connection().execute('SELECT value FROM example').fetchone()[0] == '完成'
    finally:
        server.close_db_connection()


def test_readonly_database_uri_escapes_special_path_characters(packaged_database, monkeypatch):
    original, expected = packaged_database
    path = original.with_name('kanji #1?.db')
    path.write_bytes(expected)
    monkeypatch.setattr(server, 'DB_PATH', path)
    try:
        assert server.get_db_connection().execute('SELECT value FROM example').fetchone()[0] == '完成'
    finally:
        server.close_db_connection()
