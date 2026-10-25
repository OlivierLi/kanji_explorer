"""
scripts/audit/render_audit.py
常用漢字2,136字の全構成要素ハイライト視覚レンダリング＆検証ツール。

各漢字の全選択可能コンポーネントを実測ラスタライゼーションして画像化し、
全Oracle (A, B, C) の診断結果とともに audit.md 更新用データを出力します。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import ids_parser
import glyph_service
from scripts.fuzz import invariants, raster, kvg_oracle

DB_PATH = BASE_DIR / "data" / "kanji_explorer.db"
FONT_PATH = BASE_DIR / "static" / "fonts" / "Jigmo.ttf"
AUDIT_VISUALS_DIR = BASE_DIR / "audit_visuals"


def get_joyo_by_grade(grade: int) -> list[str]:
    """指定された学年の常用漢字リストを取得。"""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute(
        "SELECT char FROM characters WHERE grade = ? ORDER BY sort_priority, rowid;",
        (grade,),
    )
    chars = [r[0] for r in c.fetchall() if r[0]]
    conn.close()
    return chars


def render_component_tile(
    char: str,
    layer: dict[str, Any],
    R: np.ndarray,
    L: np.ndarray,
    kvg_bbox: list[float] | None = None,
    tile_w: int = 160,
    tile_h: int = 210,
    glyph_size: int = 140,
) -> Image.Image:
    """単一コンポーネント選択時の視覚プレビュータイル画像を生成。"""
    tile = Image.new("RGB", (tile_w, tile_h), "#ffffff")
    draw = ImageDraw.Draw(tile)

    # 外枠
    draw.rectangle([1, 1, tile_w - 2, tile_h - 2], fill="#fafbfc", outline="#e1e4e8", width=1)

    gx = (tile_w - glyph_size) // 2
    gy = 6

    # 140x140 へのリサイズ
    r_img = Image.fromarray(R.astype(np.uint8) * 255).resize((glyph_size, glyph_size), Image.Resampling.NEAREST)
    l_img = Image.fromarray(L.astype(np.uint8) * 255).resize((glyph_size, glyph_size), Image.Resampling.NEAREST)
    r_arr = np.array(r_img) > 0
    l_arr = np.array(l_img) > 0

    base_color = np.array([198, 203, 209], dtype=np.uint8)   # 薄灰 (#c6cbd1)
    hl_color = np.array([255, 90, 54], dtype=np.uint8)       # 朱色 (#ff5a36)

    tile_arr = np.array(tile)
    sub = tile_arr[gy : gy + glyph_size, gx : gx + glyph_size]
    sub[r_arr] = base_color
    sub[l_arr] = hl_color
    tile_arr[gy : gy + glyph_size, gx : gx + glyph_size] = sub

    tile = Image.fromarray(tile_arr)
    draw = ImageDraw.Draw(tile)

    # クリップ矩形のアウトライン (黒線)
    clip_rects = layer.get("clip_rects") or [layer.get("bbox", [0.0, 0.0, 1.0, 1.0])]
    for cr in clip_rects:
        if len(cr) >= 4:
            x1 = gx + int(cr[0] * glyph_size)
            y1 = gy + int(cr[1] * glyph_size)
            x2 = gx + int(round((cr[0] + cr[2]) * glyph_size))
            y2 = gy + int(round((cr[1] + cr[3]) * glyph_size))
            draw.rectangle([x1, y1, x2, y2], outline="#24292f", width=1)

    # KanjiVG正解領域 (青破線相当)
    if kvg_bbox and len(kvg_bbox) >= 4:
        kx1 = gx + int(kvg_bbox[0] * glyph_size)
        ky1 = gy + int(kvg_bbox[1] * glyph_size)
        kx2 = gx + int(round((kvg_bbox[0] + kvg_bbox[2]) * glyph_size))
        ky2 = gy + int(round((kvg_bbox[1] + kvg_bbox[3]) * glyph_size))
        draw.rectangle([kx1, ky1, kx2, ky2], outline="#0969da", width=2)

    # キャプション
    font_main = None
    font_sub = None
    if FONT_PATH.exists():
        try:
            font_main = ImageFont.truetype(str(FONT_PATH), 13)
            font_sub = ImageFont.truetype(str(FONT_PATH), 11)
        except Exception:
            pass

    p = layer.get("path", "")
    comp = layer.get("char") or layer.get("raw_char") or ""
    role = layer.get("role_label", "")
    share = layer.get("_ink_share", 0.0)

    draw.text((6, glyph_size + 10), f"{p} {comp} ({role})", fill="#1f2328", font=font_main)
    draw.text((6, glyph_size + 28), f"ink: {share*100:.1f}%", fill="#57606a", font=font_sub)

    return tile


def render_kanji_card(
    char: str,
    grade: int,
    out_svg_data: dict[str, Any],
    R: np.ndarray,
    layer_masks: dict[str, np.ndarray],
    kvg_groups: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    out_path: Path,
) -> dict[str, Any]:
    """漢字1文字の全コンポーネント選択状態を網羅した視覚検査カードを生成。"""
    layers = out_svg_data.get("component_layers", [])
    tot_ink = max(1, int(np.sum(R)))

    # 各レイヤーのインクシェアを算出
    for l in layers:
        lp = l.get("path", "")
        mask = layer_masks.get(lp)
        l_pix = int(np.sum(mask)) if mask is not None else 0
        l["_ink_share"] = l_pix / tot_ink
        l["_ink_pix"] = l_pix

    kvg_by_elem: dict[str, list[float]] = {}
    for g in kvg_groups:
        ne = g.get("norm_elem") or g.get("elem")
        if ne and "bbox" in g:
            kvg_by_elem[ne] = g["bbox"]

    tile_w, tile_h = 160, 210
    cols = min(6, max(3, len(layers)))
    rows = (len(layers) + cols - 1) // cols

    header_h = 45
    card_w = cols * tile_w + 20
    card_h = header_h + rows * tile_h + 20

    card = Image.new("RGB", (card_w, card_h), "#ffffff")
    draw = ImageDraw.Draw(card)

    font_title = None
    if FONT_PATH.exists():
        try:
            font_title = ImageFont.truetype(str(FONT_PATH), 18)
        except Exception:
            pass

    # ヘッダー情報描画
    v_critical = [v for v in violations if v.get("oracle") in ("B1", "B4", "B5", "B6", "B8")]
    status_str = "⚠️ 問題あり" if v_critical else ("ℹ️ 警告あり" if violations else "✅ 良好")
    status_color = "#cf222e" if v_critical else ("#9a6700" if violations else "#1a7f37")

    draw.text(
        (15, 12),
        f"【{char}】 学年: 小{grade} | 部品数: {len(layers)} | 判定: {status_str}",
        fill=status_color,
        font=font_title,
    )

    # 各コンポーネントタイルを配置
    for idx, l in enumerate(layers):
        r = idx // cols
        c = idx % cols
        lp = l.get("path", "")
        mask = layer_masks.get(lp, np.zeros_like(R))
        comp_char = l.get("char") or l.get("raw_char") or ""
        k_box = kvg_by_elem.get(comp_char)

        tile = render_component_tile(
            char=char,
            layer=l,
            R=R,
            L=mask,
            kvg_bbox=k_box,
            tile_w=tile_w,
            tile_h=tile_h,
        )
        card.paste(tile, (10 + c * tile_w, header_h + r * tile_h))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    card.save(out_path)

    return {
        "char": char,
        "grade": grade,
        "num_layers": len(layers),
        "violations": violations,
        "critical_violations": v_critical,
        "status": "ISSUE" if v_critical else ("WARN" if violations else "OK"),
        "card_image": str(out_path),
    }


def audit_single_kanji(char: str, grade: int, save_card: bool = True) -> dict[str, Any]:
    """単一漢字の構文解析・SVG生成・ラスタライズ・全Oracle検査を実行。"""
    try:
        tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
        out_svg = glyph_service.build_interactive_ids_svg(tree)
        R, layer_masks = raster.compute_all_layer_masks(char, out_svg, size=256)
    except Exception as e:
        return {
            "char": char,
            "grade": grade,
            "status": "ERROR",
            "error": str(e),
            "violations": [{"oracle": "ERR", "message": f"レンダリング例外: {e}"}],
        }

    violations: list[dict[str, Any]] = []

    # 1. Oracle A (幾何不変条件)
    for v in invariants.check_oracle_a(char, tree=tree):
        violations.append(v.to_dict())

    # 2. Oracle B (インク実測 B1~B8)
    for v in raster.check_oracle_b(char, tree=tree, out_svg_data=out_svg):
        violations.append(v.to_dict())

    # 3. Oracle C (KanjiVG正解比較)
    kvg_groups = kvg_oracle.parse_kanjivg_groups(char)
    for v in kvg_oracle.check_oracle_c(char, tree=tree):
        violations.append(v.to_dict())

    card_path = AUDIT_VISUALS_DIR / f"grade_{grade}" / f"{char}.png"
    if save_card:
        return render_kanji_card(
            char=char,
            grade=grade,
            out_svg_data=out_svg,
            R=R,
            layer_masks=layer_masks,
            kvg_groups=kvg_groups,
            violations=violations,
            out_path=card_path,
        )

    return {
        "char": char,
        "grade": grade,
        "num_layers": len(out_svg.get("component_layers", [])),
        "violations": violations,
        "status": "ISSUE" if any(v.get("oracle") in ("B1", "B4", "B5", "B6", "B8") for v in violations) else "OK",
    }


def audit_grade(grade: int, save_cards: bool = True) -> list[dict[str, Any]]:
    """指定学年の漢字を順次レンダリング・検証。"""
    chars = get_joyo_by_grade(grade)
    results = []
    print(f"▶ 小学{grade}年 常用漢字検証開始: 全 {len(chars)} 字")
    t0 = time.time()
    for idx, ch in enumerate(chars, 1):
        res = audit_single_kanji(ch, grade, save_card=save_cards)
        results.append(res)
        if idx % 20 == 0 or idx == len(chars):
            rate = idx / max(0.01, time.time() - t0)
            issues = sum(1 for r in results if r["status"] == "ISSUE")
            print(f"  進捗: {idx}/{len(chars)} 字完了 ({rate:.1f} 字/秒, 問題検知: {issues} 字)")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Joyo Kanji Highlight Audit Tool")
    parser.add_argument("--grade", type=int, default=1, help="検査対象の学年 (1~6, 8)")
    parser.add_argument("--char", type=str, default=None, help="単一文字指定")
    parser.add_argument("--no-cards", action="store_true", help="個別タイル画像の保存をスキップ")
    args = parser.parse_args()

    if args.char:
        res = audit_single_kanji(args.char, grade=args.grade, save_card=not args.no_cards)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        results = audit_grade(args.grade, save_cards=not args.no_cards)
        issues = [r for r in results if r["status"] == "ISSUE"]
        print(f"\n✅ 小学{args.grade}年 検証完了: 全 {len(results)} 字中、正常 {len(results)-len(issues)} 字, 問題検知 {len(issues)} 字")


if __name__ == "__main__":
    main()
