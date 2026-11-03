"""Small polygon operations for straight-contour ink ownership.

Coordinates are normalized screen coordinates; no raster or font dependency.
"""

def clip_polygon_area(points: list[tuple[float, float]], rect: list[float]) -> float:
    """Area of a contour inside an axis-aligned clip (Sutherland–Hodgman)."""
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return 0.0
    for axis, bound, keep_above in ((0, x, True), (0, x + w, False),
                                    (1, y, True), (1, y + h, False)):
        if not points:
            return 0.0
        clipped = []
        previous = points[-1]
        previous_inside = previous[axis] >= bound if keep_above else previous[axis] <= bound
        for current in points:
            inside = current[axis] >= bound if keep_above else current[axis] <= bound
            if inside != previous_inside:
                fraction = (bound - previous[axis]) / (current[axis] - previous[axis])
                clipped.append(tuple(previous[i] + fraction * (current[i] - previous[i]) for i in (0, 1)))
            if inside:
                clipped.append(current)
            previous, previous_inside = current, inside
        points = clipped
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2


def _cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])


def _contains_point(polygon: list[tuple[float, float]], point: tuple[float, float]) -> bool:
    winding = 0
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        cross = _cross(a, b, point)
        if (abs(cross) < 1e-12 and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
                and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])):
            return True
        if a[1] <= point[1] < b[1] and cross > 0:
            winding += 1
        elif b[1] <= point[1] < a[1] and cross < 0:
            winding -= 1
    return winding != 0


def contains_polygon(outer: list[tuple[float, float]], inner: list[tuple[float, float]]) -> bool:
    """Containment including touching edges, but excluding concavity crossings."""
    if not inner or not all(_contains_point(outer, point) for point in inner):
        return False
    for a, b in zip(inner, inner[1:] + inner[:1]):
        for c, d in zip(outer, outer[1:] + outer[:1]):
            if _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0:
                return False
    return True
