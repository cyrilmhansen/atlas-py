"""Optional live Qwen/OpenAI-compatible evaluation runner."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from .backend import BackendError, OpenAICompatibleBackend, StreamResult
from .cli import numbered_source
from .prompt import DEFAULT_REFERENCE_CONTEXT, PROMPT_VERSION, build_prompt
from .validate import ValidationError, parse_and_validate


def _usage_value(usage: dict, key: str):
    value = usage.get(key)
    return value if value is not None else "n/a"


def _reasoning_tokens(usage: dict):
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict) and details.get("reasoning_tokens") is not None:
        return details["reasoning_tokens"]
    return "n/a"


def _done_line(duration: float, prompt: str, result: StreamResult | None, valid: bool) -> str:
    usage = result.usage if result else {}
    return (f"[done] {duration:.2f}s | prompt={_usage_value(usage, 'prompt_tokens')} "
            f"| completion={_usage_value(usage, 'completion_tokens')} "
            f"| total={_usage_value(usage, 'total_tokens')} "
            f"| reasoning={_reasoning_tokens(usage)} | valid={'yes' if valid else 'no'}")


def _safe_artifact_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).name)


def _thinking_label(thinking: bool | None) -> str:
    return "on" if thinking is True else "off" if thinking is False else "default"


def _context_hash(reference_context: str) -> str:
    return hashlib.sha256(reference_context.encode("utf-8")).hexdigest()


def evaluate(corpus_dir: str, report: str, base_url: str, model: str, api_key: str | None,
             stream: bool = False, quiet: bool = False, show_prompt: bool = False,
             save_prompts: str | None = None, only: list[str] | None = None,
             thinking: bool | None = None, save_responses: str | None = None,
             reference_context: str = DEFAULT_REFERENCE_CONTEXT) -> None:
    backend = OpenAICompatibleBackend(base_url, model, api_key, thinking=thinking)
    rows = []
    paths = sorted(Path(corpus_dir).glob("*.md"))
    if only:
        available = {path.name: path for path in paths}
        unknown = [name for name in only if name not in available]
        if unknown:
            raise ValueError(f"unknown fixture name(s): {', '.join(unknown)}")
        selected = set(only)
        paths = [path for path in paths if path.name in selected]
    if save_prompts:
        Path(save_prompts).mkdir(parents=True, exist_ok=True)
    if save_responses:
        Path(save_responses).mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(paths, 1):
        source = numbered_source(path.stem, path.read_text(encoding="utf-8"))
        prompt = build_prompt(source.text, reference_context=reference_context)
        if not quiet:
            print(f"=== {path.name} [{index}/{len(paths)}] ===", flush=True)
            if show_prompt:
                print("\n[prompt]", flush=True)
                print(prompt, end="", flush=True)
                if not prompt.endswith("\n"):
                    print(flush=True)
        if save_prompts:
            (Path(save_prompts) / f"{_safe_artifact_name(path.name)}.prompt.txt").write_text(prompt, encoding="utf-8")
        started = time.monotonic()
        error = ""
        extraction = None
        result = None
        try:
            if stream:
                state = {"reasoning": False, "content": False}

                def show_reasoning(text: str) -> None:
                    if not state["reasoning"]:
                        print("\n[reasoning]", flush=True)
                        state["reasoning"] = True
                    print(text, end="", flush=True)

                def show_content(text: str) -> None:
                    if not state["content"]:
                        print("\n[answer]", flush=True)
                        state["content"] = True
                    print(text, end="", flush=True)

                result = backend.extract_stream(prompt, show_reasoning, show_content)
                raw = result.content
            else:
                result = backend.extract_result(prompt)
                raw = result.content
            extraction = parse_and_validate(raw, source)
        except (BackendError, ValidationError, OSError, ValueError) as exc:
            error = str(exc)
        duration = time.monotonic() - started
        rows.append((path.name, extraction, error, duration, result))
        if save_responses:
            artifact = {
                "fixture": path.name,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "reference_context_sha256": _context_hash(reference_context),
                "thinking": _thinking_label(thinking),
                "duration": duration,
                "usage": result.usage if result else {},
                "reasoning_content": result.reasoning if result else "",
                "content": result.content if result else "",
                "validation_status": "valid" if extraction else "invalid",
                "validation_error": error or None,
                "finish_reason": result.finish_reason if result else None,
            }
            (Path(save_responses) / f"{_safe_artifact_name(path.name)}.response.json").write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not quiet:
            print(_done_line(duration, source.text, result, extraction is not None), flush=True)
    lines = ["# Corpus evaluation", "", f"- backend: `{base_url}`", f"- model: `{model}`", f"- prompt: `{PROMPT_VERSION}`", f"- reference_context_sha256: `{_context_hash(reference_context)}`", f"- thinking: `{_thinking_label(thinking)}`", f"- streaming: `{'yes' if stream else 'no'}`", "", "| Source | JSON/provenance | Observations | Claims | Hypotheses | Questions | Duration (s) | Prompt | Completion | Reasoning | Error |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for name, extraction, error, duration, result in rows:
        valid = "yes" if extraction else "no"
        obs = len(extraction.observations) if extraction else 0
        claims = len(extraction.claims) if extraction else 0
        hypotheses = sum(c["status"] == "HYPOTHESIS" for c in extraction.claims) if extraction else 0
        questions = len(extraction.questions) if extraction else 0
        usage = result.usage if result else {}
        lines.append(f"| {name} | {valid} | {obs} | {claims} | {hypotheses} | {questions} | {duration:.3f} | {_usage_value(usage, 'prompt_tokens')} | {_usage_value(usage, 'completion_tokens')} | {_reasoning_tokens(usage)} | {error.replace('|', '/') } |")
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
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--show-prompt", action="store_true")
    parser.add_argument("--save-prompts")
    parser.add_argument("--save-responses")
    parser.add_argument("--only", action="append")
    parser.add_argument("--thinking", choices=["on", "off"])
    parser.add_argument("--reference-context")
    parser.add_argument("--reference-context-file")
    args = parser.parse_args(argv)
    context = args.reference_context
    if args.reference_context_file:
        if context is not None:
            parser.error("use only one of --reference-context and --reference-context-file")
        context = Path(args.reference_context_file).read_text(encoding="utf-8")
    evaluate(args.corpus_dir, args.report, args.base_url, args.model, args.api_key, args.stream, args.quiet,
             args.show_prompt, args.save_prompts, args.only,
             None if args.thinking is None else args.thinking == "on", args.save_responses,
             DEFAULT_REFERENCE_CONTEXT if context is None else context)


if __name__ == "__main__":
    main()
