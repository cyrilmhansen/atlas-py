"""Small, experiment-local ChatJimmy probe; does not modify Corpus Miner."""
import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from corpus_miner.prompt import DEFAULT_REFERENCE_CONTEXT, PROMPT_VERSION, build_prompt
from corpus_miner.cli import numbered_source
from corpus_miner.validate import parse_and_validate


BASE = "http://192.168.1.188:8000"
MODEL = "Qwen3.5-0.8B-OptiQ-4bit"
API_KEY = "ABCD"


def request(prompt, max_tokens=512):
    payload = {"model": MODEL, "temperature": 0, "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": prompt}],
               "stream": False, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(BASE + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as response:
        data = json.load(response)
    data["wall_seconds"] = time.monotonic() - started
    return data


def regression(corpus, out):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(corpus.glob("*.md")):
        source = numbered_source(path.stem, path.read_text(encoding="utf-8"))
        prompt = build_prompt(source.text, DEFAULT_REFERENCE_CONTEXT)
        (out / "prompts").mkdir(exist_ok=True)
        (out / "responses").mkdir(exist_ok=True)
        (out / "prompts" / (path.name + ".prompt.txt")).write_text(prompt, encoding="utf-8")
        try:
            data = request(prompt)
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            try:
                extraction = parse_and_validate(content, source)
                valid, error = True, None
            except Exception as exc:
                valid, error = False, str(exc)
            usage = data.get("usage", {})
            artifact = {"fixture": path.name, "model": MODEL, "prompt_version": PROMPT_VERSION,
                        "thinking": "off", "max_tokens": 512, "duration": data["wall_seconds"],
                        "usage": usage, "content": content, "validation_status": "valid" if valid else "invalid",
                        "validation_error": error}
            (out / "responses" / (path.name + ".response.json")).write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            rows.append({"fixture": path.name, "valid": valid, "duration": data["wall_seconds"],
                         "usage": usage, "validation_error": error,
                         "claims": len(extraction.claims) if valid else 0,
                         "questions": len(extraction.questions) if valid else 0})
        except Exception as exc:
            rows.append({"fixture": path.name, "valid": False, "duration": None, "error": str(exc)})
    (out / "summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def concurrency(prompts, out):
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for workers in (1, 2, 4):
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda p: request(p, 256), prompts))
        elapsed = time.monotonic() - started
        records.append({"concurrency": workers, "requests": len(results), "wall_seconds": elapsed,
                        "durations": [r["wall_seconds"] for r in results],
                        "completion_tokens": [r.get("usage", {}).get("completion_tokens") for r in results]})
    (out / "concurrency.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def scout(out):
    out.mkdir(parents=True, exist_ok=True)
    items = {
        "claim-scope": "How can Atlas test whether a derived engineering claim broadens the scope of local evidence? Give candidate counterexamples and one discriminating experiment. Candidates only.",
        "region-conversion": "For QuickDraw region representations, what small experiment could test whether bitmap-to-runs conversion is worthwhile under reuse? Give competing explanations and measurable factors. Candidates only.",
        "digital-line-contract": "What implementation-level cases could distinguish digital-line contracts involving clipping, endpoint policy, and tie-breaking? Give candidate sources or tiny discriminating cases. Candidates only.",
    }
    results = []
    for name, question in items.items():
        data = request(question, 256)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        artifact = {"item": name, "model": MODEL, "thinking": "off", "max_tokens": 256,
                    "duration": data["wall_seconds"], "usage": data.get("usage", {}), "content": content}
        (out / (name + ".json")).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"item": name, "duration": data["wall_seconds"], "content": content})
    (out / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    regression(args.corpus, args.out / "regression-capped")
    prompts = [build_prompt(numbered_source(p.stem, p.read_text(encoding="utf-8")).text,
                            DEFAULT_REFERENCE_CONTEXT) for p in sorted(args.corpus.glob("*.md"))[:4]]
    concurrency(prompts, args.out / "performance")
    scout(args.out / "scout")


if __name__ == "__main__":
    main()
