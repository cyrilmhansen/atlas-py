"""Experiment-local bridge for the anonymous ChatJimmy web API."""
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from corpus_miner.cli import numbered_source
from corpus_miner.prompt import DEFAULT_REFERENCE_CONTEXT, PROMPT_VERSION, build_prompt
from corpus_miner.validate import parse_and_validate


BASE = "https://chatjimmy.ai"
MODEL = "llama3.1-8B"
CHAT_OPTIONS = {"selectedModel": MODEL, "systemPrompt": "", "topK": 8}


def chat(prompt: str) -> dict:
    payload = {"messages": [{"role": "user", "content": prompt}],
               "data": {}, "chatOptions": CHAT_OPTIONS}
    request = urllib.request.Request(
        BASE + "/api/chat", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/plain"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            body = response.read().decode("utf-8", "replace")
        error = None
        status = 200
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()}
        body = exc.read().decode("utf-8", "replace")
        error = f"HTTP {exc.code}: {body[:500]}"
        status = exc.code
    return {"status": status, "headers": headers, "body": body,
            "duration": time.monotonic() - started, "error": error,
            "request": payload}


def split_stats(body: str):
    match = re.search(r"<\|stats\|>([\s\S]+?)<\|/stats\|>", body)
    if not match:
        return body, None
    try:
        stats = json.loads(match.group(1))
    except json.JSONDecodeError:
        stats = {"_parse_error": match.group(1)}
    return body[:match.start()] + body[match.end():], stats


def run_gate(corpus: Path, out: Path, names: list[str]) -> list[dict]:
    (out / "prompts").mkdir(parents=True, exist_ok=True)
    (out / "responses").mkdir(parents=True, exist_ok=True)
    rows = []
    for name in names:
        path = corpus / name
        source = numbered_source(path.stem, path.read_text(encoding="utf-8"))
        prompt = build_prompt(source.text, DEFAULT_REFERENCE_CONTEXT)
        (out / "prompts" / (name + ".prompt.txt")).write_text(prompt, encoding="utf-8")
        result = chat(prompt)
        content, stats = split_stats(result["body"])
        try:
            extraction = parse_and_validate(content, source)
            valid, validation_error = True, None
        except Exception as exc:
            extraction, valid, validation_error = None, False, str(exc)
        artifact = {"fixture": name, "model": MODEL, "prompt_version": PROMPT_VERSION,
                    "thinking": "public-default", "duration": result["duration"],
                    "status": result["status"], "headers": result["headers"],
                    "stats": stats, "content": content,
                    "validation_status": "valid" if valid else "invalid",
                    "validation_error": validation_error}
        (out / "responses" / (name + ".response.json")).write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rows.append({"fixture": name, "valid": valid, "duration": result["duration"],
                     "status": result["status"], "validation_error": validation_error,
                     "stats": stats,
                     "observations": len(extraction.observations) if extraction else 0,
                     "claims": len(extraction.claims) if extraction else 0,
                     "questions": len(extraction.questions) if extraction else 0})
    (out / "summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    gate_names = ["quicksort.md", "binary-search.md", "a1-unresolved.md",
                  "a2-resolved.md", "b1-evidence-request.md", "c2-irrelevant-absence.md"]
    run_gate(args.corpus, args.out / "semantic-gate", gate_names)


if __name__ == "__main__":
    main()
