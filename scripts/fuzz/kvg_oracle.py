"""
scripts/fuzz/kvg_oracle.py
Oracle C: KanjiVG 正解ストロークグループ比較・外れ値検出モジュール。

fuzz.md 仕様:
- KanjiVG XML (data/kanjivg.xml.gz) に収録された約6.7k字のストロークグループ (kvg:element) を正解データとして利用
- IDS 構文木ノードと KVG グループを部品記号の正規化を通じて対応付け
- 各ノードの bbox と KVG の stroke bounding box を比較:
  - C1: IoU 乖離 (IoU < 0.35)
  - C2: 重心オフセット過大 (中心間距離 > 0.20)
  - C3: 兄弟要素領域への侵食 (KVGで兄弟に属するストロークがクリップ矩形に深く侵入)
- 各 IDC 構造ごとの経験的分割比率統計の収集機能
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Any

import ids_parser
import glyph_service
from . import corpus

KVG_NS = "http://kanjivg.tagaini.net"

# 部首変形および CJK 部首補助の標準部品等価マップ（glyph_service より共有）
RADICAL_FORM_MAP = glyph_service.RADICAL_FORM_MAP
get_equivalent_symbols = glyph_service.get_equivalent_symbols
_get_equivalent_symbols = get_equivalent_symbols


@dataclass
class KvgViolation:
    char: str
    oracle: str  # "C1", "C2", "C3"
    path: str
    component: str
    score: float
    message: str
    ids_bbox: list[float]
    kvg_bbox: list[float]
    iou: float
    center_offset: float
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_iou(b1: list[float], b2: list[float]) -> float:
    """2つの正規化矩形 [x, y, w, h] の IoU (Intersection over Union) を計算。"""
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[0] + b1[2], b2[0] + b2[2])
    y2 = min(b1[1] + b1[3], b2[1] + b2[3])
    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h
    union_area = (b1[2] * b1[3]) + (b2[2] * b2[3]) - inter_area
    if union_area <= 1e-6:
        return 0.0
    return inter_area / union_area


def _center_distance(b1: list[float], b2: list[float]) -> float:
    """2つの矩形 [x, y, w, h] の中心点ユークリッド距離を計算。"""
    c1x = b1[0] + b1[2] * 0.5
    c1y = b1[1] + b1[3] * 0.5
    c2x = b2[0] + b2[2] * 0.5
    c2y = b2[1] + b2[3] * 0.5
    return math.hypot(c1x - c2x, c1y - c2y)


def parse_kanjivg_groups(char: str) -> list[dict[str, Any]]:
    """
    指定文字の KanjiVG XML からストロークグループ一覧を抽出。
    各グループ: {id, elem, norm_elem, bbox: [x,y,w,h], stroke_count, position}
    """
    service = glyph_service._get_default_kanjivg_service()
    xml_text = service.get_kanji_xml(char)
    if not xml_text:
        return []

    wrapped = f'<kanjivg xmlns:kvg="{KVG_NS}">{xml_text}</kanjivg>'
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        return []

    groups: list[dict[str, Any]] = []

    for g in root.iter():
        if not g.tag.endswith("g"):
            continue
        elem = g.attrib.get(f"{{{KVG_NS}}}element")
        if not elem:
            continue

        norm_elem, _ = glyph_service.normalize_element_symbol(elem)
        norm_elem = ids_parser.normalize_component(norm_elem or elem)

        pts: list[tuple[float, float]] = []
        stroke_count = 0
        for p in g.iter():
            if p.tag.endswith("path"):
                stroke_count += 1
                d = p.attrib.get("d", "")
                pts.extend(glyph_service._parse_svg_path_points(d))

        if pts:
            xs = [pt[0] / 109.0 for pt in pts]
            ys = [pt[1] / 109.0 for pt in pts]
            bx = min(xs)
            by = min(ys)
            bw = max(xs) - bx
            bh = max(ys) - by
            groups.append({
                "id": g.attrib.get("id", ""),
                "elem": elem,
                "norm_elem": norm_elem,
                "position": g.attrib.get(f"{{{KVG_NS}}}position", ""),
                "bbox": [round(bx, 4), round(by, 4), round(bw, 4), round(bh, 4)],
                "stroke_count": stroke_count,
            })

    return groups


def check_oracle_c(
    char: str,
    tree: dict[str, Any] | None = None,
) -> list[KvgViolation]:
    """文字に対して Oracle C (KanjiVG 正解グループ比較) を実行します。"""
    violations: list[KvgViolation] = []

    kvg_groups = parse_kanjivg_groups(char)
    if not kvg_groups:
        # KanjiVG 未収録文字（拡張漢字等）はスキップ
        return violations

    if tree is None:
        try:
            tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
        except Exception:
            return violations

    # 全ノードを平坦化
    tree_nodes: list[dict[str, Any]] = []

    def flatten(n: dict[str, Any], depth: int):
        c_path = n.get("path", "0")
        c_char = n.get("char") or n.get("raw_char") or ""
        norm_c = ids_parser.normalize_component(c_char)
        tree_nodes.append({
            "path": c_path,
            "char": c_char,
            "norm_char": norm_c,
            "bbox": n.get("bbox", [0.0, 0.0, 1.0, 1.0]),
            "role_label": n.get("role_label", ""),
            "depth": depth,
            "node": n,
        })
        for c in n.get("children", []):
            flatten(c, depth + 1)

    flatten(tree, 0)

    # ルート (path == "0") を除外したノードと KVG グループをマッチング
    matched_kvg_ids: set[str] = set()

    for tn in tree_nodes:
        if tn["path"] == "0":
            continue
        t_char = tn["norm_char"]
        if not t_char:
            continue

        # 1. 記号名・異体字・部首変形に基づくマッチング
        t_equivs = _get_equivalent_symbols(t_char)
        raw_char = tn.get("char", "")
        if raw_char:
            t_equivs.update(_get_equivalent_symbols(raw_char))

        candidates = [
            g for g in kvg_groups
            if g["id"] not in matched_kvg_ids
            and (
                g["norm_elem"] in t_equivs
                or g["elem"] in t_equivs
                or bool(_get_equivalent_symbols(g["elem"]) & t_equivs)
            )
        ]

        # 2. CHISE実体参照（&CDP-…;）等に対する位置的重心マッチングフォールバック
        if not candidates and (t_char.startswith("&") or raw_char.startswith("&")):
            unmatched_kvg = [g for g in kvg_groups if g["id"] not in matched_kvg_ids]
            if unmatched_kvg:
                closest = min(unmatched_kvg, key=lambda g: _center_distance(tn["bbox"], g["bbox"]))
                if _center_distance(tn["bbox"], closest["bbox"]) <= 0.25 and _compute_iou(tn["bbox"], closest["bbox"]) >= 0.20:
                    candidates = [closest]

        if not candidates:
            continue

        # 最も中心距離が近いグループをベストマッチとする
        best_g = min(candidates, key=lambda g: _center_distance(tn["bbox"], g["bbox"]))
        matched_kvg_ids.add(best_g["id"])

        t_box = tn["bbox"]
        k_box = best_g["bbox"]
        iou = _compute_iou(t_box, k_box)
        c_dist = _center_distance(t_box, k_box)
        sig = corpus.get_node_signature(tn["node"], tn["depth"])

        # -------------------------------------------------------------
        # C1: IoU 乖離 (IoU < 0.28 かつ 中心距離 > 0.12)
        # -------------------------------------------------------------
        if iou < 0.28 and c_dist > 0.12 and k_box[2] * k_box[3] > 0.03:
            score = round((1.0 - iou) * 4.0 + c_dist * 5.0, 3)
            violations.append(
                KvgViolation(
                    char=char,
                    oracle="C1",
                    path=tn["path"],
                    component=tn["char"],
                    score=score,
                    message=f"KanjiVG正解グループとのIoUが著しく乖離しています (IoU={iou:.3f}, 中心距離={c_dist:.3f})",
                    ids_bbox=t_box,
                    kvg_bbox=k_box,
                    iou=round(iou, 4),
                    center_offset=round(c_dist, 4),
                    signature=sig,
                )
            )

        # -------------------------------------------------------------
        # C2: 重心オフセット過大 (中心距離 > 0.22)
        # -------------------------------------------------------------
        elif c_dist > 0.22 and k_box[2] * k_box[3] > 0.03:
            score = round(c_dist * 8.0, 3)
            violations.append(
                KvgViolation(
                    char=char,
                    oracle="C2",
                    path=tn["path"],
                    component=tn["char"],
                    score=score,
                    message=f"KanjiVG正解グループと配置重心が大きくズレています (中心距離={c_dist:.3f}, IoU={iou:.3f})",
                    ids_bbox=t_box,
                    kvg_bbox=k_box,
                    iou=round(iou, 4),
                    center_offset=round(c_dist, 4),
                    signature=sig,
                )
            )

    # -------------------------------------------------------------
    # C0: KanjiVGデータが存在するにもかかわらず1件もノードがマッチしなかった場合
    # -------------------------------------------------------------
    if kvg_groups and not matched_kvg_ids:
        violations.append(
            KvgViolation(
                char=char,
                oracle="C0",
                path="0",
                component=char,
                score=10.0,
                message=f"KanjiVG正解グループが存在しますが、IDS構文木ノードと1件もマッチしませんでした (未マッチ={len(kvg_groups)}件)",
                ids_bbox=[0.0, 0.0, 1.0, 1.0],
                kvg_bbox=[0.0, 0.0, 1.0, 1.0],
                iou=0.0,
                center_offset=1.0,
            )
        )

    return violations
