"""Rendered component ownership regressions from the correctness review."""
import pytest

import glyph_service
import ids_parser
from scripts.fuzz import raster


@pytest.mark.parametrize("char,path", [("日", "0"), ("目", "0"),
                                      ("明", "0.0"), ("相", "0.1"),
                                      ("晶", "0.0"), ("晶", "0.1.0"), ("晶", "0.1.1")])
def test_counter_bars_exclude_frame_and_preserve_parent(char, path):
    tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
    visual = glyph_service.build_interactive_ids_svg(tree)
    whole, masks = raster.compute_all_layer_masks(char, visual, size=512)
    frame, inner = masks[path + ".0"], masks[path + ".1"]
    parent = whole if path == "0" else masks[path]
    assert inner.sum() > 50
    # Raster rounding can share one boundary column, but never whole sidebars.
    # Each shared edge can occupy one raster row/column due to outward rounding.
    inner_layer = next(l for l in visual["component_layers"] if l["path"] == path + ".1")
    boundary_budget = sum(2 * 512 * (r[2] + r[3]) + 4 for r in inner_layer["clip_rects"])
    assert (frame & inner).sum() <= boundary_budget
    assert ((frame | inner) & parent).sum() / parent.sum() > 0.98
    layers = {layer["path"]: layer for layer in visual["component_layers"]}
    clips = layers[path + ".1"]["clip_rects"]
    if len(clips) == 2:
        for i in range(2):
            child = masks[path + f".1.{i}"]
            assert child.sum() > 50
            assert (child & frame).sum() <= boundary_budget / 2
        assert ((masks[path + ".1.0"] | masks[path + ".1.1"]) == inner).all()


def test_lin_repeated_spoon_children_cover_distinct_stroke_pairs():
    strokes = glyph_service.extract_kanjivg_stroke_layers("麟")["layer_strokes"]
    assert strokes["0.0.1.0"] == ["kvg:09e9f-s8", "kvg:09e9f-s9"]
    assert strokes["0.0.1.1"] == ["kvg:09e9f-s10", "kvg:09e9f-s11"]
    assert strokes["0.0.1.0"] + strokes["0.0.1.1"] == strokes["0.0.1"]


@pytest.mark.parametrize("char,path,count", [("曆", "0.1.1", 1), ("惧", "0.1.0.1", 2)])
def test_refined_counter_bars_keep_the_ink_at_their_new_location(char, path, count):
    tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
    visual = glyph_service.build_interactive_ids_svg(tree)
    whole, masks = raster.compute_all_layer_masks(char, visual, size=512)
    layers = {layer["path"]: layer for layer in visual["component_layers"]}
    inner = masks[path]
    expected = whole & raster.create_clip_mask(layers[path]["clip_rects"], size=512)
    assert expected.sum() > 50
    assert (inner == expected).all()
    if count == 2:
        bars = [masks[f"{path}.{i}"] for i in range(count)]
        assert all(bar.sum() > 50 for bar in bars)
        assert ((bars[0] | bars[1]) == inner).all()


@pytest.mark.parametrize("char,prefix,start", [("弱", "0", 1), ("溺", "0.1", 4),
                                              ("搦", "0.1", 4), ("鰯", "0.1", 12)])
def test_repeated_enclosures_preserve_matched_bow_descendants(char, prefix, start):
    strokes = glyph_service.extract_kanjivg_stroke_layers(char)["layer_strokes"]
    for i in range(2):
        first = start + i * 5
        assert strokes[f"{prefix}.{i}.0"] == [
            f"kvg:{ord(char):05x}-s{n}" for n in range(first, first + 3)
        ]


def test_ori_retains_source_group_shared_stroke():
    strokes = glyph_service.extract_kanjivg_stroke_layers("織")["layer_strokes"]
    assert set(strokes["0.1.0"]) & set(strokes["0.1.1"]) == {"kvg:07e54-s11"}
    assert set(strokes["0.1.0"]) | set(strokes["0.1.1"]) == set(strokes["0.1"])
