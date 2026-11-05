"""Tests for stroke allocation and selection in flanking and interspersed component structures.

Validates regression fixes for characters like 鬱, 樊, 攀, 礬 where a flanking component
(such as 林 on the left and right) intersperses with a center component (such as 缶 or 爻).
"""

import ids_parser
import glyph_service


def test_utsu_stroke_allocation_exact():
    """Verify exact stroke assignments for 鬱 (U+9B31).

    Ensures that:
    - 0.0.0 (林) owns only the 8 strokes of left and right 木 (s7..s14), NOT 缶.
    - 0.0.0.0 (left 木) owns only the 4 strokes of left 木 (s7..s10).
    - 0.0.0.1 (right 木) owns only the 4 strokes of right 木 (s11..s14).
    - 0.0.1.0 (缶) owns only the 6 strokes of 缶 (s1..s6).
    - 0.0.1.1 (冖) owns only the 2 strokes of 冖 (s15..s16).
    - All subcomponents of 木 (十, 丷, 丶, 丿) own their exact respective strokes.
    - kvg_tree groups match these paths with no leaking of 缶 into 0.0.0.0.
    """
    tree = ids_parser.decompose_character("鬱", max_depth=6, compute_bbox=True)
    res = glyph_service.extract_kanjivg_stroke_layers("鬱", tree)

    assert res["has_kvg"] is True
    strokes = res["layer_strokes"]

    # 1. 缶 (6 strokes)
    expected_kan = [f"kvg:09b31-s{i}" for i in range(1, 7)]
    assert strokes["0.0.1.0"] == expected_kan

    # 2. Left 木 (4 strokes)
    expected_left_wood = [f"kvg:09b31-s{i}" for i in range(7, 11)]
    assert strokes["0.0.0.0"] == expected_left_wood

    # 3. Right 木 (4 strokes)
    expected_right_wood = [f"kvg:09b31-s{i}" for i in range(11, 15)]
    assert strokes["0.0.0.1"] == expected_right_wood

    # 4. 林 (8 strokes = left 木 + right 木, strictly NO 缶 strokes)
    expected_forest = expected_left_wood + expected_right_wood
    assert strokes["0.0.0"] == expected_forest
    assert not (set(strokes["0.0.0"]) & set(expected_kan))

    # 5. 冖 (2 strokes)
    expected_crown = ["kvg:09b31-s15", "kvg:09b31-s16"]
    assert strokes["0.0.1.1"] == expected_crown

    # 6. 中央・下 (8 strokes = 缶 + 冖)
    assert set(strokes["0.0.1"]) == set(expected_kan + expected_crown)

    # 7. 上 (16 strokes = 林 + 缶 + 冖)
    assert strokes["0.0"] == [f"kvg:09b31-s{i}" for i in range(1, 17)]

    # 8. Left 木 subcomponents:
    # 0.0.0.0.0 (十) -> 2 strokes
    assert strokes["0.0.0.0.0"] == ["kvg:09b31-s7", "kvg:09b31-s8"]
    # 0.0.0.0.1 (丷) -> 2 strokes
    assert strokes["0.0.0.0.1"] == ["kvg:09b31-s9", "kvg:09b31-s10"]
    # 0.0.0.0.1.0 (丶) -> 1 stroke
    assert strokes["0.0.0.0.1.0"] == ["kvg:09b31-s9"]
    # 0.0.0.0.1.1 (丿) -> 1 stroke
    assert strokes["0.0.0.0.1.1"] == ["kvg:09b31-s10"]

    # 9. Right 木 subcomponents:
    # 0.0.0.1.0 (十) -> 2 strokes
    assert strokes["0.0.0.1.0"] == ["kvg:09b31-s11", "kvg:09b31-s12"]
    # 0.0.0.1.1 (丷) -> 2 strokes
    assert strokes["0.0.0.1.1"] == ["kvg:09b31-s13", "kvg:09b31-s14"]
    # 0.0.0.1.1.0 (丶) -> 1 stroke
    assert strokes["0.0.0.1.1.0"] == ["kvg:09b31-s13"]
    # 0.0.0.1.1.1 (丿) -> 1 stroke
    assert strokes["0.0.0.1.1.1"] == ["kvg:09b31-s14"]

    # 10. KanjiVG group paths in kvg_tree
    kvg_tree = res["kvg_tree"]
    groups_by_path = {}

    def collect_groups(g):
        p = g.get("path")
        if p:
            groups_by_path[p] = g
        for ch in g.get("children", []):
            collect_groups(ch)

    collect_groups(kvg_tree)

    assert "0.0.0.0" in groups_by_path
    assert groups_by_path["0.0.0.0"]["element"] == "木"
    assert groups_by_path["0.0.0.0"]["direct"] == expected_left_wood

    assert "0.0.0.1" in groups_by_path
    assert groups_by_path["0.0.0.1"]["element"] == "木"
    assert groups_by_path["0.0.0.1"]["direct"] == expected_right_wood

    assert "0.0.1.0" in groups_by_path
    assert groups_by_path["0.0.1.0"]["element"] == "缶"
    assert groups_by_path["0.0.1.0"]["direct"] == expected_kan

    assert "0.0.1.1" in groups_by_path
    assert groups_by_path["0.0.1.1"]["element"] == "冖"
    assert groups_by_path["0.0.1.1"]["direct"] == expected_crown


def test_interspersed_forest_characters_disjointness():
    """Verify that interspersed 林 and center components in 樊, 攀, 礬 are cleanly separated."""
    # 樊: 棥 (⿴林爻) + 大
    tree_fan = ids_parser.decompose_character("樊", max_depth=6, compute_bbox=True)
    res_fan = glyph_service.extract_kanjivg_stroke_layers("樊", tree_fan)
    strokes_fan = res_fan["layer_strokes"]

    forest_fan = set(strokes_fan["0.0.0"])
    center_fan = set(strokes_fan["0.0.1"])
    assert len(forest_fan) == 8
    assert len(center_fan) == 4
    assert not (forest_fan & center_fan), "In 樊, 林 strokes and 爻 strokes must be disjoint"
    assert strokes_fan["0.0.0.0"] == ["kvg:06a0a-s5", "kvg:06a0a-s6", "kvg:06a0a-s7", "kvg:06a0a-s8"]
    assert strokes_fan["0.0.0.1"] == ["kvg:06a0a-s9", "kvg:06a0a-s10", "kvg:06a0a-s11", "kvg:06a0a-s12"]
    assert strokes_fan["0.0.1"] == ["kvg:06a0a-s1", "kvg:06a0a-s2", "kvg:06a0a-s3", "kvg:06a0a-s4"]

    # 攀: 樊 (棥+大) + 手
    tree_pan = ids_parser.decompose_character("攀", max_depth=6, compute_bbox=True)
    res_pan = glyph_service.extract_kanjivg_stroke_layers("攀", tree_pan)
    strokes_pan = res_pan["layer_strokes"]

    forest_pan = set(strokes_pan["0.0.0.0"])
    center_pan = set(strokes_pan["0.0.0.1"])
    assert len(forest_pan) == 8
    assert len(center_pan) == 4
    assert not (forest_pan & center_pan), "In 攀, 林 strokes and 爻 strokes must be disjoint"
    assert strokes_pan["0.0.0.0.0"] == ["kvg:06500-s5", "kvg:06500-s6", "kvg:06500-s7", "kvg:06500-s8"]
    assert strokes_pan["0.0.0.0.1"] == ["kvg:06500-s9", "kvg:06500-s10", "kvg:06500-s11", "kvg:06500-s12"]
    assert strokes_pan["0.0.0.1"] == ["kvg:06500-s1", "kvg:06500-s2", "kvg:06500-s3", "kvg:06500-s4"]

    # 礬: 樊 + 石
    tree_fan2 = ids_parser.decompose_character("礬", max_depth=6, compute_bbox=True)
    res_fan2 = glyph_service.extract_kanjivg_stroke_layers("礬", tree_fan2)
    strokes_fan2 = res_fan2["layer_strokes"]

    forest_fan2 = set(strokes_fan2["0.0.0.0"])
    center_fan2 = set(strokes_fan2["0.0.0.1"])
    assert len(forest_fan2) == 8
    assert len(center_fan2) == 4
    assert not (forest_fan2 & center_fan2), "In 礬, 林 strokes and 爻 strokes must be disjoint"
    assert strokes_fan2["0.0.0.0.0"] == ["kvg:0792c-s1", "kvg:0792c-s2", "kvg:0792c-s3", "kvg:0792c-s4"]
    assert strokes_fan2["0.0.0.0.1"] == ["kvg:0792c-s9", "kvg:0792c-s10", "kvg:0792c-s11", "kvg:0792c-s12"]
    assert strokes_fan2["0.0.0.1"] == ["kvg:0792c-s5", "kvg:0792c-s6", "kvg:0792c-s7", "kvg:0792c-s8"]


def test_flanking_container_flag_on_ast():
    """Verify that is_flanking_container is properly set on AST parent nodes of flanking elements."""
    for ch in ["鬱", "樊", "攀", "礬", "班", "問"]:
        tree = ids_parser.decompose_character(ch, max_depth=6, compute_bbox=True)

        containers = []

        def find_containers(n):
            if n.get("is_flanking_container"):
                containers.append(n)
            for c in n.get("children", []):
                find_containers(c)

        find_containers(tree)
        assert len(containers) >= 1, f"{ch} should have at least one flanking container node"
        for c_node in containers:
            ch_nodes = c_node.get("children", [])
            assert any(c.get("is_flanking") or c.get("role_label") == "両脇" for c in ch_nodes)
