"""デッドコード検出（Dead Code Detection）自動テストスイート.

vulture を用いて ids_parser.py, glyph_service.py, server.py の静的解析を行い、
未参照の関数・メソッド・変数・クラス・プロパティが存在しないことを自動保証します。
"""

from pathlib import Path
import subprocess


def test_zero_dead_code_with_vulture():
    """リポジトリ全体にデッドコードが存在しないことを検証（許容ホワイトリスト照合）."""
    repo_root = Path(__file__).resolve().parent.parent

    target_files = [
        str(repo_root / "ids_parser.py"),
        str(repo_root / "glyph_service.py"),
        str(repo_root / "server.py"),
        str(repo_root / "view_renderer.py"),
        str(repo_root / "vulture_whitelist.py"),
    ]

    cmd = [
        "python3",
        "-m",
        "vulture",
        *target_files,
        "--min-confidence",
        "60",
    ]

    res = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )

    assert res.returncode == 0, (
        f"【デッドコード検出エラー】未参照のコードが見つかりました:\n{res.stdout}\n{res.stderr}"
    )
