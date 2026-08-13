#!/usr/bin/env python3
"""Measure one concrete B0 bitmap -> B1 runs conversion."""
import json
import statistics
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = "quickdraw_region_ops_measurements.json"
PLATFORM = "AMD Ryzen AI 9 HX 370 / x86-64 Linux / GCC 16.1.1 -O3"


def make_mask(case):
    width, height = 512, 256
    rows = [bytearray((width + 7) // 8) for _ in range(height)]
    if case == "sparse_sparse_intersection":
        for i in range(36):
            y = 3 + (i * 13) % (height - 5)
            left = 5 + (i * 47) % (width - 20)
            for x in range(left, min(width, left + 15 + (i % 4) * 9)):
                rows[y][x // 8] |= 0x80 >> (x & 7)
    else:
        for y in range(height):
            for x in range(width):
                if ((x // 3) + (y // 3)) & 1:
                    rows[y][x // 8] |= 0x80 >> (x & 7)
    return rows


def to_runs(rows, width=512):
    result = []
    for row in rows:
        runs = []
        x = 0
        while x < width:
            while x < width and not (row[x // 8] & (0x80 >> (x & 7))):
                x += 1
            left = x
            while x < width and (row[x // 8] & (0x80 >> (x & 7))):
                x += 1
            if left < x:
                runs.append((left, x))
        result.append(runs)
    return result


def runs_mask(runs, width=512):
    rows = [bytearray((width + 7) // 8) for _ in runs]
    for y, line in enumerate(runs):
        for left, right in line:
            for x in range(left, right):
                rows[y][x // 8] |= 0x80 >> (x & 7)
    return rows


def source_measurements():
    data = json.loads((ROOT / SOURCE).read_text())
    selected = {}
    for case in data["benchmark"]["cases"]:
        if case["name"] not in {"sparse_sparse", "fragmented_fragmented"}:
            continue
        for operation in case["operations"]:
            if operation["op"] != "intersect":
                continue
            b0 = next(v for v in operation["variants"] if v["name"] == "B0_bitmap")
            b1 = next(v for v in operation["variants"] if v["name"] == "B1_runs")
            selected[case["name"] + "_intersection"] = {
                "production_initial_us": (b0["build_pair_median_ns"] + b0["op_median_ns"]) / 1000,
                "apply_bitmap_us": b0["apply_ns_per_use"] / 1000,
                "apply_runs_us": b1["apply_ns_per_use"] / 1000,
                "storage_bitmap": b0["result"]["storage_bytes"],
                "storage_runs": b1["result"]["storage_bytes"],
            }
    return selected


def main():
    measurements = source_measurements()
    output = {"platform": PLATFORM, "source": SOURCE, "cases": {}}
    for name, base in measurements.items():
        rows = make_mask(name)
        # Warm up before the recorded samples; the conversion itself is the only timed action.
        to_runs(rows)
        samples = []
        for _ in range(31):
            start = time.perf_counter_ns()
            converted = to_runs(rows)
            samples.append(time.perf_counter_ns() - start)
        converted = to_runs(rows)
        assert runs_mask(converted) == rows
        output["cases"][name] = {
            **base,
            "conversion_median_us": statistics.median(samples) / 1000,
            "conversion_p95_us": sorted(samples)[-2] / 1000,
            "logical_region_preserved": True,
            "samples": len(samples),
            "source_representation": "bitmap",
            "target_representation": "runs",
        }
    (ROOT / "semantic_core_v1_measurements.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
