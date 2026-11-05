"""Regression tests for PythonAnywhere packaging, manifest completeness, and WSGI entrypoint isolation."""
from __future__ import annotations

import ast
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

import scripts.package_for_pythonanywhere as pkg


ROOT = Path(__file__).resolve().parent.parent


def test_code_files_covers_all_runtime_transitive_imports():
    """Every internal Python module imported by runtime code must be in CODE_FILES."""
    code_set = set(pkg.CODE_FILES)
    assert "component_graph.py" in code_set
    assert "geometry.py" in code_set
    assert "server.py" in code_set
    assert "wsgi.py" in code_set

    for rel_path in pkg.CODE_FILES:
        path = ROOT / rel_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            mod_name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name.split(".")[0]
                    target_file = f"{mod_name}.py"
                    if (ROOT / target_file).is_file():
                        assert target_file in code_set, (
                            f"{rel_path} imports {target_file}, which is missing from CODE_FILES"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod_name = node.module.split(".")[0]
                target_file = f"{mod_name}.py"
                if (ROOT / target_file).is_file():
                    assert target_file in code_set, (
                        f"{rel_path} imports {target_file}, which is missing from CODE_FILES"
                    )


def test_all_code_files_have_future_annotations():
    """All runtime Python modules must include future annotations for Python <3.10 compatibility."""
    for rel_path in pkg.CODE_FILES:
        path = ROOT / rel_path
        content = path.read_text(encoding="utf-8")
        assert "from __future__ import annotations" in content, (
            f"{rel_path} is missing 'from __future__ import annotations'"
        )


def test_package_manifest_runtime_data_coverage():
    """Key runtime datasets used by server and parsers must be registered in the packaging manifest."""
    expected_data = {
        "data/kanji_explorer.db.gz",
        "data/kanjivg.xml.gz",
        "data/cjkvi-ids.txt",
        "data/EquivalentUnifiedIdeograph.txt",
        "data/entity_unicode_map.tsv",
    }
    expected_dirs = {
        "static",
        "data/chise-ids",
        "data/glyphwiki_cache",
    }
    assert expected_data.issubset(set(pkg.RUNTIME_DATA))
    assert expected_dirs.issubset(set(pkg.RUNTIME_DIRS))

    # All files in RUNTIME_DATA and RUNTIME_DIRS must physically exist in the repository
    for rel in pkg.RUNTIME_DATA:
        assert (ROOT / rel).is_file(), f"Declared runtime data file does not exist: {rel}"
    for rel in pkg.RUNTIME_DIRS:
        assert (ROOT / rel).is_dir(), f"Declared runtime directory does not exist: {rel}"


def test_package_for_pythonanywhere_isolated_wsgi_execution(tmp_path, monkeypatch):
    """Packaging produces an app.zip that can serve WSGI requests in a completely isolated environment."""
    target = tmp_path / "deploy"
    monkeypatch.setattr(sys, "argv", ["package_for_pythonanywhere.py", str(target)])
    pkg.main()

    zip_file = target / "app.zip"
    assert zip_file.is_file()
    assert (target / "INSTALL.txt").is_file()

    with tempfile.TemporaryDirectory() as extract_dir:
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(extract_dir)

        isolated_script = (
            "import wsgi\n"
            "def call_wsgi(path, method='GET'):\n"
            "    status_holder = []\n"
            "    def start_response(status, headers):\n"
            "        status_holder.append(status)\n"
            "    environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': ''}\n"
            "    body = wsgi.application(environ, start_response)\n"
            "    return status_holder[0], b''.join(body)\n"
            "\n"
            "# 1. Root index\n"
            "status, body = call_wsgi('/')\n"
            "assert status == '200 OK'\n"
            "assert len(body) > 0\n"
            "\n"
            "# 2. Static CSS file\n"
            "status, body = call_wsgi('/static/styles.css')\n"
            "assert status == '200 OK'\n"
            "assert len(body) > 0\n"
            "\n"
            "# 3. HEAD request\n"
            "status, body = call_wsgi('/static/styles.css', method='HEAD')\n"
            "assert status == '200 OK'\n"
            "assert body == b''\n"
            "\n"
            "# 4. OPTIONS request\n"
            "status, body = call_wsgi('/', method='OPTIONS')\n"
            "assert status == '204 No Content'\n"
            "\n"
            "# 5. 404 handler\n"
            "status, body = call_wsgi('/nonexistent')\n"
            "assert status == '404 Not Found'\n"
            "\n"
            "print('ISOLATED_WSGI_ALL_PASSED')\n"
        )

        res = subprocess.run(
            [sys.executable, "-c", isolated_script],
            cwd=extract_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert res.returncode == 0, f"WSGI isolated check failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
        assert "ISOLATED_WSGI_ALL_PASSED" in res.stdout


def test_code_only_update_over_existing_database(tmp_path, monkeypatch):
    """Simulate 'update only the code' workflow: app.zip unzipped over existing database without .gz."""
    target = tmp_path / "deploy"
    monkeypatch.setattr(sys, "argv", ["package_for_pythonanywhere.py", str(target)])
    pkg.main()

    with tempfile.TemporaryDirectory() as deployed_app_dir:
        app_path = Path(deployed_app_dir)
        db_dir = app_path / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_file = db_dir / "kanji_explorer.db"

        # Create minimal sqlite database matching characters table structure
        with sqlite3.connect(db_file) as conn:
            conn.execute(
                "CREATE TABLE characters (char TEXT PRIMARY KEY, codepoint TEXT, "
                "tier TEXT, stroke_count INTEGER, chise_ids TEXT, ja_on TEXT, "
                "ja_kun TEXT, grade INTEGER, freq INTEGER, sort_priority INTEGER)"
            )
            conn.execute(
                "INSERT INTO characters VALUES ('日', 'U+65E5', '基本漢字', 4, '日', 'ニチ', 'ひ', 1, 1, 1)"
            )

        # Unpack code-only app.zip directly over deployed app directory
        with zipfile.ZipFile(target / "app.zip", "r") as zf:
            zf.extractall(app_path)

        script = (
            "import wsgi\n"
            "status_holder = []\n"
            "def start_response(status, headers):\n"
            "    status_holder.append(status)\n"
            "environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/api/char', 'QUERY_STRING': 'q=日'}\n"
            "body = wsgi.application(environ, start_response)\n"
            "assert status_holder[0] == '200 OK', f'Status was {status_holder}'\n"
            "print('CODE_ONLY_UPDATE_PASSED')\n"
        )

        res = subprocess.run(
            [sys.executable, "-c", script],
            cwd=deployed_app_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert res.returncode == 0, f"Code-only update WSGI check failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
        assert "CODE_ONLY_UPDATE_PASSED" in res.stdout
