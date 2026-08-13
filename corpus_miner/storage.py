import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import NumberedSource, ValidatedExtraction


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, title TEXT, kind TEXT, locator TEXT NOT NULL, content_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corpus_entries (
 id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(source_id, content_hash), FOREIGN KEY(source_id) REFERENCES sources(id)
);
CREATE TABLE IF NOT EXISTS extraction_runs (
 id INTEGER PRIMARY KEY, corpus_entry_id INTEGER NOT NULL, backend TEXT NOT NULL, model TEXT,
 prompt_version TEXT NOT NULL, response_hash TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(corpus_entry_id) REFERENCES corpus_entries(id)
);
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, local_key TEXT NOT NULL, facet TEXT NOT NULL,
 statement TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
 UNIQUE(run_id, local_key), FOREIGN KEY(run_id) REFERENCES extraction_runs(id)
);
CREATE TABLE IF NOT EXISTS claims (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, status TEXT NOT NULL, statement TEXT NOT NULL,
 FOREIGN KEY(run_id) REFERENCES extraction_runs(id)
);
CREATE TABLE IF NOT EXISTS claim_evidence (
 claim_id INTEGER NOT NULL, observation_id INTEGER NOT NULL, PRIMARY KEY(claim_id, observation_id),
 FOREIGN KEY(claim_id) REFERENCES claims(id), FOREIGN KEY(observation_id) REFERENCES observations(id)
);
CREATE TABLE IF NOT EXISTS questions (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, question TEXT NOT NULL, reason TEXT NOT NULL,
 evidence_needed TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES extraction_runs(id)
);
CREATE TABLE IF NOT EXISTS question_evidence (
 question_id INTEGER NOT NULL, observation_id INTEGER NOT NULL, PRIMARY KEY(question_id, observation_id),
 FOREIGN KEY(question_id) REFERENCES questions(id), FOREIGN KEY(observation_id) REFERENCES observations(id)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    return db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(db: sqlite3.Connection, source: NumberedSource, extraction: ValidatedExtraction,
           raw_response: str, backend: str, model: str | None, prompt_version: str,
           locator: str, title: str | None, kind: str | None, force: bool = False) -> tuple[bool, int]:
    response_hash = hashlib.sha256(raw_response.encode("utf-8")).hexdigest()
    existing = db.execute("SELECT id FROM corpus_entries WHERE source_id=? AND content_hash=?", (source.source_id, source.content_hash)).fetchone()
    if existing and not force:
        return False, int(existing[0])
    now = _now()
    with db:
        db.execute("INSERT INTO sources(id,title,kind,locator,content_hash,created_at) VALUES(?,?,?,?,?,?) "
                   "ON CONFLICT(id) DO UPDATE SET title=excluded.title,kind=excluded.kind,locator=excluded.locator,content_hash=excluded.content_hash",
                   (source.source_id, title, kind, locator, source.content_hash, now))
        if force and existing:
            run_ids = [row[0] for row in db.execute("SELECT id FROM extraction_runs WHERE corpus_entry_id=?", (existing[0],))]
            for run_id in run_ids:
                claim_ids = [row[0] for row in db.execute("SELECT id FROM claims WHERE run_id=?", (run_id,))]
                question_ids = [row[0] for row in db.execute("SELECT id FROM questions WHERE run_id=?", (run_id,))]
                for claim_id in claim_ids:
                    db.execute("DELETE FROM claim_evidence WHERE claim_id=?", (claim_id,))
                for question_id in question_ids:
                    db.execute("DELETE FROM question_evidence WHERE question_id=?", (question_id,))
                db.execute("DELETE FROM claims WHERE run_id=?", (run_id,))
                db.execute("DELETE FROM questions WHERE run_id=?", (run_id,))
                db.execute("DELETE FROM observations WHERE run_id=?", (run_id,))
                db.execute("DELETE FROM extraction_runs WHERE id=?", (run_id,))
            db.execute("DELETE FROM corpus_entries WHERE id=?", (existing[0],))
        cur = db.execute("INSERT INTO corpus_entries(source_id,content_hash,created_at) VALUES(?,?,?)", (source.source_id, source.content_hash, now))
        entry_id = cur.lastrowid
        cur = db.execute("INSERT INTO extraction_runs(corpus_entry_id,backend,model,prompt_version,response_hash,status,created_at) VALUES(?,?,?,?,?,?,?)",
                         (entry_id, backend, model, prompt_version, response_hash, "accepted", now))
        run_id = cur.lastrowid
        ids: dict[str, int] = {}
        for obs in extraction.observations:
            cur = db.execute("INSERT INTO observations(run_id,local_key,facet,statement,start_line,end_line) VALUES(?,?,?,?,?,?)",
                             (run_id, obs["key"], obs["facet"], obs["statement"], obs["start_line"], obs["end_line"]))
            ids[obs["key"]] = cur.lastrowid
        for claim in extraction.claims:
            cur = db.execute("INSERT INTO claims(run_id,status,statement) VALUES(?,?,?)", (run_id, claim["status"], claim["statement"]))
            for key in claim["supported_by"]:
                db.execute("INSERT INTO claim_evidence(claim_id,observation_id) VALUES(?,?)", (cur.lastrowid, ids[key]))
        for question in extraction.questions:
            cur = db.execute("INSERT INTO questions(run_id,question,reason,evidence_needed) VALUES(?,?,?,?)",
                             (run_id, question["question"], question["reason"], question["evidence_needed"]))
            for key in question.get("derived_from", []):
                db.execute("INSERT INTO question_evidence(question_id,observation_id) VALUES(?,?)", (cur.lastrowid, ids[key]))
    return True, int(entry_id)
