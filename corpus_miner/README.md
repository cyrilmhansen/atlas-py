# Corpus Miner

POC bounded-source extraction harness. It accepts one local text source, sends
numbered lines to either the deterministic fake backend or an
OpenAI-compatible `/v1/chat/completions` endpoint, validates local evidence,
then persists one accepted extraction in SQLite and a deterministic Markdown
entry.

## Commands

```sh
python3 -m corpus_miner.cli ingest SOURCE.md --source-id example \
  --backend fake --fake-response response.json --db state/corpus.db \
  --out corpus/extracted
python3 -m corpus_miner.evaluate corpus_miner/evaluation reports/qwen.md \
  --base-url http://127.0.0.1:1234 --model Qwen
```

The fake backend is used by all deterministic tests. The OpenAI-compatible
backend reads `ATLAS_LLM_BASE_URL`, `ATLAS_LLM_MODEL`, and optional
`ATLAS_LLM_API_KEY` when invoked through the CLI.

SQLite is the operational index; Markdown is the inspectable durable view.
Validation happens before the write transaction. A repeated source content
hash is a no-op unless `--force` is used. A changed content hash is a new
corpus entry. No crawling, embeddings, promotion, or ontology mutation is
performed.

Markdown filenames use `<safe-source-id>--<hash12>.md`, for example
`nist-binary-search--a93f18c21e4b.md`. The hash prefix prevents a newer version
from overwriting an older durable artifact. `source_id` remains the original
logical identity in SQLite and in the Markdown heading; only the filename uses
the filesystem-safe normalized form. Re-ingestion with `--force` replaces only
that same versioned path.

## Accepted JSON

The versioned shape is:

```json
{
  "schema_version": 1,
  "observations": [{"key": "o1", "facet": "mechanism", "statement": "...", "start_line": 1, "end_line": 2}],
  "claims": [{"status": "DERIVED_INTERPRETATION", "statement": "...", "supported_by": ["o1"]}],
  "questions": [{"question": "...", "reason": "...", "evidence_needed": "...", "derived_from": ["o1"]}]
}
```

Observations are local source facts and must cite numbered source lines.
Claims are interpretations or hypotheses tied to observations. Questions may
have no originating observation when the source itself supplies no evidence.
SQLite tables are `sources`, `corpus_entries`, `extraction_runs`,
`observations`, `claims`, `claim_evidence`, `questions`, and
`question_evidence`.
