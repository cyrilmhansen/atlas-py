#!/usr/bin/env python3
"""Build, validate, benchmark, and record the QuickDraw BitBlt expedition."""

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
        "BitBlt.a": "331e8a5299c646fc5bde0dc7a6facff514230bbb061678b2e02514f9702aa0e8",
        "QuickDraw.p": "c1d3590c448e4e0ed536cf701e0d1f23acaa39e054cb185dfbb91929fc96a63d",
        "RgnBlt.a": "16c400510330c67c6db2b0e96601c3d9358e5ed2f13ee3c1319e7e765b06ea7f",
        "Bitmaps.a": "745f6e7fd58de49e41e5644df319363959cb9b5689dee9a3193329678a53647e",
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


def symbol_sizes():
    result = {}
    for line in output("nm", "-S", "--size-sort", "quickdraw_bitblt_experiment").splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3].startswith("qd_bitblt_r"):
            result[fields[3]] = int(fields[1], 16)
    return result


def file_hashes():
    names = ["quickdraw_bitblt.c", "quickdraw_bitblt.h",
             "quickdraw_bitblt_experiment.c", "run_quickdraw_bitblt.py",
             "Makefile"]
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in names}


def main():
    subprocess.run(["make", "clean"], cwd=ROOT, check=True)
    subprocess.run(["make", f"CFLAGS={CFLAGS}"], cwd=ROOT, check=True)
    validation = output("./quickdraw_bitblt_experiment", "--test")

    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    benchmark_cpu = affinity[0] if affinity else None
    command = ["./quickdraw_bitblt_experiment", "--benchmark"]
    if benchmark_cpu is not None and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {benchmark_cpu})
    benchmark = json.loads(output(*command))

    size_fields = output("size", "quickdraw_bitblt_experiment").splitlines()[-1].split()
    measurements = {
        "historical_source": HISTORICAL,
        "reimplementation_hashes": file_hashes(),
        "validation": {
            "result": validation,
            "directed_and_random_cases": 6298,
            "variants": 4,
            "sanitizers_checked_separately": ["address", "undefined"],
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
            "executable_bytes": (ROOT / "quickdraw_bitblt_experiment").stat().st_size,
            "sections_bytes": {
                "text": int(size_fields[0]),
                "data": int(size_fields[1]),
                "bss": int(size_fields[2]),
            },
            "variant_symbol_bytes": symbol_sizes(),
        },
        "benchmark": benchmark,
        "notes": [
            "Wall-clock is primary; algorithmic counters are gathered outside timed samples.",
            "Useful throughput counts rectangle payload, not all memory traffic.",
            "Working sets are reused and therefore predominantly cache-hot.",
            "R3 was designed only after the preserved R0-R2 preliminary measurement.",
        ],
    }
    (ROOT / "quickdraw_bitblt_measurements.json").write_text(
        json.dumps(measurements, indent=2) + "\n"
    )
    subprocess.run(["make", "clean"], cwd=ROOT, check=True)
    print(validation)
    print(f"measurements: {ROOT / 'quickdraw_bitblt_measurements.json'}")


if __name__ == "__main__":
    main()
