import argparse
import hashlib
import json
import os
from pathlib import Path

from .backend import FakeBackend, OpenAICompatibleBackend
from .markdown import markdown_filename, render
from .models import NumberedSource
from .prompt import DEFAULT_REFERENCE_CONTEXT, PROMPT_VERSION, build_prompt
from .storage import connect, ingest
from .validate import ValidationError, parse_and_validate


MAX_SOURCE_CHARS = 100_000


def numbered_source(source_id: str, text: str) -> NumberedSource:
    lines = tuple(text.splitlines())
    numbered = "\n".join(f"[L{i}] {line}" for i, line in enumerate(lines, 1))
    return NumberedSource(source_id, numbered, lines, hashlib.sha256(text.encode("utf-8")).hexdigest())


def ingest_file(path: str, source_id: str, kind: str | None, db_path: str, output_dir: str,
                backend_name: str, model: str | None, force: bool = False, backend=None,
                fake_response: str | None = None, max_source_chars: int = MAX_SOURCE_CHARS,
                reference_context: str = DEFAULT_REFERENCE_CONTEXT) -> int:
    text = Path(path).read_text(encoding="utf-8")
    if len(text) > max_source_chars:
        raise ValueError(f"source exceeds configured limit of {max_source_chars} characters")
    source = numbered_source(source_id, text)
    prompt = build_prompt(source.text, reference_context=reference_context)
    backend = backend or make_backend(backend_name, model, fake_response)
    raw = backend.extract(prompt)
    extraction = parse_and_validate(raw, source)
    filename = markdown_filename(source_id, source.content_hash)
    markdown = render(source, extraction, backend.name, model, filename, str(Path(path)))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    target = output / filename
    db = connect(db_path)
    try:
        accepted, entry_id = ingest(db, source, extraction, raw, backend.name, model, PROMPT_VERSION,
                                    str(Path(path)), None, kind, force)
        if accepted:
            target.write_text(markdown, encoding="utf-8")
    finally:
        db.close()
    print(json.dumps({"accepted": accepted, "corpus_entry_id": entry_id, "source_id": source_id}, ensure_ascii=False))
    return 0


def make_backend(name: str, model: str | None, fake_response: str | None = None):
    if name == "fake":
        if fake_response is None:
            raise ValueError("CLI fake backend requires --fake-response")
        return FakeBackend(Path(fake_response).read_text(encoding="utf-8"))
    if name == "openai":
        base = os.environ.get("ATLAS_LLM_BASE_URL")
        selected = model or os.environ.get("ATLAS_LLM_MODEL")
        if not base or not selected:
            raise ValueError("openai backend requires ATLAS_LLM_BASE_URL and ATLAS_LLM_MODEL")
        return OpenAICompatibleBackend(base, selected, os.environ.get("ATLAS_LLM_API_KEY"))
    raise ValueError(f"unknown backend: {name}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="corpus_miner")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_parser = sub.add_parser("ingest")
    ingest_parser.add_argument("path")
    ingest_parser.add_argument("--source-id", required=True)
    ingest_parser.add_argument("--kind")
    ingest_parser.add_argument("--db", default="state/corpus.db")
    ingest_parser.add_argument("--out", default="corpus/extracted")
    ingest_parser.add_argument("--backend", choices=["fake", "openai"], default="openai")
    ingest_parser.add_argument("--model")
    ingest_parser.add_argument("--force", action="store_true")
    ingest_parser.add_argument("--fake-response", help="JSON response file for the deterministic fake backend")
    ingest_parser.add_argument("--max-source-chars", type=int, default=MAX_SOURCE_CHARS)
    ingest_parser.add_argument("--reference-context")
    ingest_parser.add_argument("--reference-context-file")
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("corpus_dir")
    evaluate_parser.add_argument("report")
    evaluate_parser.add_argument("--base-url", required=True)
    evaluate_parser.add_argument("--model", required=True)
    evaluate_parser.add_argument("--api-key")
    evaluate_parser.add_argument("--stream", action="store_true")
    evaluate_parser.add_argument("--quiet", action="store_true")
    evaluate_parser.add_argument("--show-prompt", action="store_true")
    evaluate_parser.add_argument("--save-prompts")
    evaluate_parser.add_argument("--save-responses")
    evaluate_parser.add_argument("--only", action="append")
    evaluate_parser.add_argument("--thinking", choices=["on", "off"])
    evaluate_parser.add_argument("--reference-context")
    evaluate_parser.add_argument("--reference-context-file")
    args = parser.parse_args(argv)
    if args.command == "ingest":
        try:
            context = args.reference_context
            if args.reference_context_file:
                if context is not None:
                    parser.error("use only one of --reference-context and --reference-context-file")
                context = Path(args.reference_context_file).read_text(encoding="utf-8")
            return ingest_file(args.path, args.source_id, args.kind, args.db, args.out, args.backend, args.model, args.force,
                               fake_response=args.fake_response, max_source_chars=args.max_source_chars,
                               reference_context=DEFAULT_REFERENCE_CONTEXT if context is None else context)
        except (OSError, ValueError, ValidationError) as exc:
            parser.error(str(exc))
    if args.command == "evaluate":
        from .evaluate import evaluate
        try:
            context = args.reference_context
            if args.reference_context_file:
                if context is not None:
                    parser.error("use only one of --reference-context and --reference-context-file")
                context = Path(args.reference_context_file).read_text(encoding="utf-8")
            evaluate(args.corpus_dir, args.report, args.base_url, args.model, args.api_key, args.stream, args.quiet,
                     args.show_prompt, args.save_prompts, args.only,
                     None if args.thinking is None else args.thinking == "on", args.save_responses,
                     DEFAULT_REFERENCE_CONTEXT if context is None else context)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    return 0


if __name__ == "__main__":
    main()
