"""大規模漢字コーパスに対する幾何・不変条件（Invariants）網羅的ストレステスト."""

import pytest

import ids_parser
import glyph_service


CORPUS = [
    # 常用漢字・基本構造
    "一", "二", "三", "十", "木", "林", "森", "日", "月", "明", "晶",
    "品", "川", "洲", "山", "岩", "水", "氷", "火", "炎", "土", "金",
    "言", "語", "話", "読", "書", "学", "校", "生", "先", "人", "休",
    # 左右・三分割構造
    "樹", "測", "湖", "億", "働", "織", "謝", "街", "斑", "辯", "瀬",
    # 上下・三段構造
    "筒", "墓", "塞", "基", "堂", "幕", "暮", "意", "急", "想", "慈",
    "当", "光", "尚", "巣", "単", "蛍", "常", "党", "掌", "賞",
    # 包囲・垂れ・繞・交差構造
    "国", "団", "園", "回", "因", "困", "問", "間", "開", "閉", "閣",
    "同", "岡", "風", "凡", "凶", "函", "区", "医", "匠",
    "広", "店", "病", "痛", "厳", "原", "厚", "歴", "屋", "房",
    "近", "進", "道", "通", "連", "迎", "返", "追", "起", "超", "越",
    "司", "句", "包", "気", "式", "武",
    # 接触・微細部品
    "夢", "停", "厎", "嵈", "爚", "蚕", "東", "重", "車", "軍",
    # 稠密・超複雑漢字
    "鬱", "鑑", "嚢", "驚", "襲", "鸞", "驫", "贏", "薔", "薇", "竈", "蠱", "麟", "饗", "籤",
    # 国字・特殊字形
    "辻", "笹", "榊", "畠", "峠", "凪", "凧", "雫",
]


class TestCorpusInvariants:
    """全コーパス文字に対する普遍的不変条件（Invariants）検証."""

    @pytest.mark.parametrize("char", CORPUS)
    def test_character_invariants(self, char):
        ids = (
            ids_parser.get_character_ids(char)
            or ids_parser.COMPONENT_SUBDECOMPOSITIONS.get(char)
            or char
        )
        tree = ids_parser.decompose_character(
            ids, max_depth=6, use_atomic=True, compute_bbox=True
        )
        tree["char"] = char

        out = glyph_service.build_interactive_ids_svg(tree)
        base_path = out.get("base_path")
        layers = out.get("component_layers", [])

        # 単一筆画等を除く複合字はレイヤーを持つこと
        if tree.get("children"):
            assert len(layers) >= 1, f"文字 '{char}' のコンポーネントレイヤーが空です。"

        for layer in layers:
            l_path = layer["path"]
            l_char = layer["char"]
            bbox = layer["bbox"]
            clip_rects = layer["clip_rects"]
            hit_rects = layer.get("hit_rects")
            slice_path = layer["slice_path"]
            needs_clip = layer["needs_clip"]

            # 不変条件 1: bbox の座標値が有限の実数であり、妥当な幾何範囲内であること
            assert len(bbox) == 4
            x, y, w, h = bbox
            assert -0.05 <= x <= 1.05, f"{char}:{l_path} bbox x={x} out of bounds"
            assert -0.05 <= y <= 1.05, f"{char}:{l_path} bbox y={y} out of bounds"
            assert 0.0 < w <= 1.10, f"{char}:{l_path} bbox w={w} degenerate"
            assert 0.0 < h <= 1.10, f"{char}:{l_path} bbox h={h} degenerate"

            # 不変条件 2: clip_rects が空でなく、各矩形が妥当であること
            assert isinstance(clip_rects, list) and len(clip_rects) >= 1
            for r in clip_rects:
                assert len(r) == 4
                _rx, _ry, rw, rh = r
                assert rw > 0.0 and rh > 0.0

            # 不変条件 3 (Bug 5 防止): 未クリップの全体 base_path 描画が絶対に発生しないこと
            if base_path and slice_path == base_path:
                assert needs_clip is True, (
                    f"【重大インバリアント違反】文字 '{char}' のレイヤー '{l_path}' ({l_char}) が "
                    f"needs_clip=False のまま全体グリフ base_path を描画しています。"
                )

            # 不変条件 4: hit_rects が指定されている場合、各要素が4要素リストであること
            if hit_rects is not None:
                assert isinstance(hit_rects, list) and len(hit_rects) >= 1
                for hr in hit_rects:
                    assert len(hr) == 4
                    assert hr[2] > 0.0 and hr[3] > 0.0

            # 不変条件 5: svg_transform が有効な構文であること
            st = layer.get("svg_transform", "")
            assert st.startswith("translate(")
            assert "scale(" in st
