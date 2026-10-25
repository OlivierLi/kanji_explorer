"""
scripts/fuzz/raster.py
Oracle B: 256x256 インクマスク・ラスタライゼーション検査モジュール。

fuzz.md 仕様:
- R: 全字インクマスク (TrueType中抜き・穴考慮 256x256 bool配列)
- L: レイヤーインクマスク (slice_path ∩ union(clip_rects))
- B1: インクシェア vs 画数シェア (|L|/|R| vs strokes(node)/strokes(root))
- B2: 兄弟要素インク重複 (|L_i ∩ L_j| / min(|L_i|, |L_j|))
- B3: 親インク被覆率 (∪ L_children が親の L の 80% 以上をカバー)
- B4: 空白ハイライト (画数 >= 1 なのに |L| <= 5 ピクセル)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any
import numpy as np
from PIL import Image, ImageDraw

import glyph_service
import ids_parser
from . import corpus


@dataclass
class RasterViolation:
    char: str
    oracle: str  # "B1", "B2", "B3", "B4"
    path: str
    component: str
    score: float
    message: str
    ink_share: float
    stroke_share: float
    overlap_ratio: float = 0.0
    coverage_ratio: float = 1.0
    layer_pixels: int = 0
    total_pixels: int = 0
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def rasterize_glyph_path(svg_path: str, size: int = 256) -> np.ndarray:
    """SVGパス文字列（Jigmo座標 0..1024, y上向き 880..0）から 256x256 の bool マスクを生成。"""
    if not svg_path:
        return np.zeros((size, size), dtype=bool)

    islands = glyph_service._extract_ink_islands(svg_path)
    if not islands:
        return np.zeros((size, size), dtype=bool)

    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    scale = size / 1024.0

    for isl in islands:
        subpaths = re.findall(r"M[^Z]+Z", isl["d"])
        if not subpaths:
            continue
        pts = glyph_service._parse_svg_path_points(subpaths[0])
        if len(pts) >= 3:
            draw.polygon([(p[0] * scale, (880.0 - p[1]) * scale) for p in pts], fill=255)
        for h in subpaths[1:]:
            h_pts = glyph_service._parse_svg_path_points(h)
            if len(h_pts) >= 3:
                draw.polygon([(p[0] * scale, (880.0 - p[1]) * scale) for p in h_pts], fill=0)

    return np.array(img) > 0


def create_clip_mask(clip_rects: list[list[float]], size: int = 256) -> np.ndarray:
    """正規化 clip_rects [[x, y, w, h], ...] から 256x256 のクリップ領域 bool マスクを生成。"""
    mask = np.zeros((size, size), dtype=bool)
    for cr in clip_rects:
        if not cr or len(cr) < 4:
            continue
        cx1 = max(0, min(size, int(cr[0] * size)))
        cy1 = max(0, min(size, int(cr[1] * size)))
        cx2 = max(0, min(size, int(np.ceil((cr[0] + cr[2]) * size))))
        cy2 = max(0, min(size, int(np.ceil((cr[1] + cr[3]) * size))))
        if cx2 > cx1 and cy2 > cy1:
            mask[cy1:cy2, cx1:cx2] = True
    return mask


def _find_1d_gaps(
    intervals: list[tuple[float, float]],
    min_gap: float = 0.004,
) -> list[tuple[float, float, float]]:
    """1次元区間群から空隙ギャップ (start, end, mid) のリストを抽出。"""
    if len(intervals) < 2:
        return []
    s = sorted(intervals)
    merged: list[list[float]] = []
    for a1, a2 in s:
        if not merged or a1 > merged[-1][1]:
            merged.append([a1, a2])
        else:
            merged[-1][1] = max(merged[-1][1], a2)
    gaps: list[tuple[float, float, float]] = []
    for i in range(len(merged) - 1):
        g1, g2 = merged[i][1], merged[i + 1][0]
        if g2 - g1 >= min_gap:
            gaps.append((g1, g2, (g1 + g2) / 2.0))
    return gaps


def compute_all_layer_masks(
    char: str,
    out_svg_data: dict[str, Any],
    size: int = 256,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """
    全字インクマスク R と、各レイヤー path に対応するハイライトインクマスク L の辞書を生成。
    """
    base_path = out_svg_data.get("base_path") or glyph_service.get_jigmo_path(char) or ""
    R = rasterize_glyph_path(base_path, size=size)

    layers = out_svg_data.get("component_layers", [])
    layer_masks: dict[str, np.ndarray] = {}

    for l in layers:
        l_path = l.get("path", "")
        clip_rects = l.get("clip_rects") or [l.get("bbox", [0.0, 0.0, 1.0, 1.0])]
        c_mask = create_clip_mask(clip_rects, size=size)

        slice_p = l.get("slice_path", "")
        needs_clip = l.get("needs_clip", True)

        if slice_p and slice_p != base_path:
            slice_mask = rasterize_glyph_path(slice_p, size=size)
            layer_masks[l_path] = (slice_mask & c_mask) if needs_clip else slice_mask
        else:
            layer_masks[l_path] = R & c_mask

    return R, layer_masks


def check_oracle_b(
    char: str,
    tree: dict[str, Any] | None = None,
    out_svg_data: dict[str, Any] | None = None,
    size: int = 256,
) -> list[RasterViolation]:
    """文字に対して Oracle B の全インク検査 (B1~B4) を実行します。"""
    violations: list[RasterViolation] = []

    if tree is None:
        try:
            tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
        except Exception:
            return violations

    if out_svg_data is None:
        try:
            out_svg_data = glyph_service.build_interactive_ids_svg(tree)
        except Exception as e:
            violations.append(
                RasterViolation(
                    char=char,
                    oracle="B0",
                    path="0",
                    component=char,
                    score=10.0,
                    message=f"SVGレイヤー生成例外: {e}",
                    ink_share=0.0,
                    stroke_share=1.0,
                )
            )
            return violations

    R, layer_masks = compute_all_layer_masks(char, out_svg_data, size=size)
    total_ink = int(np.sum(R))
    if total_ink <= 20:
        # グリフが存在しないか点のみ
        return violations

    total_strokes = corpus.get_stroke_count(char, default=corpus.estimate_node_strokes(tree))
    layers_by_path = {l.get("path"): l for l in out_svg_data.get("component_layers", [])}

    base_path = out_svg_data.get("base_path") or glyph_service.get_jigmo_path(char) or ""
    islands = glyph_service._extract_ink_islands(base_path) if base_path else []
    isl_masks = {
        i["id"]: rasterize_glyph_path(i["d"] + "".join(i.get("holes", [])), size=size)
        for i in islands
    }
    isl_pixels = {i["id"]: int(np.sum(isl_masks[i["id"]])) for i in islands}

    # 各レイヤーのインクピクセル数とシェア
    layer_pixels: dict[str, int] = {}
    for p, mask in layer_masks.items():
        layer_pixels[p] = int(np.sum(mask))

    # 構文木を走査して B1, B2, B3, B4, B7, B8 を検証
    def walk(node: dict[str, Any], depth: int):
        c_path = node.get("path", "0")
        c_char = node.get("char") or node.get("raw_char") or ""
        c_op = node.get("op")
        children = node.get("children", [])
        sig = corpus.get_node_signature(node, depth)

        if c_path != "0" and c_path in layer_masks:
            l_pix = layer_pixels[c_path]
            ink_share = l_pix / total_ink
            node_strokes = corpus.estimate_node_strokes(node)
            stroke_share = max(0.01, node_strokes / max(1, total_strokes))

            # -------------------------------------------------------------
            # B4: 空白ハイライト (|L| <= 5 ピクセル なのに画数 >= 1)
            # -------------------------------------------------------------
            if l_pix <= 5 and node_strokes >= 1:
                violations.append(
                    RasterViolation(
                        char=char,
                        oracle="B4",
                        path=c_path,
                        component=c_char,
                        score=8.0,
                        message=f"部品ハイライトのインクが空です (画数={node_strokes}, インク={l_pix}px)",
                        ink_share=round(ink_share, 4),
                        stroke_share=round(stroke_share, 4),
                        layer_pixels=l_pix,
                        total_pixels=total_ink,
                        signature=sig,
                    )
                )

            # -------------------------------------------------------------
            # B1: インクシェア vs 画数シェア
            # -------------------------------------------------------------
            # 過大インク判定: 1画・小部品なのに全体の 30% 以上のインクを占奪、または画数比の 3.5倍以上
            if ink_share > stroke_share * 3.5 and ink_share > 0.20:
                inflation = ink_share / stroke_share
                violations.append(
                    RasterViolation(
                        char=char,
                        oracle="B1",
                        path=c_path,
                        component=c_char,
                        score=round(inflation, 3),
                        message=f"部品のインク占有率が画数期待値に対して過大です (実測={ink_share*100:.1f}%, 期待={stroke_share*100:.1f}%, 倍率={inflation:.1f}x)",
                        ink_share=round(ink_share, 4),
                        stroke_share=round(stroke_share, 4),
                        layer_pixels=l_pix,
                        total_pixels=total_ink,
                        signature=sig,
                    )
                )

            # -------------------------------------------------------------
            # B7: インク過小ハイライト (Under-inking)
            # -------------------------------------------------------------
            if node_strokes >= 2 and l_pix > 5 and ink_share < (stroke_share / 2.5) and l_pix < (total_ink * 0.40):
                under_ratio = stroke_share / max(0.001, ink_share)
                if under_ratio >= 2.5:
                    violations.append(
                        RasterViolation(
                            char=char,
                            oracle="B7",
                            path=c_path,
                            component=c_char,
                            score=round(under_ratio, 3),
                            message=f"部品のインク占有率が画数期待値に対して過小です (実測={ink_share*100:.1f}%, 期待={stroke_share*100:.1f}%, 不足={under_ratio:.1f}x)",
                            ink_share=round(ink_share, 4),
                            stroke_share=round(stroke_share, 4),
                            layer_pixels=l_pix,
                            total_pixels=total_ink,
                            signature=sig,
                        )
                    )

            # -------------------------------------------------------------
            # B8: クリップ矩形による実インク直線切断 (Straight-edge truncation)
            # -------------------------------------------------------------
            layer_info = layers_by_path.get(c_path, {})
            if layer_info.get("needs_clip", True):
                L = layer_masks[c_path]
                clip_rects = layer_info.get("clip_rects") or [layer_info.get("bbox", [0.0, 0.0, 1.0, 1.0])]
                max_cut_len = 0
                for cr in clip_rects:
                    if len(cr) < 4:
                        continue
                    cx, cy, cw, ch = cr
                    # 水平エッジ
                    for ey in (cy, cy + ch):
                        py = int(round(ey * size))
                        if 2 <= py < size - 2:
                            px1 = max(0, int(cx * size))
                            px2 = min(size, int(np.ceil((cx + cw) * size)))
                            cut = R[py - 1, px1:px2] & R[py, px1:px2] & (L[py - 1, px1:px2] != L[py, px1:px2])
                            max_cut_len = max(max_cut_len, int(np.sum(cut)))
                    # 垂直エッジ
                    for ex in (cx, cx + cw):
                        px = int(round(ex * size))
                        if 2 <= px < size - 2:
                            py1 = max(0, int(cy * size))
                            py2 = min(size, int(np.ceil((cy + ch) * size)))
                            cut = R[py1:py2, px - 1] & R[py1:py2, px] & (L[py1:py2, px - 1] != L[py1:py2, px])
                            max_cut_len = max(max_cut_len, int(np.sum(cut)))

                # ⿻ (交差) 以外で、直線切断長が 14 ピクセル以上の実インク切断を検出
                if max_cut_len >= 14 and c_op not in ("⿻", "⿾", "⿿"):
                    score = round(max_cut_len / 4.0, 3)
                    violations.append(
                        RasterViolation(
                            char=char,
                            oracle="B8",
                            path=c_path,
                            component=c_char,
                            score=score,
                            message=f"クリップ矩形境界で実インクが直線的に切断されています (切断長={max_cut_len}px)",
                            ink_share=round(ink_share, 4),
                            stroke_share=round(stroke_share, 4),
                            layer_pixels=l_pix,
                            total_pixels=total_ink,
                            signature=sig,
                        )
                    )

        # -------------------------------------------------------------
        # B2: 兄弟要素インク重複
        # -------------------------------------------------------------
        if c_op and c_op not in ("⿻", "⿾", "⿿") and len(children) >= 2:
            child_paths = [c.get("path") for c in children if c.get("path") in layer_masks]
            for i in range(len(child_paths)):
                for j in range(i + 1, len(child_paths)):
                    p1, p2 = child_paths[i], child_paths[j]
                    m1, m2 = layer_masks[p1], layer_masks[p2]
                    overlap_pix = int(np.sum(m1 & m2))
                    min_pix = min(layer_pixels[p1], layer_pixels[p2])
                    if min_pix > 20:
                        overlap_ratio = overlap_pix / min_pix
                        if overlap_ratio > 0.30:
                            c1_name = layers_by_path.get(p1, {}).get("char", "")
                            c2_name = layers_by_path.get(p2, {}).get("char", "")
                            violations.append(
                                RasterViolation(
                                    char=char,
                                    oracle="B2",
                                    path=c_path,
                                    component=f"{c1_name}+{c2_name}",
                                    score=round(overlap_ratio * 6.0, 3),
                                    message=f"兄弟部品間でインクが過剰に重複点灯しています (重複率={overlap_ratio*100:.1f}%, 重複={overlap_pix}px)",
                                    ink_share=round(overlap_pix / total_ink, 4),
                                    stroke_share=0.0,
                                    overlap_ratio=round(overlap_ratio, 4),
                                    layer_pixels=overlap_pix,
                                    total_pixels=total_ink,
                                    signature=sig,
                                )
                            )

        # -------------------------------------------------------------
        # B3: 親インク被覆率 (子要素のインク和が親インクをカバーしているか)
        # -------------------------------------------------------------
        if children and c_path in layer_masks:
            child_paths = [c.get("path") for c in children if c.get("path") in layer_masks]
            if child_paths:
                union_child = np.zeros_like(R)
                for cp in child_paths:
                    union_child |= layer_masks[cp]
                parent_mask = layer_masks[c_path] if c_path != "0" else R
                p_pix = int(np.sum(parent_mask))
                if p_pix > 50:
                    cov_pix = int(np.sum(parent_mask & union_child))
                    cov_ratio = cov_pix / p_pix
                    # 70% 未満しかカバーできていない場合は筆画欠落バグの疑い
                    if cov_ratio < 0.70:
                        missing_ratio = 1.0 - cov_ratio
                        violations.append(
                            RasterViolation(
                                char=char,
                                oracle="B3",
                                path=c_path,
                                component=c_char,
                                score=round(missing_ratio * 5.0, 3),
                                message=f"子要素群による親インクの被覆率が低すぎます（筆画欠落の疑い: 被覆={cov_ratio*100:.1f}%, 未被覆={missing_ratio*100:.1f}%）",
                                ink_share=round(cov_ratio, 4),
                                stroke_share=1.0,
                                coverage_ratio=round(cov_ratio, 4),
                                layer_pixels=cov_pix,
                                total_pixels=p_pix,
                                signature=sig,
                            )
                        )

    # 構文木ノードのパス引きマップを構築
    node_by_path: dict[str, dict[str, Any]] = {}
    def collect_nodes(n: dict[str, Any]):
        node_by_path[n.get("path", "0")] = n
        for c in n.get("children", []):
            collect_nodes(c)
    collect_nodes(tree)

    walk(tree, 0)

    # -------------------------------------------------------------
    # B5: 近傍空隙が存在するインク島のクリップ切断 (Cut-through with an available gap)
    # -------------------------------------------------------------
    if len(islands) >= 2:
        for layer in out_svg_data.get("component_layers", []):
            l_path = layer.get("path", "")
            if l_path == "0" or not layer.get("needs_clip", True):
                continue
            if layer.get("char") in ("囗", "门", "門", "冂") or layer.get("role_label") in ("外囲", "上囲", "下囲", "左囲"):
                continue
            clip_rects = layer.get("clip_rects") or [layer.get("bbox", [0.0, 0.0, 1.0, 1.0])]
            c_mask = create_clip_mask(clip_rects, size=size)
            c_char = layer.get("char", "")
            node_strokes = corpus.get_stroke_count(c_char, default=1)
            stroke_share = max(0.01, node_strokes / max(1, total_strokes))

            parent_p = l_path.rsplit(".", 1)[0] if "." in l_path else "0"
            parent_node = node_by_path.get(parent_p)
            parent_bbox = parent_node.get("bbox", [0.0, 0.0, 1.0, 1.0]) if parent_node else [0.0, 0.0, 1.0, 1.0]
            if parent_p == "0":
                py_start = 0.02
                py_end = 0.98
                px_start = 0.02
                px_end = 0.98
            else:
                py_start = parent_bbox[1] + 0.015
                py_end = parent_bbox[1] + parent_bbox[3] - 0.015
                px_start = parent_bbox[0] + 0.015
                px_end = parent_bbox[0] + parent_bbox[2] - 0.015

            # 包囲構造の内側要素（c1）は外枠側の内部空隙へ侵食しないよう親探索範囲を制限
            if parent_node and parent_node.get("op") in ("⿸", "⿹", "⿺", "⿵", "⿶", "⿷", "⿴") and l_path.endswith(".1"):
                l_bbox = layer.get("bbox", [0.0, 0.0, 1.0, 1.0])
                py_start = max(py_start, l_bbox[1] - 0.02)
                py_end = min(py_end, l_bbox[1] + l_bbox[3] + 0.02)
                px_start = max(px_start, l_bbox[0] - 0.02)
                px_end = min(px_end, l_bbox[0] + l_bbox[2] + 0.02)

            for cr in clip_rects:
                if len(cr) < 4:
                    continue
                cx, cy, cw, ch = cr
                col_x1 = max(0, int(cx * size))
                col_x2 = min(size, int((cx + cw) * size))
                # 水平エッジの検査
                for ey in (cy, cy + ch):
                    if ey <= 0.02 or ey >= 0.98:
                        continue
                    py_cut = int(round(ey * size))
                    for isl in islands:
                        if isl["y1"] < ey - 0.02 and isl["y2"] > ey + 0.02:
                            if min(isl["x2"], cx + cw) - max(isl["x1"], cx) < 0.04:
                                continue
                            im = isl_masks.get(isl["id"])
                            if im is None:
                                continue
                            if not np.any(im[max(0, py_cut - 1):min(size, py_cut + 2), col_x1:col_x2]):
                                continue
                            # レイヤーのクリップマスクがエッジの両側でインクを被覆している場合、内部の結合シームであるため切断とみなさない
                            if 0 < py_cut < size - 1:
                                if np.any(im[py_cut - 1, col_x1:col_x2] & c_mask[py_cut - 1, col_x1:col_x2]) and \
                                   np.any(im[py_cut + 1, col_x1:col_x2] & c_mask[py_cut + 1, col_x1:col_x2]):
                                    continue
                            col_islands = [
                                i for i in islands
                                if min(i["x2"], cx + cw) - max(i["x1"], cx) >= 0.04
                            ]
                            y_gaps = _find_1d_gaps([(i["y1"], i["y2"]) for i in col_islands], min_gap=0.004)
                            nearby_gaps = [
                                g for g in y_gaps
                                if abs(g[2] - ey) <= 0.15 and (py_start <= g[2] <= py_end)
                                and (g[2] >= cy + 0.01 if ey > cy + 0.01 else g[2] <= cy + ch - 0.01)
                            ]
                            if nearby_gaps:
                                best_gap = min(nearby_gaps, key=lambda g: abs(g[2] - ey))
                                dist_to_gap = abs(best_gap[2] - ey)
                                if dist_to_gap > 0.012:
                                    ipix = isl_pixels.get(isl["id"], 0)
                                    if ipix >= 40:
                                        cut_above = int(np.sum(im[:py_cut, col_x1:col_x2]))
                                        cut_below = int(np.sum(im[py_cut:, col_x1:col_x2]))
                                        cut_pix = min(cut_above, cut_below)
                                        if cut_pix >= 25 and (cut_pix / max(1, ipix)) >= 0.12:
                                            cut_frac = cut_pix / max(1, ipix)
                                            score = round(cut_frac * (1.0 + dist_to_gap / 0.05) * 6.0, 3)
                                            violations.append(
                                                RasterViolation(
                                                    char=char,
                                                    oracle="B5",
                                                    path=l_path,
                                                    component=c_char,
                                                    score=score,
                                                    message=f"近傍にインク空隙が存在するにもかかわらずクリップ境界がインク島を切断しています (ギャップ距離={dist_to_gap:.3f}, 切断比率={cut_frac*100:.1f}%, 切断={cut_pix}px)",
                                                    ink_share=round(cut_pix / total_ink, 4),
                                                    stroke_share=round(stroke_share, 4),
                                                    layer_pixels=cut_pix,
                                                    total_pixels=total_ink,
                                                    signature=layer.get("signature", ""),
                                                )
                                            )
                # 垂直エッジの検査
                row_y1 = max(0, int(cy * size))
                row_y2 = min(size, int((cy + ch) * size))
                for ex in (cx, cx + cw):
                    if ex <= 0.02 or ex >= 0.98:
                        continue
                    px_cut = int(round(ex * size))
                    for isl in islands:
                        if isl["x1"] < ex - 0.02 and isl["x2"] > ex + 0.02:
                            if min(isl["y2"], cy + ch) - max(isl["y1"], cy) < 0.04:
                                continue
                            im = isl_masks.get(isl["id"])
                            if im is None:
                                continue
                            if not np.any(im[row_y1:row_y2, max(0, px_cut - 1):min(size, px_cut + 2)]):
                                continue
                            # レイヤーのクリップマスクがエッジの両側でインクを被覆している場合、内部の結合シームであるため切断とみなさない
                            if 0 < px_cut < size - 1:
                                if np.any(im[row_y1:row_y2, px_cut - 1] & c_mask[row_y1:row_y2, px_cut - 1]) and \
                                   np.any(im[row_y1:row_y2, px_cut + 1] & c_mask[row_y1:row_y2, px_cut + 1]):
                                    continue
                            row_islands = [
                                i for i in islands
                                if min(i["y2"], cy + ch) - max(i["y1"], cy) >= 0.04
                            ]
                            x_gaps = _find_1d_gaps([(i["x1"], i["x2"]) for i in row_islands], min_gap=0.004)
                            nearby_gaps = [
                                g for g in x_gaps
                                if abs(g[2] - ex) <= 0.15 and (px_start <= g[2] <= px_end)
                                and (g[2] >= cx + 0.01 if ex > cx + 0.01 else g[2] <= cx + cw - 0.01)
                            ]
                            if nearby_gaps:
                                best_gap = min(nearby_gaps, key=lambda g: abs(g[2] - ex))
                                dist_to_gap = abs(best_gap[2] - ex)
                                if dist_to_gap > 0.012:
                                    ipix = isl_pixels.get(isl["id"], 0)
                                    if ipix >= 40:
                                        cut_left = int(np.sum(im[row_y1:row_y2, :px_cut]))
                                        cut_right = int(np.sum(im[row_y1:row_y2, px_cut:]))
                                        cut_pix = min(cut_left, cut_right)
                                        if cut_pix >= 25 and (cut_pix / max(1, ipix)) >= 0.12:
                                            cut_frac = cut_pix / max(1, ipix)
                                            score = round(cut_frac * (1.0 + dist_to_gap / 0.05) * 6.0, 3)
                                            violations.append(
                                                RasterViolation(
                                                    char=char,
                                                    oracle="B5",
                                                    path=l_path,
                                                    component=c_char,
                                                    score=score,
                                                    message=f"近傍にインク空隙が存在するにもかかわらずクリップ境界がインク島を切断しています (ギャップ距離={dist_to_gap:.3f}, 切断比率={cut_frac*100:.1f}%, 切断={cut_pix}px)",
                                                    ink_share=round(cut_pix / total_ink, 4),
                                                    stroke_share=round(stroke_share, 4),
                                                    layer_pixels=cut_pix,
                                                    total_pixels=total_ink,
                                                    signature=layer.get("signature", ""),
                                                )
                                            )

    # -------------------------------------------------------------
    # B6: 単一インク島の複数葉ノード分割 (Island fragmentation)
    # -------------------------------------------------------------
    if len(islands) >= 2:
        leaf_nodes: list[dict[str, Any]] = []
        def get_all_leaves(n: dict[str, Any], under_overlay: bool = False):
            is_ov = under_overlay or (n.get("op") in ("⿻", "⿾", "⿿"))
            kids = n.get("children", [])
            if not kids:
                leaf_nodes.append({"node": n, "under_overlay": is_ov})
            for ch in kids:
                get_all_leaves(ch, is_ov)
        get_all_leaves(tree)

        for isl in islands:
            iid = isl["id"]
            ipix = isl_pixels.get(iid, 0)
            if ipix < 60:
                continue
            im = isl_masks[iid]
            lighting_leaves: list[tuple[str, str, int, float]] = []
            has_overlay_leaf = False
            for lf_info in leaf_nodes:
                lf = lf_info["node"]
                lp = lf.get("path")
                if lp in layer_masks:
                    ov = int(np.sum(im & layer_masks[lp]))
                    if ov >= ipix * 0.08:
                        if lf_info["under_overlay"]:
                            has_overlay_leaf = True
                        lighting_leaves.append((lp, lf.get("char", ""), ov, ov / ipix, lf))

            if len(lighting_leaves) >= 2 and not has_overlay_leaf:
                has_shared_by_design = all(item[4].get("_has_shared_island") for item in lighting_leaves)
                if not has_shared_by_design:
                    max_share = max(x[3] for x in lighting_leaves)
                    if max_share < 0.90:
                        score = round(len(lighting_leaves) * (1.0 - max_share) * 6.0, 3)
                        comp_names = "+".join(x[1] for x in lighting_leaves)
                        violations.append(
                            RasterViolation(
                                char=char,
                                oracle="B6",
                                path=lighting_leaves[0][0],
                                component=comp_names,
                                score=score,
                                message=f"単一インク島が {len(lighting_leaves)} 個の葉部品 ({comp_names}) に細片化されています (最大占有率={max_share*100:.1f}%)",
                                ink_share=round(ipix / total_ink, 4),
                                stroke_share=0.0,
                                layer_pixels=ipix,
                                total_pixels=total_ink,
                            )
                        )

    return violations
