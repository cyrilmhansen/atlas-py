import json
import io
import sqlite3
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from contextlib import redirect_stdout
from pathlib import Path

from corpus_miner.backend import BackendError, FakeBackend, OpenAICompatibleBackend
from corpus_miner.cli import ingest_file, numbered_source, main as cli_main
from corpus_miner.evaluate import evaluate
from corpus_miner.markdown import markdown_filename, render
from corpus_miner.models import ValidatedExtraction
from corpus_miner.models import ALLOWED_FACETS
from corpus_miner.prompt import DEFAULT_REFERENCE_CONTEXT, PROMPT_VERSION, build_prompt
from corpus_miner.storage import connect, ingest
from corpus_miner.validate import ValidationError, parse_and_validate


SOURCE_TEXT = """Local term: run fusion.
The mechanism advances the smaller endpoint.
Precondition: both inputs are ordered and disjoint internally.
Property: output intervals remain ordered.
Reference: Example, 2024.
Open question: how does fragmentation affect cost?
"""


def extraction(**changes):
    value = {
        "schema_version": 1,
        "observations": [
            {"key": "o1", "facet": "term", "statement": "The source names run fusion.", "start_line": 1, "end_line": 1},
            {"key": "o2", "facet": "mechanism", "statement": "The smaller endpoint advances.", "start_line": 2, "end_line": 2},
            {"key": "o3", "facet": "precondition", "statement": "Inputs are ordered.", "start_line": 3, "end_line": 3},
            {"key": "o4", "facet": "property", "statement": "Output is ordered.", "start_line": 4, "end_line": 4},
            {"key": "o5", "facet": "reference", "statement": "A reference is present.", "start_line": 5, "end_line": 5},
        ],
        "claims": [{"status": "DERIVED_INTERPRETATION", "statement": "The mechanism preserves order.", "supported_by": ["o2", "o4"]}],
        "questions": [{"question": "What affects cost?", "reason": "The source leaves it open.", "evidence_needed": "Measurements", "derived_from": ["o4"]}],
    }
    value.update(changes)
    return value


class CorpusMinerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = numbered_source("fixture", SOURCE_TEXT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a1_valid_full_and_markdown(self):
        parsed = parse_and_validate(json.dumps(extraction()), self.source)
        self.assertEqual(len(parsed.observations), 5)
        md = render(self.source, parsed, "fake", None, "fixture.md")
        self.assertIn("Source lines: L2–L2", md)
        db = connect(self.root / "a.db")
        accepted, _ = ingest(db, self.source, parsed, json.dumps(extraction()), "fake", None, PROMPT_VERSION, "fixture.md", None, "reference")
        self.assertTrue(accepted)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 5)

    def test_prompt_declares_every_allowed_facet(self):
        prompt = build_prompt("[L1] example")
        self.assertEqual(PROMPT_VERSION, "corpus-miner-v4")
        for facet in ALLOWED_FACETS:
            self.assertIn(facet, prompt)
        self.assertIn("MUST be exactly one of", prompt)

    def test_prompt_makes_claims_questions_optional_and_consequential(self):
        prompt = build_prompt("[L1] example")
        self.assertIn("Claims and questions are NOT quotas", prompt)
        self.assertIn("CONSEQUENCE_IF_UNKNOWN", prompt)
        self.assertIn("not always faster", prompt)
        self.assertIn("no universal", prompt)

    def test_reference_context_default_and_custom_are_explicitly_separated(self):
        default = build_prompt("[L1] source")
        self.assertIn("REFERENCE CONTEXT", default)
        self.assertIn("Atlas builds reusable engineering knowledge", default)
        self.assertIn("SOURCE answers: \"What is supported?\"", default)
        self.assertIn("REFERENCE CONTEXT answers: \"What is worth extracting?\"", default)
        self.assertIn("It is NOT evidence", default)
        self.assertIn("numbered\nSOURCE", default)
        self.assertIn("historical algorithms", default)
        self.assertEqual(DEFAULT_REFERENCE_CONTEXT.splitlines()[0],
                         "Atlas builds reusable engineering knowledge about software, algorithms, computer systems, data representations, and their implementations.")
        custom = build_prompt("[L1] source", reference_context="Only retain parser invariants.")
        self.assertIn("Only retain parser invariants.", custom)
        self.assertNotIn("Atlas builds reusable engineering knowledge about software", custom)

    def test_reference_context_does_not_create_provenance(self):
        custom = "The source contains no facts about parser invariants."
        prompt = build_prompt("[L1] Source says only this.", reference_context=custom)
        self.assertIn(custom, prompt)
        value = {"schema_version": 1, "observations": [{
            "key": "o1", "facet": "other", "statement": "Source says only this.",
            "start_line": 1, "end_line": 1}], "claims": [], "questions": []}
        parsed = parse_and_validate(json.dumps(value), numbered_source("source", "Source says only this."))
        self.assertEqual(parsed.observations[0]["start_line"], 1)

    def test_prompt_question_contract_matches_validator(self):
        prompt = build_prompt("[L1] example")
        for field in ("question", "reason", "evidence_needed", "derived_from"):
            self.assertIn(f"`{field}`", prompt)
        self.assertIn("never use", prompt)
        self.assertIn("`requested_evidence`", prompt)
        self.assertNotIn("question object\nMUST use exactly these semantic fields: `statement`", prompt)

    def test_json_transport_accepts_raw_and_one_json_fence(self):
        value = extraction(observations=[], claims=[], questions=[])
        raw = json.dumps(value)
        self.assertEqual(parse_and_validate(raw, self.source).observations, ())
        self.assertEqual(parse_and_validate("```json\n" + raw + "\n```", self.source).observations, ())
        self.assertEqual(parse_and_validate("```\n" + raw + "\n```", self.source).observations, ())
        self.assertEqual(parse_and_validate("  \n```json\n" + raw + "\n```\n  ", self.source).observations, ())

    def test_json_transport_rejects_explanatory_text_multiple_fences_and_bad_fence(self):
        raw = json.dumps({"schema_version": 1, "observations": [], "claims": [], "questions": []})
        invalid = [
            "Explanation\n```json\n" + raw + "\n```",
            "```json\n" + raw + "\n```\nExplanation",
            "```json\n" + raw + "\n```\n```json\n" + raw + "\n```",
            "```json\n{not-json}\n```",
            raw + "\ncomment",
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValidationError):
                    parse_and_validate(candidate, self.source)

    def test_explicit_source_question_may_have_no_evidence(self):
        value = {"schema_version": 1, "observations": [], "claims": [], "questions": [{
            "question": "What remains open?", "reason": "Explicitly stated by the source.",
            "evidence_needed": "The requested experiment", "derived_from": [],
        }]}
        parsed = parse_and_validate(json.dumps(value), self.source)
        self.assertEqual(parsed.questions[0]["derived_from"], [])

    def test_explicit_question_evidence_uses_canonical_field(self):
        value = {"schema_version": 1, "observations": [], "claims": [], "questions": [{
            "question": "When does X become worthwhile?",
            "reason": "Explicitly stated by the source.",
            "evidence_needed": "benchmark Y",
            "derived_from": [],
        }]}
        parsed = parse_and_validate(json.dumps(value), self.source)
        question = parsed.questions[0]
        self.assertEqual(question["question"], "When does X become worthwhile?")
        self.assertEqual(question["evidence_needed"], "benchmark Y")
        self.assertNotIn("requested_evidence", question)

    def test_markdown_filename_is_deterministic_and_safe(self):
        self.assertEqual(markdown_filename("nist/binary search: v1", "a" * 64),
                         "nist-binary-search-v1--aaaaaaaaaaaa.md")
        self.assertEqual(markdown_filename("/ ???", "b" * 64), "source--bbbbbbbbbbbb.md")

    def test_two_hashes_have_two_names(self):
        self.assertNotEqual(markdown_filename("source-a", "1" * 64),
                             markdown_filename("source-a", "2" * 64))

    def test_end_to_end_two_versions_keep_two_markdown_files(self):
        source_path = self.root / "source.md"
        source_path.write_text(SOURCE_TEXT, encoding="utf-8")
        output = self.root / "out"
        backend = FakeBackend(extraction())
        db_path = str(self.root / "db.sqlite")
        ingest_file(str(source_path), "source/a", "reference", db_path, str(output), "fake", None, backend=backend)
        first = numbered_source("source/a", SOURCE_TEXT)
        changed_text = SOURCE_TEXT + "Changed version.\n"
        source_path.write_text(changed_text, encoding="utf-8")
        ingest_file(str(source_path), "source/a", "reference", db_path, str(output), "fake", None, backend=backend)
        second = numbered_source("source/a", changed_text)
        self.assertEqual(sorted(p.name for p in output.glob("*.md")), sorted([
            markdown_filename("source/a", first.content_hash),
            markdown_filename("source/a", second.content_hash),
        ]))
        db = connect(db_path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM corpus_entries").fetchone()[0], 2)
        self.assertEqual(db.execute("SELECT id FROM sources WHERE id=?", ("source/a",)).fetchone()[0], "source/a")
        self.assertIn(first.content_hash, (output / markdown_filename("source/a", first.content_hash)).read_text(encoding="utf-8"))
        self.assertIn(second.content_hash, (output / markdown_filename("source/a", second.content_hash)).read_text(encoding="utf-8"))

    def test_identical_reingestion_is_noop_and_force_replaces_own_file(self):
        source_path = self.root / "source.md"
        source_path.write_text(SOURCE_TEXT, encoding="utf-8")
        output = self.root / "out"
        db_path = str(self.root / "db.sqlite")
        backend = FakeBackend(extraction())
        ingest_file(str(source_path), "source", "reference", db_path, str(output), "fake", None, backend=backend)
        source = numbered_source("source", SOURCE_TEXT)
        target = output / markdown_filename("source", source.content_hash)
        original = target.read_text(encoding="utf-8")
        ingest_file(str(source_path), "source", "reference", db_path, str(output), "fake", None, backend=backend)
        self.assertEqual(len(list(output.glob("*.md"))), 1)
        target.write_text("stale", encoding="utf-8")
        ingest_file(str(source_path), "source", "reference", db_path, str(output), "fake", None,
                    force=True, backend=backend)
        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertEqual(len(list(output.glob("*.md"))), 1)
        self.assertEqual(connect(db_path).execute("SELECT COUNT(*) FROM corpus_entries").fetchone()[0], 1)

    def test_original_source_id_is_in_markdown(self):
        source_path = self.root / "source.md"
        source_path.write_text(SOURCE_TEXT, encoding="utf-8")
        output = self.root / "out"
        ingest_file(str(source_path), "folder/source name", "reference", str(self.root / "db.sqlite"), str(output), "fake", None,
                    backend=FakeBackend(extraction()))
        markdown = next(output.glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("# Corpus entry: folder/source name", markdown)
        self.assertIn(numbered_source("folder/source name", SOURCE_TEXT).content_hash, markdown)

    def test_a2_invalid_json(self):
        with self.assertRaises(ValidationError): parse_and_validate("{", self.source)

    def test_a3_missing_locator(self):
        value = extraction(); del value["observations"][0]["start_line"]
        with self.assertRaises(ValidationError): parse_and_validate(json.dumps(value), self.source)

    def test_a4_out_of_range(self):
        value = extraction(); value["observations"][0]["end_line"] = 99
        with self.assertRaises(ValidationError): parse_and_validate(json.dumps(value), self.source)

    def test_a5_broken_evidence(self):
        value = extraction(); value["claims"][0]["supported_by"] = ["o99"]
        with self.assertRaises(ValidationError): parse_and_validate(json.dumps(value), self.source)

    def test_a6_hypothesis_preserved(self):
        value = extraction(); value["claims"][0]["status"] = "HYPOTHESIS"
        parsed = parse_and_validate(json.dumps(value), self.source)
        self.assertEqual(parsed.claims[0]["status"], "HYPOTHESIS")

    def test_a7_question_persisted(self):
        parsed = parse_and_validate(json.dumps(extraction()), self.source)
        self.assertEqual(parsed.questions[0]["evidence_needed"], "Measurements")

    def test_a8_idempotence(self):
        db = connect(self.root / "a.db"); parsed = parse_and_validate(json.dumps(extraction()), self.source)
        args = (parsed, json.dumps(extraction()), "fake", None, PROMPT_VERSION, "fixture.md", None, "reference")
        self.assertTrue(ingest(db, self.source, *args)[0]); self.assertFalse(ingest(db, self.source, *args)[0])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM corpus_entries").fetchone()[0], 1)

    def test_a9_changed_source_is_new_version(self):
        db = connect(self.root / "a.db"); parsed = parse_and_validate(json.dumps(extraction()), self.source)
        args = (parsed, json.dumps(extraction()), "fake", None, PROMPT_VERSION, "fixture.md", None, "reference")
        ingest(db, self.source, *args)
        changed = numbered_source("fixture", SOURCE_TEXT + "New line.\n")
        parsed2 = parse_and_validate(json.dumps(extraction()), changed)
        ingest(db, changed, parsed2, json.dumps(extraction()), "fake", None, PROMPT_VERSION, "fixture.md", None, "reference")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM corpus_entries").fetchone()[0], 2)

    def test_a10_storage_rolls_back(self):
        db = connect(self.root / "a.db"); parsed = parse_and_validate(json.dumps(extraction()), self.source)
        db.execute("CREATE TRIGGER fail_claims BEFORE INSERT ON claims BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): ingest(db, self.source, parsed, "raw", "fake", None, PROMPT_VERSION, "fixture.md", None, "reference")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM corpus_entries").fetchone()[0], 0)

    def test_a11_backend_error_has_no_storage(self):
        db = connect(self.root / "a.db")
        with self.assertRaises(BackendError):
            OpenAICompatibleBackend("http://127.0.0.1:1", "test", timeout=0.1).extract("prompt")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0], 0)

    def test_openai_compatible_backend(self):
        response = json.dumps({"choices": [{"message": {"content": json.dumps(extraction())}}]}).encode()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.end_headers(); self.wfile.write(response)
            def log_message(self, *_args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            raw = OpenAICompatibleBackend(f"http://127.0.0.1:{server.server_port}", "test").extract("prompt")
            self.assertEqual(parse_and_validate(raw, self.source).claims[0]["status"], "DERIVED_INTERPRETATION")
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_thinking_on_off_and_default_payloads(self):
        requests = []
        response = json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(response)
            def log_message(self, *_args): pass
        server = HTTPServer(("127.0.0.1", 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            OpenAICompatibleBackend(base, "test", thinking=True).extract("p1")
            OpenAICompatibleBackend(base, "test", thinking=False).extract("p2")
            OpenAICompatibleBackend(base, "test").extract("p3")
            self.assertEqual(requests[0]["chat_template_kwargs"], {"enable_thinking": True})
            self.assertEqual(requests[1]["chat_template_kwargs"], {"enable_thinking": False})
            self.assertNotIn("chat_template_kwargs", requests[2])
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_evaluation_selection_prompt_and_response_artifacts(self):
        corpus = self.root / "corpus"
        corpus.mkdir()
        (corpus / "02-second.md").write_text("second", encoding="utf-8")
        (corpus / "01-first.md").write_text("first", encoding="utf-8")
        prompts = self.root / "prompts"
        responses = self.root / "responses"
        requests = []
        response = json.dumps({"choices": [{"message": {
            "reasoning_content": "private reasoning",
            "content": '{"schema_version":1,"observations":[],"claims":[],"questions":[]}',
        }}], "usage": {"prompt_tokens": 3}}).encode()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(response)
            def log_message(self, *_args): pass
        server = HTTPServer(("127.0.0.1", 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                evaluate(str(corpus), str(self.root / "report.md"), f"http://127.0.0.1:{server.server_port}", "test", None,
                         stream=False, show_prompt=True, save_prompts=str(prompts), only=["02-second.md", "01-first.md"],
                         thinking=True, save_responses=str(responses), concurrency=2)
        finally:
            server.shutdown(); thread.join(); server.server_close()
        self.assertEqual(len(requests), 2)
        self.assertIn("[prompt]", output.getvalue())
        self.assertIn(build_prompt(numbered_source("first", "first").text), output.getvalue())
        self.assertEqual({request["messages"][0]["content"] for request in requests}, {
            (prompts / "01-first.md.prompt.txt").read_text(encoding="utf-8"),
            (prompts / "02-second.md.prompt.txt").read_text(encoding="utf-8"),
        })
        self.assertTrue(all(request["chat_template_kwargs"] == {"enable_thinking": True} for request in requests))
        artifact = json.loads((responses / "01-first.md.response.json").read_text(encoding="utf-8"))
        self.assertEqual(artifact["reasoning_content"], "private reasoning")
        self.assertNotIn("private reasoning", artifact["content"])
        self.assertEqual(artifact["validation_status"], "valid")
        report = (self.root / "report.md").read_text(encoding="utf-8")
        self.assertIn("- thinking: `on`", report)
        self.assertIn("- streaming: `no`", report)
        self.assertIn("- concurrency: `2`", report)
        self.assertIn("- prompt: `corpus-miner-v4`", report)

    def test_evaluation_unknown_fixture_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(str(self.root), str(self.root / "report.md"), "http://127.0.0.1:1", "test", None,
                     only=["missing.md"])

    def test_concurrency_default_one_and_parallel_results_are_ordered(self):
        corpus = self.root / "concurrent-corpus"
        corpus.mkdir()
        for marker in "ABC":
            (corpus / f"{marker}.md").write_text(marker, encoding="utf-8")

        class ControlledResponse:
            def __init__(self, barrier=None, delays=None, fail=None):
                self.barrier = barrier
                self.delays = delays or {}
                self.fail = fail
                self.lock = threading.Lock()
                self.active = 0
                self.max_active = 0
                self.completed = []
                self.prompts = []

            def __call__(self, prompt):
                marker = next(value for value in "ABC" if f"[L1] {value}" in prompt)
                with self.lock:
                    self.prompts.append(prompt)
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                try:
                    if self.fail == marker:
                        raise RuntimeError(f"synthetic failure for {marker}")
                    if self.barrier:
                        self.barrier.wait(timeout=3)
                    time.sleep(self.delays.get(marker, 0))
                    return json.dumps({
                        "schema_version": 1,
                        "observations": [{"key": "o1", "facet": "term",
                                           "statement": f"fixture {marker}",
                                           "start_line": 1, "end_line": 1}],
                        "claims": [], "questions": [],
                    })
                finally:
                    with self.lock:
                        self.active -= 1
                        self.completed.append(marker)

        sequential = ControlledResponse()
        sequential_report = self.root / "sequential.md"
        evaluate(str(corpus), str(sequential_report), "unused", "test", None,
                 save_prompts=str(self.root / "sequential-prompts"),
                 save_responses=str(self.root / "sequential-responses"),
                 reference_context="concurrency test context", backend_factory=lambda: FakeBackend(sequential))
        self.assertEqual(sequential.max_active, 1)
        self.assertIn("- concurrency: `1`", sequential_report.read_text(encoding="utf-8"))

        parallel = ControlledResponse(barrier=threading.Barrier(3), delays={"A": 0.08, "B": 0.04, "C": 0.0})
        parallel_report = self.root / "parallel.md"
        evaluate(str(corpus), str(parallel_report), "unused", "test", None, concurrency=3,
                 save_prompts=str(self.root / "parallel-prompts"),
                 save_responses=str(self.root / "parallel-responses"),
                 thinking=False, reference_context="concurrency test context",
                 backend_factory=lambda: FakeBackend(parallel))
        self.assertGreaterEqual(parallel.max_active, 2)
        self.assertEqual(parallel.completed, ["C", "B", "A"])
        report = parallel_report.read_text(encoding="utf-8")
        self.assertLess(report.index("| A.md |"), report.index("| B.md |"))
        self.assertLess(report.index("| B.md |"), report.index("| C.md |"))
        self.assertIn("- concurrency: `3`", report)
        for marker in "ABC":
            prompt = (self.root / "parallel-prompts" / f"{marker}.md.prompt.txt").read_text(encoding="utf-8")
            self.assertIn(f"[L1] {marker}", prompt)
            artifact = json.loads((self.root / "parallel-responses" / f"{marker}.md.response.json").read_text(encoding="utf-8"))
            self.assertIn(f'"statement": "fixture {marker}"', artifact["content"])
            self.assertEqual(artifact["thinking"], "off")
            self.assertEqual(artifact["validation_status"], "valid")
        self.assertEqual(len(list((self.root / "parallel-responses").glob("*.json"))), 3)

    def test_concurrent_failure_isolated_and_reference_context_preserved(self):
        corpus = self.root / "failure-corpus"
        corpus.mkdir()
        for marker in "ABC":
            (corpus / f"{marker}.md").write_text(marker, encoding="utf-8")

        class Response:
            def __call__(self, prompt):
                marker = next(value for value in "ABC" if f"[L1] {value}" in prompt)
                if "Only this reference context" not in prompt:
                    raise AssertionError("reference context was not applied")
                if marker == "B":
                    raise RuntimeError("synthetic backend failure")
                return json.dumps({"schema_version": 1, "observations": [], "claims": [], "questions": []})

        report = self.root / "failure.md"
        evaluate(str(corpus), str(report), "unused", "test", None, concurrency=3,
                 save_responses=str(self.root / "failure-responses"),
                 reference_context="Only this reference context", backend_factory=lambda: FakeBackend(Response()))
        content = report.read_text(encoding="utf-8")
        self.assertIn("| A.md | yes |", content)
        self.assertIn("| B.md | no |", content)
        self.assertIn("synthetic backend failure", content)
        self.assertIn("| C.md | yes |", content)
        self.assertEqual(len(list((self.root / "failure-responses").glob("*.json"))), 3)

    def test_invalid_concurrency_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(str(self.root), str(self.root / "report.md"), "unused", "test", None, concurrency=0)
        with self.assertRaises(SystemExit):
            cli_main(["evaluate", str(self.root), str(self.root / "report.md"),
                      "--base-url", "unused", "--model", "test", "--concurrency", "0"])

    def test_stream_sse_reconstructs_reasoning_content_and_usage(self):
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "think-1"}, "finish_reason": None}]},
            {"choices": [{"delta": {"reasoning_content": " think-2"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": '{"schema_version":1,'}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": '"observations":[],"claims":[],"questions":[]}'}, "finish_reason": "stop"}]},
            {"usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
                        "completion_tokens_details": {"reasoning_tokens": 3}}},
        ]
        lines = ["data: " + json.dumps(chunk) for chunk in chunks] + ["data: [DONE]"]

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.seen_stream = request.get("stream")
                self.server.seen_options = request.get("stream_options")
                self.server.seen_thinking = request.get("chat_template_kwargs")
                self.send_response(200); self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for line in lines:
                    self.wfile.write((line + "\n\n").encode()); self.wfile.flush()
            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        reasoning, content = [], []
        try:
            result = OpenAICompatibleBackend(f"http://127.0.0.1:{server.server_port}", "test", thinking=False).extract_stream(
                "prompt", reasoning.append, content.append)
            self.assertEqual("".join(reasoning), "think-1 think-2")
            self.assertEqual("".join(content), result.content)
            parsed = parse_and_validate(result.content, self.source)
            self.assertEqual(len(parsed.observations), 0)
            self.assertEqual(result.usage["total_tokens"], 18)
            self.assertTrue(server.seen_stream)
            self.assertEqual(server.seen_options, {"include_usage": True})
            self.assertEqual(server.seen_thinking, {"enable_thinking": False})
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_stream_sse_without_reasoning_and_usage_only_chunk(self):
        lines = [
            "",
            "data: " + json.dumps({"choices": [{"delta": {"content": "{}"}}]}),
            "data: " + json.dumps({"usage": {"prompt_tokens": 2}}),
            "data: [DONE]",
        ]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                for line in lines: self.wfile.write((line + "\n\n").encode())
            def log_message(self, *_args): pass
        server = HTTPServer(("127.0.0.1", 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            result = OpenAICompatibleBackend(f"http://127.0.0.1:{server.server_port}", "test").extract_stream("prompt")
            self.assertEqual(result.reasoning, "")
            self.assertEqual(result.content, "{}")
            self.assertEqual(result.usage["prompt_tokens"], 2)
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_stream_sse_invalid_json_is_backend_error(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                self.wfile.write(b"data: {not-json}\n\n")
            def log_message(self, *_args): pass
        server = HTTPServer(("127.0.0.1", 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with self.assertRaises(BackendError):
                OpenAICompatibleBackend(f"http://127.0.0.1:{server.server_port}", "test").extract_stream("prompt")
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_a12_markdown_deterministic(self):
        parsed = parse_and_validate(json.dumps(extraction()), self.source)
        self.assertEqual(render(self.source, parsed, "fake", None, "x"), render(self.source, parsed, "fake", None, "x"))

    def test_a13_empty_observations(self):
        value = extraction(observations=[], claims=[], questions=[])
        self.assertEqual(len(parse_and_validate(json.dumps(value), self.source).observations), 0)

    def test_empty_source_can_have_no_knowledge(self):
        empty = numbered_source("empty", "")
        value = {"schema_version": 1, "observations": [], "claims": [], "questions": []}
        self.assertEqual(len(parse_and_validate(json.dumps(value), empty).observations), 0)


if __name__ == "__main__": unittest.main()
