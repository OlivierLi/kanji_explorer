"""A nonempty bounding-box overlap is not necessarily an ink intersection."""
import pytest

import glyph_service as glyphs
import ids_parser
from geometry import clip_polygon_area
from scripts.fuzz import raster


@pytest.mark.parametrize('rect,area', [([0,0,1,1],1), ([0.5,0,1,1],0.5),
                                     ([1,0,1,1],0), ([0,0,0,1],0)])
def test_polygon_clip_area(rect, area):
    square = [(0,0), (1,0), (1,1), (0,1)]
    assert clip_polygon_area(square, rect) == pytest.approx(area)


def test_counter_is_not_ink():
    island = glyphs._extract_ink_islands(glyphs.get_jigmo_path('口'))[0]
    x1, y1, x2, y2 = island['hole_boxes'][0]
    inside = [x1 + .01, y1 + .01, x2 - x1 - .02, y2 - y1 - .02]
    assert not glyphs._island_intersects_clips(island, [inside])
    assert glyphs._island_intersects_clips(island, [[0,0,1,1]])


@pytest.mark.parametrize('assigned', [0, 1])
def test_empty_assignments_recover_and_populated_assignments_are_preserved(monkeypatch, assigned):
    # The first contour is L-shaped: its bbox covers the second, isolated bar.
    path = 'M0 880H1024V800H80V-144H0Z M410 470H614V368H410Z'
    monkeypatch.setattr(glyphs, 'get_jigmo_path', lambda char: path)

    def assign(tree, islands, shared):
        for child in tree['children']:
            child['_islands'] = [islands[assigned]]
            child['_has_shared_island'] = True
            child['clip_rects'] = [[.4, .4, .2, .1]]

    monkeypatch.setattr(glyphs, '_assign_ink_islands_to_tree', assign)
    tree = ids_parser.parse_ids('⿰一二', compute_bbox=True)
    tree['char'] = '仮'
    visual = glyphs.build_interactive_ids_svg(tree)
    expected_path = path if assigned == 0 else glyphs._extract_ink_islands(path)[1]['d']
    assert all(layer['slice_path'] == expected_path for layer in visual['component_layers'])
    whole, masks = raster.compute_all_layer_masks('仮', visual, size=256)
    assert masks['0.0'].sum() > 100
    expected = whole & raster.create_clip_mask([[.4,.4,.2,.1]], size=256)
    assert (masks['0.0'] == expected).all()


@pytest.mark.parametrize('path', ['0.1.0.1', '0.1.1.0.1'])
def test_taki_bars_have_the_ink_at_their_clip_positions(path):
    tree = ids_parser.decompose_character('滝', max_depth=6, compute_bbox=True)
    visual = glyphs.build_interactive_ids_svg(tree)
    whole, masks = raster.compute_all_layer_masks('滝', visual, size=512)
    layer = next(layer for layer in visual['component_layers'] if layer['path'] == path)
    expected = whole & raster.create_clip_mask(layer['clip_rects'], size=512)
    assert expected.sum() > 50
    assert (masks[path] == expected).all()



def test_curved_contours_are_not_declared_empty_from_control_polygons():
    island = glyphs._extract_ink_islands('M0 880Q512 1000 1024 880L1024 800H0Z')[0]
    assert not island['is_linear']
    assert glyphs._island_intersects_clips(island, [[.4,.4,.2,.1]])


@pytest.mark.parametrize('char', list('道画進埴飜操殖遼欄遭植値運連遵直置䯂䳗'))
def test_holes_are_attached_to_contours_that_contain_them(char):
    from geometry import contains_polygon
    islands = glyphs._extract_ink_islands(glyphs.get_jigmo_path(char))
    assert any(island['hole_polygons'] for island in islands)
    for island in islands:
        if island['is_linear']:
            assert all(contains_polygon(island['polygon'], hole) for hole in island['hole_polygons'])


@pytest.mark.parametrize('char,path,clip', [
    ('䯂', '0.1.1.1', [628 / 1024, 546 / 1024, 61 / 1024, 38 / 1024]),
    ('䳗', '0.0.1', [274 / 1024, 345 / 1024, 96 / 1024, 60 / 1024]),
])
def test_reversed_winding_strokes_become_standalone_islands(char, path, clip):
    tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
    visual = glyphs.build_interactive_ids_svg(tree)
    whole, masks = raster.compute_all_layer_masks(char, visual, size=256)
    region = raster.create_clip_mask([clip], size=256)
    assert (whole & region).sum() > 50
    assert (masks[path] & region).sum() > 50
