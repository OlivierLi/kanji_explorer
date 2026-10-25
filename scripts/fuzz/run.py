"""
scripts/fuzz/run.py
漢字ハイライト幾何構造・ファジング検査メイン実行CLI。

使用例:
  python3 scripts/fuzz/run.py --tier 1 --oracles A,B,C --limit 100
  python3 scripts/fuzz/run.py --tier 1 --workers 8
  python3 scripts/fuzz/run.py --char 巣
  python3 scripts/fuzz/run.py --tier 3 --limit 500 --diff fuzz_report/failures_prev.jsonl
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import ids_parser
import glyph_service

from scripts.fuzz import corpus, invariants, raster, kvg_oracle, report

REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "fuzz_report"


def inspect_single_char(
    char: str,
    active_oracles: set[str],
) -> list[dict[str, Any]]:
    """単一文字に対して指定されたOracle群を適用し、違反レコードリストを生成。"""
    violations: list[dict[str, Any]] = []

    tree = None
    out_svg = None

    needs_tree = bool(active_oracles & {"A", "B", "C"})
    needs_svg = bool(active_oracles & {"B"})

    if needs_tree:
        try:
            tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
        except Exception as e:
            violations.append({
                "char": char,
                "oracle": "A0",
                "path": "0",
                "component": char,
                "score": 10.0,
                "message": f"decompose_character 例外: {e}",
            })
            return violations

    if needs_svg and tree is not None:
        try:
            out_svg = glyph_service.build_interactive_ids_svg(tree)
        except Exception as e:
            violations.append({
                "char": char,
                "oracle": "B0",
                "path": "0",
                "component": char,
                "score": 10.0,
                "message": f"build_interactive_ids_svg 例外: {e}",
            })

    # Oracle A
    if "A" in active_oracles and tree is not None:
        for v in invariants.check_oracle_a(char, tree=tree):
            d = v.to_dict()
            violations.append(d)

    # Oracle B
    if "B" in active_oracles and tree is not None and out_svg is not None:
        for v in raster.check_oracle_b(char, tree=tree, out_svg_data=out_svg):
            d = v.to_dict()
            # 実測クリップ矩形をタイル描画用に添付
            for l in out_svg.get("component_layers", []):
                if l.get("path") == d.get("path"):
                    d["actual_clip_rects"] = l.get("clip_rects")
                    break
            violations.append(d)

    # Oracle C
    if "C" in active_oracles and tree is not None:
        for v in kvg_oracle.check_oracle_c(char, tree=tree):
            d = v.to_dict()
            violations.append(d)

    return violations


def _worker_task(args: tuple[str, set[str]]) -> list[dict[str, Any]]:
    ch, orcs = args
    return inspect_single_char(ch, orcs)


def run_diff(current_failures: list[dict[str, Any]], prev_file: Path) -> dict[str, Any]:
    """過去の failures.jsonl と現在の結果を比較して差分を算出。"""
    if not prev_file.exists():
        return {}

    prev_records: list[dict[str, Any]] = []
    with open(prev_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                prev_records.append(json.loads(line))

    prev_keys = {(r.get("char"), r.get("path"), r.get("oracle")) for r in prev_records}
    curr_keys = {(r.get("char"), r.get("path"), r.get("oracle")) for r in current_failures}

    fixed = prev_keys - curr_keys
    new_violations = curr_keys - prev_keys
    persisting = curr_keys & prev_keys

    return {
        "prev_count": len(prev_records),
        "curr_count": len(current_failures),
        "fixed_count": len(fixed),
        "new_count": len(new_violations),
        "persisting_count": len(persisting),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Kanji Highlight Geometry Fuzzer")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=1, help="対象コーパス (1: 常用・人名用, 2: KanjiVG, 3: リスク構文)")
    parser.add_argument("--oracles", type=str, default="A,B,C", help="実行するOracle (カンマ区切り: A,B,C)")
    parser.add_argument("--limit", type=int, default=None, help="検査文字数の上限")
    parser.add_argument("--char", type=str, default=None, help="単一文字のみ検査する場合に指定")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1), help="並列プロセス数")
    parser.add_argument("--diff", type=str, default=None, help="比較用前回収果 JSONL パス")
    parser.add_argument("--sheets", type=int, default=3, help="生成するコンタクトシート数 (0で無効化)")
    parser.add_argument("--output-dir", type=str, default=str(REPORT_DIR), help="レポート出力ディレクトリ")

    args = parser.parse_args()

    active_oracles = {o.strip().upper() for o in args.oracles.split(",") if o.strip()}
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.char:
        char_list = [args.char]
    else:
        char_list = corpus.get_corpus(tier=args.tier, limit=args.limit)

    total_chars = len(char_list)
    print(f"======================================================================")
    print(f"▶ 漢字ハイライト幾何構造ファジング検査開始")
    print(f"  対象文字数: {total_chars:,} 文字 (Tier {args.tier})")
    print(f"  有効Oracle: {', '.join(sorted(active_oracles))}")
    print(f"  並列ワーカー数: {args.workers}")
    print(f"======================================================================")

    t0 = time.time()
    all_failures: list[dict[str, Any]] = []

    tasks = [(ch, active_oracles) for ch in char_list]

    completed_chars = 0
    if args.workers > 1 and len(tasks) > 5:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(_worker_task, t) for t in tasks]
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                if res:
                    all_failures.extend(res)
                completed_chars += 1
                if completed_chars % 500 == 0 or completed_chars == total_chars:
                    rate = completed_chars / max(0.01, time.time() - t0)
                    print(f"  進捗: {completed_chars:,}/{total_chars:,} 文字完了 ({rate:.1f} 文字/秒, 違反: {len(all_failures):,} 件)")
    else:
        for t in tasks:
            res = _worker_task(t)
            if res:
                all_failures.extend(res)
            completed_chars += 1
            if completed_chars % 200 == 0 or completed_chars == total_chars:
                rate = completed_chars / max(0.01, time.time() - t0)
                print(f"  進捗: {completed_chars:,}/{total_chars:,} 文字完了 ({rate:.1f} 文字/秒, 違反: {len(all_failures):,} 件)")

    elapsed = time.time() - t0
    print(f"\n✅ 検査完了: {total_chars:,} 文字を {elapsed:.2f} 秒で検証しました。")
    print(f"   検出違反総数: {len(all_failures):,} 件 (影響文字数: {len({f['char'] for f in all_failures}):,} 文字)")

    # 1. failures.jsonl 出力
    jsonl_path = out_dir / "failures.jsonl"
    report.write_failures_jsonl(all_failures, jsonl_path)
    print(f"   - 違反ログ出力: {jsonl_path}")

    # 2. summary.md 出力
    summary_md = report.generate_summary_markdown(all_failures, total_chars, elapsed, tier=args.tier)
    summary_path = out_dir / "summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    print(f"   - 診断サマリー: {summary_path}")

    # 3. コンタクトシート生成
    if args.sheets > 0 and all_failures:
        sheets_dir = out_dir / "sheets"
        sheets = report.generate_contact_sheets(all_failures, sheets_dir, max_sheets=args.sheets)
        print(f"   - コンタクトシート ({len(sheets)} 枚): {sheets_dir}")

    # 4. 差分検証 (存在する場合)
    if args.diff:
        diff_res = run_diff(all_failures, Path(args.diff))
        if diff_res:
            print(f"\n======================================================================")
            print(f"▶ 前回実行との差分検証結果")
            print(f"  前回違反件数: {diff_res['prev_count']:,} 件 → 今回: {diff_res['curr_count']:,} 件")
            print(f"  解消済み違反: {diff_res['fixed_count']:,} 件 🎉")
            print(f"  新規発生違反: {diff_res['new_count']:,} 件")
            print(f"  継続中違反: {diff_res['persisting_count']:,} 件")
            print(f"======================================================================")


if __name__ == "__main__":
    main()
