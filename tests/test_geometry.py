"""Polygon containment must check ink, not just axis-aligned extents."""
from geometry import contains_polygon


def test_containment_is_independent_of_winding():
    outer = [(0,0), (1,0), (1,1), (0,1)]
    inner = [(0,0), (.5,0), (.5,.5), (0,.5)]
    assert contains_polygon(outer, inner)
    assert contains_polygon(outer[::-1], inner[::-1])
    assert not contains_polygon(inner, outer)


def test_concave_bounding_box_is_not_containment():
    outer = [(0,0),(1,0),(1,.1),(.1,.1),(.1,1),(0,1)]
    inner = [(.4,.4),(.6,.4),(.6,.6),(.4,.6)]
    assert not contains_polygon(outer, inner)


def test_edges_cannot_cross_a_concavity_even_if_all_vertices_are_inside():
    # U-shaped container; the inner rectangle bridges its empty middle.
    outer = [(0,0),(1,0),(1,1),(.8,1),(.8,.2),(.2,.2),(.2,1),(0,1)]
    inner = [(.1,.4),(.9,.4),(.9,.6),(.1,.6)]
    assert not contains_polygon(outer, inner)
    assert not contains_polygon(outer, [])
