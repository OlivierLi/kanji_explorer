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


def test_edges_cannot_exit_concavity_through_reflex_vertices_or_boundary_bridges():
    # V-notch where the inner top edge exits outer through reflex vertices (0.2, 0.5) and (0.8, 0.5).
    v_notch = [(0,0),(1,0),(1,1),(0.9,1),(0.8,0.5),(0.5,0.2),(0.2,0.5),(0.1,1),(0,1)]
    bridging_reflex = [(0.1,0.5),(0.9,0.5),(0.9,0.1),(0.1,0.1)]
    assert not contains_polygon(v_notch, bridging_reflex)

    # U-slot where all four inner corners lie on the boundary walls, but the polygon spans the empty slot.
    u_shape = [(0,0),(1,0),(1,1),(.8,1),(.8,.2),(.2,.2),(.2,1),(0,1)]
    slot_bridge = [(.2,.3),(.8,.3),(.8,.9),(.2,.9)]
    assert not contains_polygon(u_shape, slot_bridge)
