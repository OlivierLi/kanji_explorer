"""glyph_service.py の網羅的単体テストスイート."""

import pytest

import ids_parser
import glyph_service


class TestJigmoOutlineExtraction:
    """Jigmoフォントからのベクターアウトライン抽出."""

    @pytest.mark.parametrize("char", ["蛍", "日", "月", "木", "水", "火", "土", "金"])
    def test_get_jigmo_path_common_kanji(self, char):
        path_d = glyph_service.get_jigmo_path(char)
        assert path_d is not None
        assert path_d.startswith("M")
        assert "Z" in path_d

    def test_get_jigmo_path_extension_g(self):
        # 拡張G領域の文字 (𰃮: U+300EE)
        path_d = glyph_service.get_jigmo_path("𰃮")
        assert path_d is not None
        assert path_d.startswith("M")

    def test_get_jigmo_path_nonexistent_returns_none(self):
        # 存在しない特殊文字
        path_d = glyph_service.get_jigmo_path("\ufffd")
        assert path_d is None


class TestSvgPathParsing:
    """_parse_svg_path_points によるSVGコマンド解析."""

    def test_parse_simple_rect(self):
        d = "M 0 0 L 100 0 L 100 100 L 0 100 Z"
        pts = glyph_service._parse_svg_path_points(d)
        assert len(pts) >= 4
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        assert min(xs) == 0 and max(xs) == 100
        assert min(ys) == 0 and max(ys) == 100

    def test_parse_curves(self):
        d = "M 10 10 C 20 20 40 20 50 10 Q 60 0 70 10 Z"
        pts = glyph_service._parse_svg_path_points(d)
        assert len(pts) >= 3


class TestExtractInkIslands:
    """_extract_ink_islands による独立インク島および内包穴の抽出."""

    def test_extract_islands_from_sun(self):
        # 「日」: 外枠 + 内部穴（2つ）
        path_d = glyph_service.get_jigmo_path("日")
        assert path_d is not None
        islands = glyph_service._extract_ink_islands(path_d)
        assert len(islands) >= 1
        isl0 = islands[0]
        assert "hole_boxes" in isl0
        assert len(isl0["hole_boxes"]) == 2

    def test_island_geometry_normalization(self):
        # 抽出されたインク島の座標が 0.0〜1.0 の正規化範囲内であること
        path_d = glyph_service.get_jigmo_path("木")
        islands = glyph_service._extract_ink_islands(path_d)
        assert len(islands) >= 1
        for isl in islands:
            assert 0.0 <= isl["x1"] <= 1.0
            assert 0.0 <= isl["y1"] <= 1.0
            assert 0.0 <= isl["x2"] <= 1.0
            assert 0.0 <= isl["y2"] <= 1.0
            assert isl["w"] > 0 and isl["h"] > 0


class TestExpectedMinIslands:
    """_expected_min_islands の最小島数推論."""

    @pytest.mark.parametrize("char,expected", [
        ("⺍", 3), ("𭕄", 3), ("⺌", 3), ("氵", 3), ("灬", 3),
        ("丷", 2), ("八", 2), ("冫", 2), ("二", 2),
        ("口", 1), ("木", 1), ("日", 1),
    ])
    def test_expected_min_islands_leaves(self, char, expected):
        node = {"type": "char", "char": char}
        assert glyph_service._expected_min_islands(node) == expected


class TestAssignLinear:
    """_assign_linear による左右・上下方向の幾何配分."""

    def test_linear_split_horizontal(self):
        children = [
            {"bbox": [0.0, 0.0, 0.4, 1.0]},
            {"bbox": [0.4, 0.0, 0.6, 1.0]},
        ]
        islands = [
            {"id": 0, "x1": 0.05, "x2": 0.35, "y1": 0.1, "y2": 0.9},
            {"id": 1, "x1": 0.45, "x2": 0.95, "y1": 0.1, "y2": 0.9},
        ]
        assignments = {0: [], 1: []}
        shared = set()
        glyph_service._assign_linear(children, islands, "x", 1.0, assignments, shared)
        assert len(assignments[0]) == 1 and assignments[0][0]["id"] == 0
        assert len(assignments[1]) == 1 and assignments[1][0]["id"] == 1
        assert len(shared) == 0

    def test_linear_spanning_island_shared(self):
        children = [
            {"bbox": [0.0, 0.0, 1.0, 0.3]},
            {"bbox": [0.0, 0.3, 1.0, 0.7]},
        ]
        islands = [
            {"id": 0, "x1": 0.45, "x2": 0.55, "y1": 0.05, "y2": 0.90},  # 全体を跨ぐ縦画
        ]
        assignments = {0: [], 1: []}
        shared = set()
        glyph_service._assign_linear(children, islands, "y", 1.0, assignments, shared)
        assert len(assignments[0]) == 1 and assignments[0][0]["id"] == 0
        assert len(assignments[1]) == 1 and assignments[1][0]["id"] == 0
        assert 0 in shared


class TestBuildInteractiveIdsSvg:
    """build_interactive_ids_svg の出力構造・変形行列・クリップ検証."""

    def test_interactive_svg_structure(self):
        tree = ids_parser.decompose_character("休", max_depth=2, compute_bbox=True)
        tree["char"] = "休"
        res = glyph_service.build_interactive_ids_svg(tree)
        assert "base_path" in res and res["base_path"] is not None
        assert "component_layers" in res
        assert len(res["component_layers"]) >= 2

        for layer in res["component_layers"]:
            assert "path" in layer
            assert "char" in layer
            assert "bbox" in layer
            assert "clip_rects" in layer
            assert "svg_transform" in layer
            assert "slice_path" in layer
            assert "needs_clip" in layer
            # svg_transform のフォーマット検証: translate(...) scale(...)
            assert layer["svg_transform"].startswith("translate(")
            assert "scale(" in layer["svg_transform"]


class TestGetGlyphSvg:
    """get_glyph_svg による単一文字および実体参照SVG生成."""

    def test_single_char_jigmo_svg(self):
        svg = glyph_service.get_glyph_svg("木")
        assert svg.startswith("<svg")
        assert "</svg>" in svg
        assert 'fill="#57606a"' in svg

    def test_entity_resolution_svg(self):
        svg = glyph_service.get_glyph_svg("&CDP-8BD9;")
        assert svg.startswith("<svg")

    def test_unresolved_fallback_svg(self):
        svg = glyph_service.get_glyph_svg("&UNKNOWN-TEST-TOKEN;")
        assert svg.startswith("<svg")
        assert "UNKNOWN-TEST-TOKEN" in svg


class TestKanjiVgService:
    """KanjiVGService のパースおよびCHISE IDSアライメント."""

    def test_kanjivg_parse_common_kanji(self):
        service = glyph_service._get_default_kanjivg_service()
        data = service.parse_kanji("日", align_chise=True)
        assert data is not None
        assert "strokes" in data
        assert len(data["strokes"]) == 4

    def test_kanjivg_chise_alignment_hotaru(self):
        service = glyph_service._get_default_kanjivg_service()
        data = service.parse_kanji("蛍", align_chise=True)
        assert data is not None
        # 蛍のトップノードが存在すること
        assert data["id"] == "kvg:086cd"
        assert len(data["children"]) >= 1
