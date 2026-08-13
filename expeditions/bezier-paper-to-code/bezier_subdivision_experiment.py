"""Small discriminating experiment: exact subdivision versus a chord."""

from __future__ import annotations

import json
from pathlib import Path


Point = tuple[float, float]


def mix(a: Point, b: Point, t: float) -> Point:
    return ((1.0 - t) * a[0] + t * b[0], (1.0 - t) * a[1] + t * b[1])


def cubic(points: tuple[Point, Point, Point, Point], t: float) -> Point:
    a, b, c, d = points
    ab, bc, cd = mix(a, b, t), mix(b, c, t), mix(c, d, t)
    abc, bcd = mix(ab, bc, t), mix(bc, cd, t)
    return mix(abc, bcd, t)


def split_half(points: tuple[Point, Point, Point, Point]) -> tuple[
    tuple[Point, Point, Point, Point], tuple[Point, Point, Point, Point]
]:
    a, b, c, d = points
    ab, bc, cd = mix(a, b, 0.5), mix(b, c, 0.5), mix(c, d, 0.5)
    abc, bcd = mix(ab, bc, 0.5), mix(bc, cd, 0.5)
    middle = mix(abc, bcd, 0.5)
    return (a, ab, abc, middle), (middle, bcd, cd, d)


def main() -> None:
    curve = ((0.0, 0.0), (0.0, 3.0), (3.0, 3.0), (3.0, 0.0))
    left, right = split_half(curve)
    original_quarter = cubic(curve, 0.25)
    left_midpoint = cubic(left, 0.5)
    original_three_quarters = cubic(curve, 0.75)
    right_midpoint = cubic(right, 0.5)
    chord_midpoint = mix(curve[0], curve[3], 0.5)

    result = {
        "curve": curve,
        "subdivision_parameter": 0.5,
        "exact_checks": {
            "left_midpoint_equals_original_quarter":
                left_midpoint == original_quarter,
            "right_midpoint_equals_original_three_quarters":
                right_midpoint == original_three_quarters,
        },
        "points": {
            "curve_at_0.5": cubic(curve, 0.5),
            "chord_midpoint": chord_midpoint,
        },
        "chord_midpoint_euclidean_error":
            ((cubic(curve, 0.5)[0] - chord_midpoint[0]) ** 2
             + (cubic(curve, 0.5)[1] - chord_midpoint[1]) ** 2) ** 0.5,
    }
    Path(__file__).with_name("bezier_subdivision_experiment.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
