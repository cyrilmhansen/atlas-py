#!/usr/bin/env python3
"""Reproduce the native B0-result -> B1 conversion experiment."""
import json
import hashlib
import os
import platform
import subprocess
import sys


MAKE = ["make", "-f", "Makefile.semantic-core-v1-native"]


def run(cmd, env=None):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)


def main():
    run(MAKE + ["clean"])
    run(MAKE + ["all", "CC=cc", "CFLAGS=-O3 -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic"])
    native = run(["./semantic_core_v1_native_conversion"])
    run(MAKE + ["sanitize"] , env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})
    data = json.loads(native.stdout)
    data["experiment"] = "semantic-core-v1-native-b0-to-b1"
    data["implementation"] = {
        "executable": "semantic_core_v1_native_conversion",
        "sources": [
            "semantic_core_v1_native_conversion.c",
            "quickdraw_region_ops.c",
            "quickdraw_bitblt.c",
        ],
        "compiler": "cc",
        "cflags": "-O3 -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic",
        "sanitizers": "address,undefined",
        "compiler_version": run(["cc", "--version"]).stdout.splitlines()[0],
    }
    data["source_sha256"] = {
        name: hashlib.sha256(open(name, "rb").read()).hexdigest()
        for name in data["implementation"]["sources"]
    }
    data["platform"] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_affinity": "CPU 0 requested by executable",
    }
    data["protocol"] = {
        "timer": "CLOCK_MONOTONIC_RAW",
        "samples": 31,
        "warmup": 1,
        "apply_batch": 100,
        "statistic": "median of 31 samples; application median divided by batch",
        "result_chain": "inputs -> B0 build/op -> exact B0 result -> B1 conversion -> apply",
    }
    with open("semantic_core_v1_native_measurements.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
