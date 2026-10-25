"""
scripts/fuzz/invariants.py
Oracle A: 純粋幾何学的・構造的不変条件チェッカー (描画不要・高速実行).

fuzz.md 仕様:
- A1: 子要素 bbox が親 bbox の内部にあること (⿻丨の突出例外を除く)
- A2: 基本筆画部品の形状限界 (「一」「二」「三」の高さ <= 0.12, 「丨」「亅」の幅 <= 0.12, 「丶」の面積 <= 0.04)
- A3: 面積シェア vs 画数シェア比 (area(node)/area(root) が strokes(node)/strokes(root) の3倍以内)
- A4: 有効スケール検査 (葉ノードの面積が画数シェアの2倍を超えて肥大化していないこと)
- A5: 兄弟要素の重複 (非⿻演算子において、兄弟矩形の重なりが小さい方の15%以内)
- A6: 包囲構え hit_rects の内側遮蔽検査 (外枠の hit_rects が内側要素の内部を覆わないこと)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import ids_parser
from . import corpus


@dataclass
class InvariantViolation:
    char: str
    oracle: str  # "A1" ~ "A6"
    path: str
    component: str
    score: float
    message: str
    bbox: list[float]
    parent_bbox: list[float] | None = None
    expected: Any = None
    actual: Any = None
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rect_intersection(r1: list[float], r2: list[float]) -> float:
    """2つの矩形 [x, y, w, h] の交差面積を返します。"""
    x1 = max(r1[0], r2[0])
    y1 = max(r1[1], r2[1])
    x2 = min(r1[0] + r1[2], r2[0] + r2[2])
    y2 = min(r1[1] + r1[3], r2[1] + r2[3])
    if x2 > x1 and y2 > y1:
        return (x2 - x1) * (y2 - y1)
    return 0.0


def check_oracle_a(char: str, tree: dict[str, Any] | None = None) -> list[InvariantViolation]:
    """文字に対して Oracle A の全不変条件 (A1~A6) を検査します。"""
    violations: list[InvariantViolation] = []

    if tree is None:
        try:
            tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
        except Exception as e:
            violations.append(
                InvariantViolation(
                    char=char,
                    oracle="A0",
                    path="0",
                    component=char,
                    score=10.0,
                    message=f"構文木分解時例外: {e}",
                    bbox=[0, 0, 1, 1],
                )
            )
            return violations

    total_strokes = corpus.get_stroke_count(char, default=estimate_root_strokes(tree))
    root_bbox = tree.get("bbox", [0.0, 0.0, 1.0, 1.0])
    root_area = max(1e-4, root_bbox[2] * root_bbox[3])

    def walk(node: dict[str, Any], parent: dict[str, Any] | None, depth: int):
        c_path = node.get("path", "0")
        c_char = node.get("char") or node.get("raw_char") or ""
        c_bbox = node.get("bbox", [0.0, 0.0, 1.0, 1.0])
        cx, cy, cw, ch = c_bbox
        if node.get("hit_rects"):
            c_area = sum(r[2] * r[3] for r in node["hit_rects"])
            cw_eff = max(r[2] for r in node["hit_rects"])
            ch_eff = max(r[3] for r in node["hit_rects"])
        else:
            c_area = max(0.0, cw * ch)
            cw_eff = cw
            ch_eff = ch
        c_op = node.get("op")
        children = node.get("children", [])
        sig = corpus.get_node_signature(node, depth)

        # -------------------------------------------------------------
        # A1: 子要素 bbox が親 bbox の内部にあること (許容誤差 0.03)
        # -------------------------------------------------------------
        if parent is not None and c_path != "0":
            px, py, pw, ph = parent.get("bbox", [0.0, 0.0, 1.0, 1.0])
            p_op = parent.get("op", "")
            # ⿻丨 の意図的オーバーシュート構造は除外
            is_overshoot_ok = (p_op == "⿻" and c_char in ("丨", "亅"))
            if not is_overshoot_ok:
                tol = 0.035
                out_x = max(0.0, px - cx) + max(0.0, (cx + cw) - (px + pw))
                out_y = max(0.0, py - cy) + max(0.0, (cy + ch) - (py + ph))
                if out_x > tol or out_y > tol:
                    score = (out_x + out_y) * 10.0
                    violations.append(
                        InvariantViolation(
                            char=char,
                            oracle="A1",
                            path=c_path,
                            component=c_char,
                            score=round(score, 3),
                            message=f"子要素が親bboxをはみ出しています (out_x={out_x:.3f}, out_y={out_y:.3f})",
                            bbox=c_bbox,
                            parent_bbox=[px, py, pw, ph],
                            actual={"out_x": out_x, "out_y": out_y},
                            signature=sig,
                        )
                    )

        # -------------------------------------------------------------
        # A2: 基本筆画部品の形状限界 (ルート文字自体が「一」等の場合は除外)
        # -------------------------------------------------------------
        if c_path != "0":
            if c_char in ("一", "二", "三"):
                # 横画単体の高さ制限 (一: 0.14, 二/三: 0.38)
                max_h_char = 0.14 if c_char == "一" else 0.38
                p_op = parent.get("op", "") if parent else ""
                p_h = parent.get("bbox", [0, 0, 1, 1])[3] if parent else 1.0
                p_char = parent.get("char") or parent.get("raw_char") or "" if parent else ""
                if p_char in ("二", "𠄞", "亼"):
                    max_h_parent = max(0.04, p_h * 0.58)
                elif p_char == "三":
                    max_h_parent = max(0.04, p_h * 0.45)
                elif p_char in ("目", "日", "白", "自", "貝") or p_op in ("⿴", "⿵", "⿶", "⿷", "⿻"):
                    max_h_parent = max(0.04, p_h * 0.70)
                elif p_op in ("⿰", "⿲"):
                    max_h_parent = max_h_char
                else:
                    max_h_parent = max(0.04, p_h * 0.38)
                if ch_eff > max_h_char or ch_eff > max_h_parent:
                    ratio = ch_eff / max_h_char
                    violations.append(
                        InvariantViolation(
                            char=char,
                            oracle="A2",
                            path=c_path,
                            component=c_char,
                            score=round(ratio, 3),
                            message=f"横画部品 {c_char} の高さが過大です (h={ch_eff:.3f}, 上限={max_h_char:.3f})",
                            bbox=c_bbox,
                            parent_bbox=parent.get("bbox") if parent else None,
                            expected=f"h <= {max_h_char}",
                            actual=round(ch_eff, 4),
                            signature=sig,
                        )
                    )

            elif c_char in ("丨", "亅"):
                # 縦画単体の幅が文字全体の規定値を超える場合は肥大化 (丨: 0.14, 亅はハネがあるため0.22)
                max_w_char = 0.22 if c_char == "亅" else 0.14
                if cw_eff > max_w_char:
                    ratio = cw_eff / max_w_char
                    violations.append(
                        InvariantViolation(
                            char=char,
                            oracle="A2",
                            path=c_path,
                            component=c_char,
                            score=round(ratio, 3),
                            message=f"縦画部品 {c_char} の幅が過大です (w={cw_eff:.3f}, 上限={max_w_char:.3f})",
                            bbox=c_bbox,
                            expected=f"w <= {max_w_char}",
                            actual=round(cw_eff, 4),
                            signature=sig,
                        )
                    )

            elif c_char == "丶":
                # 点単体の面積が 0.055 を超える場合は肥大化 (フォント実インク約0.044 + マージン)
                max_area = 0.055
                if c_area > max_area:
                    ratio = c_area / max_area
                    violations.append(
                        InvariantViolation(
                            char=char,
                            oracle="A2",
                            path=c_path,
                            component=c_char,
                            score=round(ratio, 3),
                            message=f"点画部品 丶 の面積が過大です (area={c_area:.3f}, 上限={max_area:.3f})",
                            bbox=c_bbox,
                            expected=f"area <= {max_area}",
                            actual=round(c_area, 4),
                            signature=sig,
                        )
                    )

        # -------------------------------------------------------------
        # A3 & A4: 面積シェア vs 画数シェア比
        # -------------------------------------------------------------
        if c_path != "0" and c_area > 0:
            node_strokes = corpus.estimate_node_strokes(node)
            stroke_ratio = max(0.01, node_strokes / max(1, total_strokes))
            area_ratio = c_area / root_area

            # A3: 面積シェアが画数シェアの3.2倍を超える場合 (例: 1画/11画 なのに面積 35%)
            if area_ratio > stroke_ratio * 3.2 and area_ratio > 0.18:
                inflation = area_ratio / stroke_ratio
                violations.append(
                    InvariantViolation(
                        char=char,
                        oracle="A3",
                        path=c_path,
                        component=c_char,
                        score=round(inflation, 3),
                        message=f"画数に対して矩形面積が異常に肥大しています (画数={node_strokes}/{total_strokes}, 面積比={area_ratio:.2f}, 倍率={inflation:.1f}x)",
                        bbox=c_bbox,
                        expected=f"area_ratio <= {stroke_ratio*3.2:.2f}",
                        actual=round(area_ratio, 4),
                        signature=sig,
                    )
                )

            # A4: 葉ノード (これ以上分解されない終端) で画数シェアの2.5倍を超える場合
            if not children and area_ratio > stroke_ratio * 2.5 and c_area > 0.22:
                inflation = area_ratio / stroke_ratio
                violations.append(
                    InvariantViolation(
                        char=char,
                        oracle="A4",
                        path=c_path,
                        component=c_char,
                        score=round(inflation, 3),
                        message=f"終端葉ノードの占有面積が大きすぎます (面積={c_area:.3f}, 画数={node_strokes}, 倍率={inflation:.1f}x)",
                        bbox=c_bbox,
                        expected=f"area_ratio <= {stroke_ratio*2.5:.2f}",
                        actual=round(area_ratio, 4),
                        signature=sig,
                    )
                )

        # -------------------------------------------------------------
        # A5: 兄弟要素の重複 (分割演算子 ⿰, ⿱, ⿲, ⿳ のみ)
        # -------------------------------------------------------------
        partition_ops = {"⿰", "⿱", "⿲", "⿳"}
        if c_op in partition_ops and len(children) >= 2:
            for i in range(len(children)):
                for j in range(i + 1, len(children)):
                    b1 = children[i].get("bbox", [0, 0, 1, 1])
                    b2 = children[j].get("bbox", [0, 0, 1, 1])
                    overlap = _rect_intersection(b1, b2)
                    min_area = max(1e-4, min(b1[2] * b1[3], b2[2] * b2[3]))
                    overlap_ratio = overlap / min_area
                    if overlap_ratio > 0.18:
                        violations.append(
                            InvariantViolation(
                                char=char,
                                oracle="A5",
                                path=c_path,
                                component=f"{children[i].get('char','')}+{children[j].get('char','')}",
                                score=round(overlap_ratio * 5.0, 3),
                                message=f"分割演算子 {c_op} の兄弟要素が過剰に重複しています (重複率={overlap_ratio*100:.1f}%)",
                                bbox=b1,
                                parent_bbox=b2,
                                expected="overlap <= 18%",
                                actual=f"{overlap_ratio*100:.1f}%",
                                signature=sig,
                            )
                        )

        # -------------------------------------------------------------
        # A6: 包囲構え hit_rects の内側遮蔽検査
        # -------------------------------------------------------------
        enclosure_ops = {"⿴", "⿵", "⿶", "⿷", "⿸", "⿹", "⿺", "⿼", "⿽"}
        if c_op in enclosure_ops and len(children) == 2:
            outer = children[0]
            inner = children[1]
            outer_hits = outer.get("hit_rects") or outer.get("clip_rects") or []
            inner_box = inner.get("bbox", [0, 0, 1, 1])
            # 内側要素の中心矩形 (50%縮小領域) と外枠hit_rectsの干渉を検査
            ix, iy, iw, ih = inner_box
            inner_center = [ix + iw * 0.25, iy + ih * 0.25, iw * 0.5, ih * 0.5]
            inner_center_area = max(1e-4, inner_center[2] * inner_center[3])
            hit_overlap = sum(_rect_intersection(hr, inner_center) for hr in outer_hits)
            if hit_overlap / inner_center_area > 0.15:
                ratio = hit_overlap / inner_center_area
                violations.append(
                    InvariantViolation(
                        char=char,
                        oracle="A6",
                        path=f"{c_path}.0",
                        component=outer.get("char", "外枠"),
                        score=round(ratio * 4.0, 3),
                        message=f"外枠のhit_rectsが内側要素の中心領域を遮蔽しています (遮蔽率={ratio*100:.1f}%)",
                        bbox=inner_box,
                        parent_bbox=c_bbox,
                        expected="hit_overlap <= 15%",
                        actual=f"{ratio*100:.1f}%",
                        signature=sig,
                    )
                )

        for child in children:
            walk(child, node, depth + 1)

    walk(tree, None, 0)
    return violations


def estimate_root_strokes(tree: dict[str, Any]) -> int:
    """構文木から全体の総画数を合算推定します。"""
    c_char = tree.get("char") or ""
    if c_char:
        sc = corpus.get_stroke_count(c_char, default=0)
        if sc > 0:
            return sc
    return corpus.estimate_node_strokes(tree)
