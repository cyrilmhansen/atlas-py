"""Optional live Qwen/OpenAI-compatible evaluation runner."""
import argparse
import time
from pathlib import Path

from .backend import BackendError, OpenAICompatibleBackend
from .cli import numbered_source
from .prompt import PROMPT_VERSION, build_prompt
from .validate import ValidationError, parse_and_validate


def evaluate(corpus_dir: str, report: str, base_url: str, model: str, api_key: str | None) -> None:
    backend = OpenAICompatibleBackend(base_url, model, api_key)
    rows = []
    for path in sorted(Path(corpus_dir).glob("*.md")):
        source = numbered_source(path.stem, path.read_text(encoding="utf-8"))
        started = time.monotonic()
        error = ""
        extraction = None
        try:
            raw = backend.extract(build_prompt(source.text))
            extraction = parse_and_validate(raw, source)
        except (BackendError, ValidationError, OSError, ValueError) as exc:
            error = str(exc)
        duration = time.monotonic() - started
        rows.append((path.name, extraction, error, duration))
    lines = ["# Corpus evaluation", "", f"- backend: `{base_url}`", f"- model: `{model}`", f"- prompt: `{PROMPT_VERSION}`", "", "| Source | JSON/provenance | Observations | Claims | Hypotheses | Questions | Duration (s) | Error |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    for name, extraction, error, duration in rows:
        valid = "yes" if extraction else "no"
        obs = len(extraction.observations) if extraction else 0
        claims = len(extraction.claims) if extraction else 0
        hypotheses = sum(c["status"] == "HYPOTHESIS" for c in extraction.claims) if extraction else 0
        questions = len(extraction.questions) if extraction else 0
        lines.append(f"| {name} | {valid} | {obs} | {claims} | {hypotheses} | {questions} | {duration:.3f} | {error.replace('|', '/') } |")
    lines += ["", "## Human audit", "", "- unsupported fact?", "- important omission?", "- over-generalisation?", "- useful question?", "- ontology leakage?", ""]
    Path(report).parent.mkdir(parents=True, exist_ok=True)
    Path(report).write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_dir")
    parser.add_argument("report")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key")
    args = parser.parse_args(argv)
    evaluate(args.corpus_dir, args.report, args.base_url, args.model, args.api_key)


if __name__ == "__main__":
    main()
