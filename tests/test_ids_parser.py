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
        ("&I-J90-3021;", "亜"),
        ("&I-C1-2462;", "&C1-2462;"),
        ("&o-UU+4343;", "䍃"),
        ("&hanaJU+2E73F;", "𮜿"),
        ("&A-compU+7530;", "田"),
        ("&A-IWDSU+7A74;", "穴"),
        ("漢字", "漢字"),  # エンティティを含まない一般文字列
        # Coded-charset entities (J90, J83, JX1, JX2, G0, K0; J78 excluded)
        ("&J90-3839;", "弦"),
        ("&J83-3C59;", "邪"),
        ("&JX1-7B41;", "藋"),
        ("&JX2-7461;", "䍃"),
        ("&G0-4630;", "瓢"),
        ("&K0-7443;", "遷"),
        ("&JSP-457C;", "歰"),
        ("&J78-4B29;", "&J78-4B29;"),
        # Unicode Hex variants (BUCS+, CU+, GU+)
        ("&BUCS+518C;", "册"),
        ("&CU+2AE8D;", "𪺍"),
        ("&GU+37B7;", "㞷"),
        # CDP variant prefixes (i and v)
        ("&CDP-v001-8BEA;", "刂"),
        ("&CDP-i001-8BD9;", "甲"),
        # Wrapper prefix stripping (A-, g2-)
        ("&A-U-i002+34BC;", "㒼"),
        ("&A-CDP-i001-88BA;", "&CDP-88BA;"),
        ("&g2-UNKNOWN123;", "&UNKNOWN123;"),
        ("&g2-MJ014823;", "止"),
        ("&g2-MJ007273;", "八"),
        # Generated map resolution
        ("&AJ1-01904;", "玄"),
        ("&CDP-8B7C;", "皀"),
        ("&GT-K02140;", "乑"),
    ])
    def test_normalize_entity(self, entity, expected):
        assert ids_parser.normalize_entity(entity) == expected

    def test_generated_map_aj1_01904(self):
        # 手動オーバーライドマップから削除後も、自動生成マップ経由で玄に解決されること
        assert ids_parser.normalize_entity("&AJ1-01904;") == "玄"
        assert "&AJ1-01904;" not in ids_parser.CHISE_ENTITY_UNICODE_MAP
        assert ids_parser.GENERATED_ENTITY_UNICODE_MAP.get("&AJ1-01904;") == "玄"


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

    def test_radical_independence_gon_and_hyou(self):
        # 艮 (康煕部首138) と 皀 (康煕部首108) が誤って同一グループにマージされないこと
        assert "皀" not in ids_parser.EQUIV_GROUPS.get("艮", [])
        assert "艮" not in ids_parser.EQUIV_GROUPS.get("皀", [])
        assert ids_parser.normalize_entity("&CDP-8B7C;") == "皀"


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

    def test_decompose_ivs_character(self):
        # 異体字セレクタ (IVS) を含む文字列が単一文字として正しく分解されること
        tree = ids_parser.decompose_character("神\U000E0100", max_depth=2, compute_bbox=True)
        assert tree["char"] == "神"
        assert tree["type"] == "op"
        # 異体字セレクタが架空の子要素として紛れ込まないこと
        assert not any(c.get("raw_char") == "\U000E0100" for c in tree.get("children", []))

    def test_decompose_codepoint_string(self):
        # U+XXXX 表記が自動解決され、対象漢字の構造が正しく分解されること
        tree = ids_parser.decompose_character("U+86CD", max_depth=2, compute_bbox=True)
        assert tree["char"] == "蛍"
        assert tree["op"] == "⿱"

    def test_decompose_aj1_01904_and_ken(self):
        # &AJ1-01904; (玄) が正常に正規化・分解され、牽の構成要素木にも反映されること
        assert ids_parser.normalize_entity("&AJ1-01904;") == "玄"
        tree_aj1 = ids_parser.decompose_character("&AJ1-01904;", max_depth=2)
        assert tree_aj1["char"] == "玄"
        assert tree_aj1["type"] == "op"
        assert any(c.get("char") == "幺" for c in tree_aj1.get("children", []))

        tree_ken = ids_parser.decompose_character("牽", max_depth=3)
        assert tree_ken["char"] == "牽"
        cdp_node = next((c for c in tree_ken.get("children", []) if c.get("char") == "&CDP-89FE;"), None)
        assert cdp_node is not None
        assert any(c.get("char") == "玄" for c in cdp_node.get("children", []))

    def test_decompose_gtk00859_and_rui(self):
        # &GT-K00859; (⿱八𠆢) が八と𠆢に分解され、八への誤等価マッピングが防止されていること
        assert ids_parser.normalize_entity("&GT-K00859;") == "&GT-K00859;"
        tree_k00859 = ids_parser.decompose_character("&GT-K00859;", max_depth=2)
        assert tree_k00859["char"] == "&GT-K00859;"
        assert tree_k00859["op"] == "⿱"
        assert [c["char"] for c in tree_k00859["children"]] == ["八", "𠆢"]

        # 睿 (⿱&GT-K01554;⿱&GT-K00859;目) の木に八と𠆢が含まれること
        tree_rui = ids_parser.decompose_character("睿", max_depth=4)
        assert tree_rui["char"] == "睿"
        all_chars = set()

        def _walk(node):
            if not node:
                return
            all_chars.add(node.get("char"))
            for c in node.get("children", []):
                _walk(c)

        _walk(tree_rui)
        assert "八" in all_chars and "𠆢" in all_chars

    def test_decompose_gtk03307(self):
        # &GT-K03307; (⿱爫幺) が正常に爫と幺に分解されること
        assert ids_parser.normalize_entity("&GT-K03307;") == "&GT-K03307;"
        tree_k03307 = ids_parser.decompose_character("&GT-K03307;", max_depth=2)
        assert tree_k03307["char"] == "&GT-K03307;"
        assert tree_k03307["op"] == "⿱"
        assert [c["char"] for c in tree_k03307["children"]] == ["爫", "幺"]

    def test_decompose_c6_2d56_and_gyo(self):
        # &C6-2D56; (⿱䒑未) が正常に䒑と未に分解され、業の構成要素木にも反映されること
        assert ids_parser.normalize_entity("&C6-2D56;") == "&C6-2D56;"
        tree_c6 = ids_parser.decompose_character("&C6-2D56;", max_depth=2)
        assert tree_c6["char"] == "&C6-2D56;"
        assert tree_c6["op"] == "⿱"
        assert [c["char"] for c in tree_c6["children"]] == ["䒑", "未"]

        # 業 の木に䒑と未が含まれること
        tree_gyo = ids_parser.decompose_character("業", max_depth=4)
        assert tree_gyo["char"] == "業"
        all_chars = set()

        def _walk(node):
            if not node:
                return
            all_chars.add(node.get("char"))
            for c in node.get("children", []):
                _walk(c)

        _walk(tree_gyo)
        assert "䒑" in all_chars and "未" in all_chars

    def test_decompose_cdp_8ba4_and_ki(self):
        # &CDP-8BA4; (⿻戈𢆶) がアリティ2の⿻構造として正しく展開され、幾・畿に？欠損が発生しないこと
        tree_cdp = ids_parser.decompose_character("&CDP-8BA4;", max_depth=2)
        assert tree_cdp["op"] == "⿻"
        assert [c["char"] for c in tree_cdp["children"]] == ["戈", "𢆶"]

        def _has_missing(node):
            if not node:
                return False
            if node.get("missing"):
                return True
            return any(_has_missing(c) for c in node.get("children", []))

        tree_ki = ids_parser.decompose_character("畿", max_depth=5)
        assert not _has_missing(tree_ki)

    def test_decompose_cdp_89cc_and_kai(self):
        # &CDP-89CC; (⿰丨丨) がアリティ2の⿰構造として正しく展開され、囬の内側に？欠損が発生しないこと
        tree_cdp = ids_parser.decompose_character("&CDP-89CC;", max_depth=2)
        assert tree_cdp["op"] == "⿰"
        assert [c["char"] for c in tree_cdp["children"]] == ["丨", "丨"]

        def _has_missing(node):
            if not node:
                return False
            if node.get("missing"):
                return True
            return any(_has_missing(c) for c in node.get("children", []))

        tree_kai = ids_parser.decompose_character("囬", max_depth=5)
        assert not _has_missing(tree_kai)

    def test_decompose_cdp_89e0_and_ten(self):
        # &CDP-89E0; (⿱𠕁一) が正しく展開され、典の構成要素木に反映されること
        tree_cdp = ids_parser.decompose_character("&CDP-89E0;", max_depth=2)
        assert tree_cdp["op"] == "⿱"
        assert [c["char"] for c in tree_cdp["children"]] == ["𠕁", "一"]

        tree_ten = ids_parser.decompose_character("典", max_depth=4)
        assert tree_ten["char"] == "典"
        all_chars = set()

        def _walk(node):
            if not node:
                return
            all_chars.add(node.get("char"))
            for c in node.get("children", []):
                _walk(c)

        _walk(tree_ten)
        assert "𠕁" in all_chars or "&CDP-89E0;" in all_chars

    def test_decompose_gtk00132_and_mcs(self):
        # &GT-K00132; (⿰丨丨) および &MCS-60012539; (&CDP-89E7;) の解決検証
        tree_gtk = ids_parser.decompose_character("&GT-K00132;", max_depth=2)
        assert tree_gtk["op"] == "⿰"
        assert [c["char"] for c in tree_gtk["children"]] == ["丨", "丨"]

        assert ids_parser.COMPONENT_SUBDECOMPOSITIONS.get("&MCS-60012539;") == "&CDP-89E7;"


