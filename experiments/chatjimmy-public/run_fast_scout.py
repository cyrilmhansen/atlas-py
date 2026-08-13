"""Candidate-only Semantic Spider scout experiment for public ChatJimmy."""
import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


BASE = "https://chatjimmy.ai/api/chat"
MODEL = "llama3.1-8B"
OPTIONS = {"selectedModel": MODEL, "systemPrompt": "", "topK": 8}

TENSIONS = {
    "region-lifecycle": """Atlas evidence: QuickDraw 3 measured B0 bitmap, B1 runs, and B2 transitions. B0 is often fast for boolean combination, B1 can apply sparse results quickly, and B2 can reduce storage. Native B0-to-B1 conversion was measured for one reuse decision; other conversion and lifecycle cases remain open. Produce three concise candidate research moves, each with its likely discriminating observation. Candidates only; do not assert new Atlas knowledge.""",
    "claim-scope": """Atlas evidence: Corpus Miner audits repeatedly found local observations broadened into claims such as PRIMARY, generally, or a universal decision rule. A later investigation retained a rule that derived claims may combine observations but must not strengthen scope, modality, comparison, or causal force without evidence. Produce three candidate counterexamples or tests that could challenge this rule. Candidates only.""",
    "digital-line-contract": """Atlas evidence: Bresenham research found that tie-breaking, traversal direction, endpoint policy, clipping, and polyline composition can be separate digital-line contract dimensions. Several remain knowledge rather than formal ontology. Produce three candidate implementation cases or authoritative source directions that could distinguish these contracts. Candidates only.""",
    "cross-domain-transfer": """Atlas evidence: QuickDraw B1 intersection can be described locally; ordered_merge is structurally correspondent but initially added no new knowledge. The current open issue is when a cross-domain correspondence transfers a useful invariant, complexity property, variant, or counterexample rather than merely a synonym. Produce three candidate tests for useful transfer. Candidates only.""",
}


def request(prompt: str) -> dict:
    payload = {"messages": [{"role": "user", "content": prompt}],
               "data": {}, "chatOptions": OPTIONS}
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/plain"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
            return {"status": response.status, "duration": time.monotonic() - started,
                    "body": body, "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "duration": time.monotonic() - started,
                "body": exc.read().decode("utf-8", "replace"), "error": str(exc)}
    except Exception as exc:
        return {"status": None, "duration": time.monotonic() - started,
                "body": "", "error": str(exc)}


def run_calls(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for tension, context in TENSIONS.items():
        for index in range(1, 5):
            result = request(context)
            artifact = {"tension": tension, "call": index, "model": MODEL,
                        "prompt": context, **result}
            path = out / tension
            path.mkdir(exist_ok=True)
            (path / f"call-{index}.json").write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            rows.append({"tension": tension, "call": index, "status": result["status"],
                         "duration": result["duration"], "error": result["error"]})
    (out / "call-summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def run_concurrency(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    prompts = list(TENSIONS.values()) * 2
    rows = []
    for workers in (1, 2, 4, 8):
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(request, prompts))
        rows.append({"concurrency": workers, "requests": len(results),
                     "wall_seconds": time.monotonic() - started,
                     "successful": sum(r["status"] == 200 for r in results),
                     "statuses": [r["status"] for r in results],
                     "durations": [r["duration"] for r in results]})
    (out / "concurrency.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    run_calls(args.out / "calls")
    run_concurrency(args.out / "performance")


if __name__ == "__main__":
    main()
