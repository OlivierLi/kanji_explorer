"""
scripts/fuzz/report.py
トリアージ・レポート生成・コンタクトシート画像生成モジュール。

fuzz.md 仕様:
- fuzz_report/summary.md: 各Oracleごとの検出数、シグネチャ別グループ集計、最悪ケース一覧
- fuzz_report/failures.jsonl: 機械可読な全違反データ (差分検証用)
- fuzz_report/sheets/sheet_*.png: 最悪不具合レイヤーのコンタクトシート画像 (60グリフ/シート)
  (背景: グリフ薄灰, ハイライト: 朱色, クリップ枠: 暗線, KVG正解枠: 青破線)
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import numpy as np

import glyph_service
from . import raster

REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "fuzz_report"
FONT_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "fonts" / "Jigmo.ttf"


def write_failures_jsonl(failures: list[dict[str, Any]], filepath: Path) -> None:
    """違反レコードを JSONL ファイルに出力します。"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for fail in failures:
            f.write(json.dumps(fail, ensure_ascii=False) + "\n")


def compute_damage_score(item: dict[str, Any]) -> float:
    """ユーザー視認ダメージ優先度スコアを算出: max(B5, B6, B8) * stroke_share を最優先。"""
    orc = item.get("oracle", "")
    sc = float(item.get("score", 0.0))
    ss = float(item.get("stroke_share", 0.0) or 0.15)
    if orc in ("B5", "B6", "B8"):
        return sc * max(0.10, ss) * 2.5
    if orc in ("B1", "B7"):
        return sc * max(0.10, ss) * 1.5
    if orc in ("C0", "C1", "C2"):
        return sc * 0.8
    return sc * 0.5


def generate_summary_markdown(
    failures: list[dict[str, Any]],
    total_chars: int,
    elapsed_sec: float,
    tier: int = 1,
) -> str:
    """トリアージ用の総合サマリー Markdown 文書を生成します。"""
    unique_chars = len({f["char"] for f in failures})
    oracle_counts: dict[str, int] = defaultdict(int)
    sig_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for f in failures:
        oracle_counts[f.get("oracle", "UNKNOWN")] += 1
        sig = f.get("signature") or "generic"
        sig_groups[sig].append(f)

    # シグネチャ別ランキング (違反件数 x 最悪ダメージスコア)
    sig_ranked = sorted(
        sig_groups.items(),
        key=lambda item: len(item[1]) * max(compute_damage_score(x) for x in item[1]),
        reverse=True,
    )

    # 個別レイヤーワーストランキング (ユーザー視認ダメージ順)
    worst_layers = sorted(
        failures,
        key=compute_damage_score,
        reverse=True,
    )[:50]

    md = []
    md.append(f"# 漢字構造エクスプローラー ファジング検査レポート (Tier {tier})\n")
    md.append(f"- **検査文字総数**: {total_chars:,} 文字")
    md.append(f"- **検出違反総数**: {len(failures):,} 件 (影響文字数: {unique_chars:,} 文字)")
    md.append(f"- **検査所要時間**: {elapsed_sec:.2f} 秒\n")

    md.append("## 1. Oracle 別検出内訳\n")
    md.append("| Oracle | 分類 | 検出件数 | 概要 |")
    md.append("|:---:|:---|---:|:---|")

    oracle_meta = {
        "A1": ("幾何不変", "子要素 bbox の親領域はみ出し"),
        "A2": ("形状不変", "単一筆画部品 (一/丨/丶) の異常肥大化"),
        "A3": ("面積不変", "画数シェアに対する矩形面積の過剰占奪 (3.2倍超)"),
        "A4": ("スケール不変", "終端葉ノードの異常占有"),
        "A5": ("配置不変", "非重畳演算子における兄弟要素の過度な重複"),
        "A6": ("包囲不変", "包囲構え外枠 hit_rects による内側要素の中心遮蔽"),
        "B1": ("インク実測", "画数シェアに対する実インク占有率の過大点灯 (巣バグ型)"),
        "B2": ("インク実測", "兄弟要素間でのインク二重点灯・重複侵食"),
        "B3": ("インク実測", "子要素群による親インク被覆率不足 (筆画欠落)"),
        "B4": ("インク実測", "部品ハイライト時のインク空白 (不発)"),
        "B5": ("インク実測", "近傍に空隙が存在するインク島のクリップ切断"),
        "B6": ("インク実測", "単一インク島の複数葉ノード分割 (細片化)"),
        "B7": ("インク実測", "画数シェアに対する実インク占有率の過小ハイライト"),
        "B8": ("インク実測", "クリップ矩形境界による実インク直線切断"),
        "C0": ("KanjiVG比較", "KanjiVGデータが存在するのにIDSノードと0件マッチ"),
        "C1": ("KanjiVG比較", "正解ストロークグループとの IoU 著しい乖離 (< 0.28)"),
        "C2": ("KanjiVG比較", "正解ストロークグループとの重心オフセット過大 (> 0.22)"),
    }

    for oc in sorted(oracle_counts.keys()):
        cat, desc = oracle_meta.get(oc, ("未分類", "その他の不変条件違反"))
        md.append(f"| **{oc}** | {cat} | {oracle_counts[oc]:,} 件 | {desc} |")
    md.append("")

    md.append("## 2. 最も頻出・重篤な構文シグネチャ Top 20\n")
    md.append("共通の原因（同一の演算子・部品組み合わせルール）ごとにグループ化されたランキングです。\n")
    md.append("| 順位 | シグネチャ (`op:c0+c1@depth:role`) | 件数 | 最大スコア | 代表例 | 主な診断メッセージ |")
    md.append("|:---:|:---|---:|---:|:---:|:---|")

    for rank, (sig, items) in enumerate(sig_ranked[:20], 1):
        count = len(items)
        max_score = max(x.get("score", 0.0) for x in items)
        worst_item = max(items, key=lambda x: x.get("score", 0.0))
        ex_char = worst_item.get("char", "")
        ex_comp = worst_item.get("component", "")
        ex_msg = worst_item.get("message", "").replace("|", "\\|")
        md.append(f"| {rank} | `{sig}` | {count} | {max_score:.2f} | **{ex_char}** ({ex_comp}) | {ex_msg} |")
    md.append("")

    md.append("## 3. 個別レイヤー ワースト Top 30\n")
    md.append("| 順位 | 文字 | パス | 部品 | Oracle | スコア | 診断メッセージ |")
    md.append("|:---:|:---:|:---:|:---:|:---:|---:|:---|")

    for rank, item in enumerate(worst_layers[:30], 1):
        ch = item.get("char", "")
        p = item.get("path", "")
        comp = item.get("component", "")
        orc = item.get("oracle", "")
        sc = item.get("score", 0.0)
        msg = item.get("message", "").replace("|", "\\|")
        md.append(f"| {rank} | **{ch}** | `{p}` | {comp} | **{orc}** | {sc:.2f} | {msg} |")
    md.append("")

    md.append("## 4. コンタクトシート\n")
    md.append("視覚的確認用コンタクトシートは `fuzz_report/sheets/` に出力されています。\n")
    md.append("- グリフベース: 薄灰色 (`#b0b8c4`)\n")
    md.append("- ハイライトインク: 朱色 (`#ff5a36`)\n")
    md.append("- クリップ境界: 暗色枠線 (`#24292f`)\n")
    md.append("- KanjiVG正解領域: 青色枠線 (`#0969da`)\n")

    return "\n".join(md)


def generate_single_tile(
    char: str,
    fail: dict[str, Any],
    tile_w: int = 180,
    tile_h: int = 220,
    glyph_size: int = 150,
) -> Image.Image:
    """単一不具合の可視化タイル画像を生成。"""
    tile = Image.new("RGB", (tile_w, tile_h), "#ffffff")
    draw = ImageDraw.Draw(tile)

    # 枠線
    draw.rectangle([2, 2, tile_w - 3, tile_h - 3], fill="#fafbfc", outline="#e1e4e8", width=1)

    # グリフのベースラスタとハイライトラスタを生成
    svg_p = glyph_service.get_jigmo_path(char) or ""
    R = raster.rasterize_glyph_path(svg_p, size=glyph_size)

    # クリップ矩形マスク
    clip_rects = fail.get("actual_clip_rects")
    if not clip_rects:
        bbox = fail.get("bbox") or fail.get("ids_bbox") or [0, 0, 1, 1]
        clip_rects = [bbox]

    c_mask = raster.create_clip_mask(clip_rects, size=glyph_size)
    L = R & c_mask

    # グリフ描画オフセット
    gx = (tile_w - glyph_size) // 2
    gy = 8

    # ピクセル配列を描画
    # R: #c6cbd1, L: #ff5a36 (朱色)
    tile_arr = np.array(tile)
    base_color = np.array([198, 203, 209], dtype=np.uint8)
    hl_color = np.array([255, 90, 54], dtype=np.uint8)

    sub_view = tile_arr[gy : gy + glyph_size, gx : gx + glyph_size]
    sub_view[R] = base_color
    sub_view[L] = hl_color
    tile_arr[gy : gy + glyph_size, gx : gx + glyph_size] = sub_view

    tile = Image.fromarray(tile_arr)
    draw = ImageDraw.Draw(tile)

    # クリップ矩形のアウトライン (黒線)
    for cr in clip_rects:
        x1 = gx + int(cr[0] * glyph_size)
        y1 = gy + int(cr[1] * glyph_size)
        x2 = gx + int(round((cr[0] + cr[2]) * glyph_size))
        y2 = gy + int(round((cr[1] + cr[3]) * glyph_size))
        draw.rectangle([x1, y1, x2, y2], outline="#24292f", width=1)

    # KanjiVG 正解矩形のアウトライン (青線)
    k_box = fail.get("kvg_bbox")
    if k_box:
        kx1 = gx + int(k_box[0] * glyph_size)
        ky1 = gy + int(k_box[1] * glyph_size)
        kx2 = gx + int(round((k_box[0] + k_box[2]) * glyph_size))
        ky2 = gy + int(round((k_box[1] + k_box[3]) * glyph_size))
        draw.rectangle([kx1, ky1, kx2, ky2], outline="#0969da", width=2)

    # キャプションテキスト
    font_main = None
    font_sub = None
    if FONT_PATH.exists():
        try:
            font_main = ImageFont.truetype(str(FONT_PATH), 13)
            font_sub = ImageFont.truetype(str(FONT_PATH), 11)
        except Exception:
            pass

    p = fail.get("path", "")
    comp = fail.get("component", "")
    orc = fail.get("oracle", "")
    score = fail.get("score", 0.0)

    draw.text((8, glyph_size + 14), f"{char} ({p}: {comp})", fill="#1f2328", font=font_main)
    draw.text((8, glyph_size + 34), f"[{orc}] score: {score:.1f}", fill="#cf222e", font=font_sub)

    return tile


def generate_contact_sheets(
    failures: list[dict[str, Any]],
    out_dir: Path,
    max_sheets: int = 5,
    tiles_per_sheet: int = 60,
    cols: int = 6,
) -> list[Path]:
    """最悪スコアの不具合からコンタクトシートPNG画像を生成します。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: list[Path] = []

    # ユーザー視認ダメージスコア順にソートし、重複文字・同一パスを適度に間引いて多様なサンプルを抽出
    ranked = sorted(failures, key=compute_damage_score, reverse=True)
    selected: list[dict[str, Any]] = []
    seen_char_paths: set[tuple[str, str]] = set()

    for item in ranked:
        key = (item.get("char", ""), item.get("path", ""))
        if key not in seen_char_paths:
            seen_char_paths.add(key)
            selected.append(item)

    total_sheets = min(max_sheets, max(1, (len(selected) + tiles_per_sheet - 1) // tiles_per_sheet))

    tile_w, tile_h = 180, 220

    for sheet_idx in range(total_sheets):
        batch = selected[sheet_idx * tiles_per_sheet : (sheet_idx + 1) * tiles_per_sheet]
        if not batch:
            break

        rows = (len(batch) + cols - 1) // cols
        sheet_w = cols * tile_w
        sheet_h = rows * tile_h

        sheet = Image.new("RGB", (sheet_w, sheet_h), "#ffffff")

        for idx, fail in enumerate(batch):
            r = idx // cols
            c = idx % cols
            tile = generate_single_tile(fail.get("char", ""), fail, tile_w=tile_w, tile_h=tile_h)
            sheet.paste(tile, (c * tile_w, r * tile_h))

        sheet_file = out_dir / f"sheet_{sheet_idx + 1:02d}.png"
        sheet.save(sheet_file)
        generated_paths.append(sheet_file)

    return generated_paths
