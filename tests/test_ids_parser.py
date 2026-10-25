"""ids_parser.py の網羅的単体テストスイート."""

import pytest

import ids_parser


class TestIdcInfo:
    """全16種類のIDC演算子の定義およびアリティの検証."""

    def test_all_16_operators_defined(self):
        assert len(ids_parser.IDC_INFO) == 16
        expected_ops = {
            "⿰", "⿱", "⿲", "⿳", "⿴", "⿵", "⿶", "⿷",
            "⿸", "⿹", "⿺", "⿻", "⿼", "⿽", "⿾", "⿿",
        }
        assert set(ids_parser.IDC_INFO.keys()) == expected_ops

    @pytest.mark.parametrize("op,expected_arity", [
        ("⿰", 2), ("⿱", 2), ("⿲", 3), ("⿳", 3),
        ("⿴", 2), ("⿵", 2), ("⿶", 2), ("⿷", 2),
        ("⿸", 2), ("⿹", 2), ("⿺", 2), ("⿻", 2),
        ("⿼", 2), ("⿽", 2), ("⿾", 1), ("⿿", 1),
    ])
    def test_operator_arity(self, op, expected_arity):
        info = ids_parser.IDC_INFO[op]
        assert info["arity"] == expected_arity
        assert len(info["parts"]) == expected_arity


class TestChiseNormalization:
    """CHISE実体参照エンティティの正規化検証."""

    @pytest.mark.parametrize("entity,expected", [
        ("&U-i001+2FF1;", "⿱"),
        ("&U-i001+2FFB;", "⿻"),
        ("&U-i001+5E7A;", "幺"),
        ("&I-CDP-89B2;", "&CDP-89B2;"),
        ("&I-M-02329;", "&M-02329;"),
        ("&I-J90-3021;", "&J90-3021;"),
        ("&I-C1-2462;", "&C1-2462;"),
        ("&o-UU+4343;", "䍃"),
        ("&hanaJU+2E73F;", "𮜿"),
        ("&A-compU+7530;", "田"),
        ("&A-IWDSU+7A74;", "穴"),
        ("漢字", "漢字"),  # エンティティを含まない一般文字列
    ])
    def test_normalize_entity(self, entity, expected):
        assert ids_parser.normalize_entity(entity) == expected


class TestRadicalEquivalence:
    """部首等価性と双方向等価グループの検証."""

    def test_tsuduri_normalize_component(self):
        # ⺍ (U+2E8D) は「小」ではなく「𭕄」(U+2D544) に正規化されること
        assert ids_parser.normalize_component("⺍") == "𭕄"
        assert ids_parser.normalize_component("𭕄") == "𭕄"

    def test_equiv_groups_bidirectional(self):
        # 𭕄 と ⺍ が相互に等価グループに含まれていること
        assert "⺍" in ids_parser.EQUIV_GROUPS.get("𭕄", [])
        assert "𭕄" in ids_parser.EQUIV_GROUPS.get("⺍", [])

        # 氵, ⺡, 水 の部首等価グループ
        sanzui_group = ids_parser.EQUIV_GROUPS.get("氵", [])
        assert "水" in sanzui_group or "⺡" in sanzui_group


class TestTokenizeIds:
    """tokenize_ids のトークン分割とエンティティ正規化."""

    def test_tokenize_basic(self):
        tokens = ids_parser.tokenize_ids("⿱𰃮虫", normalize=False)
        assert tokens == ["⿱", "𰃮", "虫"]

    def test_tokenize_with_entity(self):
        tokens = ids_parser.tokenize_ids("⿰&CDP-89B2;木", normalize=False)
        assert tokens == ["⿰", "&CDP-89B2;", "木"]

    def test_tokenize_with_normalization(self):
        tokens = ids_parser.tokenize_ids("⿱&U-i001+2FF1;冖", normalize=True)
        assert tokens == ["⿱", "⿱", "冖"]


class TestParseIds:
    """parse_ids による前置記法AST構文木構築."""

    def test_binary_op_ast(self):
        node = ids_parser.parse_ids("⿰木木")
        assert node["type"] == "op"
        assert node["op"] == "⿰"
        assert len(node["children"]) == 2
        assert node["children"][0]["char"] == "木"
        assert node["children"][1]["char"] == "木"

    def test_ternary_op_ast(self):
        node = ids_parser.parse_ids("⿲木木木")
        assert node["type"] == "op"
        assert node["op"] == "⿲"
        assert len(node["children"]) == 3

    def test_missing_argument_fallback(self):
        # 演算子の引数が不足している場合のフォールバック
        node = ids_parser.parse_ids("⿰木")
        assert node["type"] == "op"
        assert len(node["children"]) == 2
        assert node["children"][1].get("missing") is True


class TestComputeBboxes:
    """compute_bboxes の2次元幾何計算."""

    def test_left_right_ratios(self):
        # 左部首 + 右細部首 (例: ⿰氵刂 -> 0.50 / 0.50)
        tree = ids_parser.decompose_character("⿰氵刂", max_depth=1, compute_bbox=True)
        c0, c1 = tree["children"]
        assert c0["bbox"] == [0.0, 0.0, 0.5, 1.0]
        assert c1["bbox"] == [0.5, 0.0, 0.5, 1.0]

    def test_left_radical_normal(self):
        # 左標準部首 (例: ⿰土木 -> 0.38 / 0.62)
        tree = ids_parser.decompose_character("⿰土木", max_depth=1, compute_bbox=True)
        c0, c1 = tree["children"]
        assert c0["bbox"] == [0.0, 0.0, 0.38, 1.0]
        assert c1["bbox"] == [0.38, 0.0, 0.62, 1.0]

    def test_left_narrow_radical(self):
        # 左細幅部首 (例: ⿰氵木 -> 0.33 / 0.67)
        tree = ids_parser.decompose_character("⿰氵木", max_depth=1, compute_bbox=True)
        c0, c1 = tree["children"]
        assert c0["bbox"] == [0.0, 0.0, 0.33, 1.0]
        assert c1["bbox"] == [0.33, 0.0, 0.67, 1.0]

    def test_small_top_radicals_ratio(self):
        # 3点冠 (例: ⿱𭕄果 -> 0.22 / 0.78)
        tree = ids_parser.decompose_character("⿱𭕄果", max_depth=1, compute_bbox=True)
        c0, c1 = tree["children"]
        assert c0["bbox"] == [0.0, 0.0, 1.0, 0.22]
        assert c1["bbox"] == [0.0, 0.22, 1.0, 0.78]

    def test_heavy_top_components_ratio(self):
        # 墓 (⿱莫土) -> 莫が 0.65, 土が 0.35
        tree = ids_parser.decompose_character("⿱莫土", max_depth=1, compute_bbox=True)
        c0, c1 = tree["children"]
        assert c0["bbox"] == [0.0, 0.0, 1.0, 0.65]
        assert c1["bbox"] == [0.0, 0.65, 1.0, 0.35]

    def test_flanking_gate_opening(self):
        # 問 (門が両脇展開され、口は中央開口部 y=0.36, h=0.58)
        tree = ids_parser.decompose_character("問", max_depth=2, compute_bbox=True)
        c0, c1 = tree["children"]
        assert c0.get("is_flanking") is True
        assert c1["role_label"] == "中央"
        assert c1["bbox"][1] == 0.36
        assert c1["bbox"][3] == 0.58

    def test_penetration_overlay_top_bottom_geometry(self):
        # 果 (⿻日木): 日が上部 (h=0.46), 木が下部 (y=0.36, h=0.64)
        tree = ids_parser.decompose_character("果", max_depth=2, compute_bbox=True)
        hi, ki = tree["children"]
        assert hi["char"] == "日"
        assert hi["bbox"] == [0.14, 0.0, 0.72, 0.46]
        assert ki["char"] == "木"
        assert ki["bbox"] == [0.0, 0.36, 1.0, 0.64]

        # 日 (⿴囗一): 一は中央横画 (h=0.24, y2 <= 0.30)
        _, ichi = hi["children"]
        assert ichi["char"] == "一"
        assert ichi["bbox"][3] <= 0.15
        assert ichi["bbox"][1] + ichi["bbox"][3] <= 0.30

        # 木 (⿻十丷): 丷（左右ハネ）は下部 (y >= 0.55)
        _, hane = ki["children"]
        assert hane["char"] == "丷"
        assert hane["bbox"][1] >= 0.55


class TestEnclosurePeripheralRects:
    """_get_enclosure_peripheral_rects の中空矩形生成."""

    @pytest.mark.parametrize("role,node_char,expected_count", [
        ("外囲", "囗", 4),
        ("上囲", "冂", 3),
        ("下囲", "凵", 3),
        ("左囲", "匚", 3),
        ("垂れ", "广", 2),
        ("包み", "勹", 2),
        ("繞", "辶", 2),
    ])
    def test_enclosure_rect_counts(self, role, node_char, expected_count):
        rects = ids_parser._get_enclosure_peripheral_rects(role, node_char, [0.0, 0.0, 1.0, 1.0])
        assert rects is not None
        assert len(rects) == expected_count
        # すべての矩形が [0, 0, 1, 1] の内部にあること
        for r in rects:
            assert 0.0 <= r[0] <= 1.0
            assert 0.0 <= r[1] <= 1.0
            assert r[2] > 0.0 and r[3] > 0.0


class TestDecomposeCharacter:
    """decompose_character の再帰展開と制限."""

    def test_decomposition_succeeds(self):
        tree = ids_parser.decompose_character("鬱", max_depth=2, compute_bbox=True)
        assert tree is not None
        assert tree["type"] == "op"
        assert len(tree["children"]) >= 2

    def test_cycle_prevention(self):
        # 相互参照や再帰による無限ループが発生せず正常終了すること
        tree = ids_parser.decompose_character("日", max_depth=8, compute_bbox=True)
        assert tree is not None
