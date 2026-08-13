#!/usr/bin/env python3
"""Demonstrate only the semantic distinctions needed by QuickDraw 1--3."""
import json
from pathlib import Path

from semantic_core import (
    ACTIVE_PIXELS, BBOX_PIXELS, BYTES, COUNT, DENSITY, DURATION,
    MICROSECONDS, PERSISTENT_STORAGE, REUSE_COUNT, RUN_COUNT,
    TEMPORARY_STORAGE, Representation, LogicalObject, active_pixels,
    bbox_pixels, measured, quantity,
)


def main() -> None:
    fixture = json.loads(Path("semantic_core_fixture.json").read_text())
    region = LogicalObject("R_sparse", "Region")
    bitmap = Representation(region, "bitmap_mask")
    runs = Representation(region, "runs")
    transitions = Representation(region, "transitions")
    assert bitmap.object is runs.object is transitions.object

    active = active_pixels(region, fixture["workloads"]["sparse_sparse_intersection"]["active_pixels"])
    box = bbox_pixels(region, fixture["workloads"]["sparse_sparse_intersection"]["bbox_pixels"])
    density = active / box

    sparse = fixture["workloads"]["sparse_sparse_intersection"]
    b1_apply = measured(DURATION, MICROSECONDS, sparse["representations"]["runs"]["apply_us"],
                        str(runs), "quickdraw_region_ops_measurements.json",
                        platform=fixture["platform"], workload="sparse_sparse/intersection",
                        statistic="median")
    b1_storage = measured(PERSISTENT_STORAGE, BYTES,
                          sparse["representations"]["runs"]["storage_bytes"],
                          str(runs), "quickdraw_region_ops_measurements.json",
                          platform=fixture["platform"], workload="sparse_sparse/intersection")
    build = measured(DURATION, MICROSECONDS, 411.748, str(runs),
                     "quickdraw_region_ops_measurements.json", platform=fixture["platform"],
                     workload="sparse_sparse/intersection", phase="build_pair")
    boolean = measured(DURATION, MICROSECONDS, 1.403, "intersection(runs,runs)",
                       "quickdraw_region_ops_measurements.json", platform=fixture["platform"],
                       workload="sparse_sparse/intersection", phase="boolean_op")
    n = quantity("N", REUSE_COUNT, COUNT, "result region", "exact", "scenario parameter")
    lifecycle = build + boolean + n * b1_apply

    print("same logical object:", bitmap, runs, transitions)
    print("density:", density.render(), "=", density.evaluate({}), density.kind.name, density.unit.name)
    print("storage:", b1_storage.value, b1_storage.unit.name, b1_storage.kind.name, b1_storage.provenance.short())
    print("lifecycle:", lifecycle.render(), "kind=", lifecycle.kind.name)
    print("lifecycle at N=100:", lifecycle.evaluate({"N": 100}), lifecycle.unit.name)

    try:
        _ = quantity(3, RUN_COUNT, COUNT, region.name, "exact", "test") + build
    except TypeError as error:
        print("rejected incoherent expression:", error)
    try:
        _ = b1_storage + b1_apply
    except TypeError as error:
        print("rejected same-unit/different-kind expression:", error)
    try:
        temporary = measured(TEMPORARY_STORAGE, BYTES, 128, "boolean operation",
                             "quickdraw_region_ops_measurements.json",
                             platform=fixture["platform"], workload="sparse_sparse/intersection")
        _ = b1_storage + temporary
    except TypeError as error:
        print("rejected same-unit/different-storage-kind expression:", error)

    assert density.evaluate({}) == 1.0
    assert lifecycle.evaluate({"N": 100}) == 411.748 + 1.403 + 100 * 0.91924
    assert bitmap.object is runs.object is transitions.object
    print("semantic demonstrations: A-F passed")


if __name__ == "__main__":
    main()
