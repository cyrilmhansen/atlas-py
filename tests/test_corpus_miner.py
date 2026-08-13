import json
import sqlite3
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from pathlib import Path

from corpus_miner.backend import BackendError, FakeBackend, OpenAICompatibleBackend
from corpus_miner.cli import ingest_file, numbered_source
from corpus_miner.markdown import markdown_filename, render
from corpus_miner.models import ValidatedExtraction
from corpus_miner.prompt import PROMPT_VERSION
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
