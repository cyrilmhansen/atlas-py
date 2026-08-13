#!/usr/bin/env python3
"""Use Semantic Core v1 to decide whether one measured conversion amortizes."""
import json
from pathlib import Path

from semantic_core import (
    BYTES, COUNT, DURATION, MICROSECONDS, PERSISTENT_STORAGE,
    REUSE_COUNT, Representation, LogicalObject, derived_duration,
    measured, quantity, repeat,
)


SOURCE = "semantic_core_v1_measurements.json"


def break_even(with_conversion, without_conversion, limit=100000):
    for n in range(1, limit + 1):
        if with_conversion.evaluate({"N": n}) < without_conversion.evaluate({"N": n}):
            return n
    return None


def make_decision(name, data):
    region = LogicalObject(name, "Region")
    initial = Representation(region, data["source_representation"])
    target = Representation(region, data["target_representation"])
    context = {
        "platform": "AMD Ryzen AI 9 HX 370 / x86-64 Linux / GCC 16.1.1 -O3",
        "workload": name,
        "source": SOURCE,
    }
    production = measured(DURATION, MICROSECONDS, data["production_initial_us"],
                          f"produce({initial})", **context)
    conversion = measured(DURATION, MICROSECONDS, data["conversion_median_us"],
                          f"convert({initial},{target})", **context,
                          statistic="median", phase="conversion")
    apply_before = measured(DURATION, MICROSECONDS, data["apply_bitmap_us"],
                            str(initial), **context, statistic="median", phase="apply")
    apply_after = measured(DURATION, MICROSECONDS, data["apply_runs_us"],
                           str(target), **context, statistic="median", phase="apply")
    n = quantity("N", REUSE_COUNT, COUNT, "reuse of result", "exact", "scenario parameter")

    without = derived_duration(
        f"without conversion: {name}", production + repeat(n, apply_before))
    with_conversion = derived_duration(
        f"with conversion: {name}", production + conversion + repeat(n, apply_after))
    threshold = break_even(with_conversion, without)

    print(f"\n{name}")
    print(f"Region identity preserved: {data['logical_region_preserved']}")
    print(f"initial representation: {initial}")
    print(f"target representation: {target}")
    print(f"conversion: {conversion.value:.3f} {conversion.unit.name}")
    print(f"storage: {data['storage_bitmap']} -> {data['storage_runs']} {BYTES.name}")
    print(f"apply before: {apply_before.value:.5f} {apply_before.unit.name}/use")
    print(f"apply after: {apply_after.value:.5f} {apply_after.unit.name}/use")
    print("without:", without.render())
    print("with:   ", with_conversion.render())
    print("leaves:", [f"{q.kind.name}@{q.provenance.short()}" for q in with_conversion.leaves()])
    print("break-even:", threshold if threshold is not None else "none in search range")
    return threshold


def main():
    data = json.loads(Path(SOURCE).read_text())
    thresholds = {name: make_decision(name, case) for name, case in data["cases"].items()}
    assert thresholds["sparse_sparse_intersection"] is not None
    assert thresholds["fragmented_fragmented_intersection"] is not None

    try:
        region = LogicalObject("invalid", "Region")
        apply = measured(DURATION, MICROSECONDS, 1, "apply", SOURCE)
        run_count = quantity(10, __import__("semantic_core").RUN_COUNT, COUNT,
                              region.name, "exact", "negative test")
        repeat(run_count, apply)
    except TypeError as error:
        print("rejected invalid repeat:", error)

    try:
        storage = measured(PERSISTENT_STORAGE, BYTES, 100, "bitmap", SOURCE)
        apply = measured(DURATION, MICROSECONDS, 1, "apply", SOURCE)
        _ = storage + apply
    except TypeError as error:
        print("rejected conversion/storage + duration:", error)

    print("v1 conversion decision: passed")


if __name__ == "__main__":
    main()
