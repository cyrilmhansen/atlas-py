#!/usr/bin/env python3
"""Build, validate, benchmark, and record QuickDraw region operations."""
import hashlib, json, os, platform, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFLAGS = "-O3 -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic"
HISTORICAL = {
    "repository": "https://github.com/jrk/QuickDraw.git",
    "commit": "6377ec5d89735a11b3f6e1ae728f555936c7583f",
    "files": {
        "RgnOp.a": "900364197e48f0445361d50839d844afc632b4942ac163cc55783a476f0abb6c",
        "Regions.a": "e673b7a31f029541ccfbe0415d6cf52fd60dd17cd2f936c5e8605e24baae2748",
        "SeekRgn.a": "066b2e232133bebb8e6110479423f0d4f476924136ec9a0ea9e20d37685edf67",
        "PackRgn.a": "67a0efddbd84ef5beaeb2adddfe53f0dbe19b4ac6b21dd68820226e7605b0727",
        "RgnBlt.a": "16c400510330c67c6db2b0e96601c3d9358e5ed2f13ee3c1319e7e765b06ea7f",
        "GrafTypes.a": "2d621b5233dd1f61c47e00514bf572c99b9338b66232b92aec04cbc4921e974e",
        "QuickDraw.p": "c1d3590c448e4e0ed536cf701e0d1f23acaa39e054cb185dfbb91929fc96a63d",
        "COPYRIGHT.TXT": "4d7a98ac9439bfb5ca9cd48928f62f9354de5073b1dfe8f14266015d57a19aaa",
    },
    "notice": "Copyright Apple Inc.; mirror notice limits availability to non-commercial use",
}

def out(*cmd): return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()
def cpu():
    p = Path("/proc/cpuinfo")
    m = re.search(r"^model name\s*:\s*(.+)$", p.read_text(), re.M) if p.exists() else None
    return m.group(1) if m else platform.processor() or "unknown"
def hashes():
    names = ["quickdraw_region_ops.c", "quickdraw_region_ops.h", "quickdraw_region_ops_experiment.c", "run_quickdraw_region_ops.py", "Makefile.region-ops", "quickdraw_bitblt.c", "quickdraw_bitblt.h"]
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}

def main():
    make = ["make", "-f", "Makefile.region-ops"]
    subprocess.run(make + ["clean"], cwd=ROOT, check=True)
    subprocess.run(make + [f"CFLAGS={CFLAGS}"], cwd=ROOT, check=True)
    subprocess.run(make + ["test"], cwd=ROOT, check=True)
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    cpu_id = affinity[0] if affinity else None
    if cpu_id is not None and hasattr(os, "sched_setaffinity"): os.sched_setaffinity(0, {cpu_id})
    warm = json.loads(out("./quickdraw_region_ops_experiment", "--benchmark"))
    benchmark = json.loads(out("./quickdraw_region_ops_experiment", "--benchmark"))
    validation = out("./quickdraw_region_ops_experiment", "--test")
    measurements = {
        "historical_source": HISTORICAL,
        "reimplementation_hashes": hashes(),
        "validation": {"result": validation, "cases": 12800, "operations": 4, "variants": 3, "sanitizers": ["address", "undefined"]},
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "cpu": cpu(), "logical_cpus": os.cpu_count(), "benchmark_cpu_affinity": cpu_id, "compiler": out("cc", "--version").splitlines()[0], "cflags": CFLAGS, "libc": " ".join(platform.libc_ver())},
        "benchmark": benchmark,
        "notes": [
            "B0/B1/B2 only; no adaptive B3 was added after the preliminary comparison.",
            "A complete untimed benchmark pass precedes the recorded pass.",
            "Build pair, boolean operation, result storage and repeated application are reported separately.",
            "The application checksum is compared across all three variants for every case and operation.",
            "Working sets are cache-hot and the benchmark process is pinned to one logical CPU when available.",
        ],
    }
    (ROOT / "quickdraw_region_ops_measurements.json").write_text(json.dumps(measurements, indent=2) + "\n")
    subprocess.run(make + ["clean"], cwd=ROOT, check=True)
    print(validation)
    print(f"measurements: {ROOT / 'quickdraw_region_ops_measurements.json'}")

if __name__ == "__main__": main()
