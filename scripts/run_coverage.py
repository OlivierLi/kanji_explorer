#!/usr/bin/env python3
"""テスト実行・カバレッジ算出・デッドコード検出 統合ランナー."""

import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_command(cmd: list[str], desc: str) -> int:
    print(f"\n{'='*70}")
    print(f"▶ {desc}")
    print(f"  コマンド: {' '.join(cmd)}")
    print(f"{'='*70}")
    res = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if res.returncode != 0:
        print(f"❌ {desc} が失敗しました (終了コード: {res.returncode})")
    else:
        print(f"✅ {desc} が正常に完了しました")
    return res.returncode


def main() -> int:
    print("=" * 70)
    print("漢字構造エクスプローラー: 統合検証パイプライン")
    print(" (テスト実行 / カバレッジ算出 / デッドコード静的解析)")
    print("=" * 70)

    # 1. pytest 実行 + カバレッジ収集
    cov_run_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "-m",
        "pytest",
        "tests/",
        "-q",
    ]
    code = run_command(cov_run_cmd, "Pytest テストスイート実行 & カバレッジ収集")
    if code != 0:
        return code

    # 2. ターミナルカバレッジレポート生成
    cov_rep_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "report",
        "-m",
    ]
    code = run_command(cov_rep_cmd, "カバレッジレポート生成 (ターミナル)")
    if code != 0:
        return code

    # 3. HTML カバレッジレポート生成
    cov_html_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "html",
    ]
    code = run_command(cov_html_cmd, "HTMLカバレッジレポート生成 (coverage_html/)")
    if code != 0:
        return code

    # 4. デッドコード検出 (vulture)
    vulture_cmd = [
        sys.executable,
        "-m",
        "vulture",
        "ids_parser.py",
        "glyph_service.py",
        "server.py",
        "view_renderer.py",
        "vulture_whitelist.py",
        "--min-confidence",
        "60",
    ]
    code = run_command(vulture_cmd, "デッドコード静的解析 (vulture)")
    if code != 0:
        return code

    print("\n" + "=" * 70)
    print("🎉 すべての検証ステージに完全合格しました！")
    print(f" - カバレッジHTML詳細: {REPO_ROOT / 'coverage_html' / 'index.html'}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
