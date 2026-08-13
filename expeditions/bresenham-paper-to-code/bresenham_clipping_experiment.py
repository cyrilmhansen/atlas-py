"""Small, non-performance experiment for digital-line clipping.

The two variants deliberately share the same integer rasterizer.  The only
changed mechanism is whether clipping happens before or after rasterization.
"""

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from math import floor


Point = tuple[int, int]
Rect = tuple[int, int, int, int]


def raster_line(a: Point, b: Point) -> list[Point]:
    """Inclusive, all-octant Bresenham form with strict tie decisions."""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    points = []
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return points
        twice = 2 * error
        if twice > dy:
            error += dy
            x0 += sx
        if twice < dx:
            error += dx
            y0 += sy


def inside(p: Point, r: Rect) -> bool:
    x, y = p
    xmin, ymin, xmax, ymax = r
    return xmin <= x <= xmax and ymin <= y <= ymax


def full_then_mask(a: Point, b: Point, r: Rect) -> list[Point]:
    return [p for p in raster_line(a, b) if inside(p, r)]


def liang_barsky(a: Point, b: Point, r: Rect):
    """Clip the geometric segment to the closed coordinate rectangle."""
    x0, y0 = a
    x1, y1 = b
    dx, dy = x1 - x0, y1 - y0
    xmin, ymin, xmax, ymax = r
    t0, t1 = Fraction(0), Fraction(1)
    for p, q in (
        (-dx, x0 - xmin),
        (dx, xmax - x0),
        (-dy, y0 - ymin),
        (dy, ymax - y0),
    ):
        if p == 0:
            if q < 0:
                return None
            continue
        t = Fraction(q, p)
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    if t0 > t1:
        return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def round_half_up(value: Fraction) -> int:
    """Explicit geometric-to-grid convention; ties go toward +infinity."""
    return floor(value + Fraction(1, 2))


def preclip_then_raster(a: Point, b: Point, r: Rect) -> list[Point]:
    clipped = liang_barsky(a, b, r)
    if clipped is None:
        return []
    rounded = tuple(
        (round_half_up(x), round_half_up(y)) for x, y in clipped
    )
    rounded = tuple(
        (
            min(max(x, r[0]), r[2]),
            min(max(y, r[1]), r[3]),
        )
        for x, y in rounded
    )
    return raster_line(rounded[0], rounded[1])


@dataclass(frozen=True)
class Difference:
    a: Point
    b: Point
    rect: Rect
    full: list[Point]
    preclip: list[Point]


def candidates(limit: int, *, nontrivial: bool = False):
    points = list(product(range(-limit, limit + 1), repeat=2))
    rects = [
        (xmin, ymin, xmax, ymax)
        for xmin, ymin, xmax, ymax in product(
            range(-limit, limit + 1), repeat=4
        )
        if xmin <= xmax and ymin <= ymax
    ]
    for a in points:
        for b in points:
            if a == b:
                continue
            for r in rects:
                if nontrivial and (r[2] <= r[0] or r[3] <= r[1]):
                    continue
                full = full_then_mask(a, b, r)
                preclip = preclip_then_raster(a, b, r)
                clipped = liang_barsky(a, b, r)
                has_nontrivial_fraction = clipped and max(
                    value.denominator for endpoint in clipped for value in endpoint
                ) > 2
                if full != preclip and (not nontrivial or (full and preclip and has_nontrivial_fraction)):
                    yield Difference(a, b, r, full, preclip)


def first_difference(limit: int, *, nontrivial: bool = False) -> Difference | None:
    return next(candidates(limit, nontrivial=nontrivial), None)


def main() -> None:
    for nontrivial in (False, True):
        for limit in (1, 2, 3):
            result = first_difference(limit, nontrivial=nontrivial)
            print(f"nontrivial={nontrivial} search_limit={limit} found={result is not None}")
            if result is not None:
                print(result)
                break


if __name__ == "__main__":
    main()
