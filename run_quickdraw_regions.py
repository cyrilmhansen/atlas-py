#!/usr/bin/env python3
"""Build, validate, benchmark, and record the QuickDraw regions expedition."""

import hashlib
import json
import os
import platform
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
CFLAGS = "-O3 -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic"
HISTORICAL = {
    "repository": "https://github.com/jrk/QuickDraw.git",
    "commit": "6377ec5d89735a11b3f6e1ae728f555936c7583f",
    "files": {
        "Regions.a": "e673b7a31f029541ccfbe0415d6cf52fd60dd17cd2f936c5e8605e24baae2748",
        "RgnOp.a": "900364197e48f0445361d50839d844afc632b4942ac163cc55783a476f0abb6c",
        "SeekRgn.a": "066b2e232133bebb8e6110479423f0d4f476924136ec9a0ea9e20d37685edf67",
        "RgnBlt.a": "16c400510330c67c6db2b0e96601c3d9358e5ed2f13ee3c1319e7e765b06ea7f",
        "PackRgn.a": "67a0efddbd84ef5beaeb2adddfe53f0dbe19b4ac6b21dd68820226e7605b0727",
        "GrafTypes.a": "2d621b5233dd1f61c47e00514bf572c99b9338b66232b92aec04cbc4921e974e",
        "QuickDraw.p": "c1d3590c448e4e0ed536cf701e0d1f23acaa39e054cb185dfbb91929fc96a63d",
        "COPYRIGHT.TXT": "4d7a98ac9439bfb5ca9cd48928f62f9354de5073b1dfe8f14266015d57a19aaa",
    },
    "notice": "Copyright Apple Inc.; mirror notice limits availability to non-commercial use",
}


def output(*command):
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def cpu_model():
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        match = re.search(r"^model name\s*:\s*(.+)$", cpuinfo.read_text(), re.MULTILINE)
        if match:
            return match.group(1)
    return platform.processor() or "unknown"


def file_hashes():
    names = [
        "quickdraw_regions.c", "quickdraw_regions.h",
        "quickdraw_regions_experiment.c", "run_quickdraw_regions.py",
        "Makefile.regions", "quickdraw_bitblt.c", "quickdraw_bitblt.h",
    ]
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in names}


def symbol_sizes():
    result = {}
    for line in output("nm", "-S", "--size-sort", "quickdraw_regions_experiment").splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3].startswith("qr_g"):
            result[fields[3]] = int(fields[1], 16)
    return result


def main():
    make = ["make", "-f", "Makefile.regions"]
    subprocess.run(make + ["clean"], cwd=ROOT, check=True)
    subprocess.run(make + [f"CFLAGS={CFLAGS}"], cwd=ROOT, check=True)
    subprocess.run(make + ["test"], cwd=ROOT, check=True)

    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    benchmark_cpu = affinity[0] if affinity else None
    if benchmark_cpu is not None and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {benchmark_cpu})

    output("./quickdraw_regions_experiment", "--benchmark")  # untimed warm-up
    benchmark = json.loads(output("./quickdraw_regions_experiment", "--benchmark"))
    validation = output("./quickdraw_regions_experiment", "--test")
    size_fields = output("size", "quickdraw_regions_experiment").splitlines()[-1].split()
    measurements = {
        "historical_source": HISTORICAL,
        "reimplementation_hashes": file_hashes(),
        "validation": {
            "result": validation,
            "directed_and_random_cases": 3227,
            "variants": 4,
            "sanitizers": ["address", "undefined"],
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "cpu": cpu_model(),
            "logical_cpus": os.cpu_count(),
            "benchmark_cpu_affinity": benchmark_cpu,
            "compiler": output("cc", "--version").splitlines()[0],
            "cflags": CFLAGS,
            "libc": " ".join(platform.libc_ver()),
        },
        "generated_code": {
            "executable_bytes": (ROOT / "quickdraw_regions_experiment").stat().st_size,
            "sections_bytes": {
                "text": int(size_fields[0]),
                "data": int(size_fields[1]),
                "bss": int(size_fields[2]),
            },
            "region_symbol_bytes": symbol_sizes(),
        },
        "benchmark": benchmark,
        "notes": [
            "Wall-clock is primary; representation counters are collected outside timed samples.",
            "A complete untimed benchmark pass precedes the recorded pass.",
            "The unchanged QuickDraw-1 R3 BitBlt backend is used for rectangle and run copies.",
            "G3 was designed only after quickdraw_regions_pre_g3.json was recorded.",
            "single_use and reuse100 combine independently measured median build and apply times.",
        ],
    }
    (ROOT / "quickdraw_regions_measurements.json").write_text(
        json.dumps(measurements, indent=2) + "\n"
    )
    subprocess.run(make + ["clean"], cwd=ROOT, check=True)
    print(validation)
    print(f"measurements: {ROOT / 'quickdraw_regions_measurements.json'}")


if __name__ == "__main__":
    main()
