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
python3 -m corpus_miner.cli evaluate corpus_miner/evaluation reports/qwen3.6-27b.md \
  --base-url http://127.0.0.1:1234 \
  --model Qwen3.6-27B-oQ4e-fp16-mtp --stream
python3 -m corpus_miner.cli evaluate corpus_miner/evaluation reports/fixture-08.md \
  --base-url http://127.0.0.1:1234 \
  --model Qwen3.6-27B-oQ4e-fp16-mtp --only 08-open-question.md --show-prompt
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

The prompt separates the evidence boundary from the relevance boundary:
`SOURCE` is the only basis for source-supported facts, while the default
Reference Context identifies reusable software and systems engineering
knowledge worth extracting. A caller may override it with
`--reference-context TEXT` or `--reference-context-file PATH`; it is not an
ontology, facet, or evidence source. Evaluation reports record its SHA-256.

With `--stream`, the OpenAI-compatible backend requests SSE with
`stream_options.include_usage`, displays reasoning and final content as they
arrive, and reports server-provided token metrics. Without `--stream`, the
original non-streaming request remains in use. The reasoning text is never
sent to the Atlas validator or persisted as corpus knowledge.

Evaluation can restrict the ordered fixture set with repeated `--only`, save
exact prompts with `--save-prompts DIR`, and save per-fixture response
telemetry with `--save-responses DIR`. `--thinking on` or `--thinking off`
adds the corresponding `chat_template_kwargs.enable_thinking`; omitting it
does not force a value.

Evaluation uses one request at a time by default. `--concurrency N` enables a
bounded thread pool with at most N independent HTTP requests active at once.
Results, reports, and prompt/response artifact names remain in fixture order.
When streaming is combined with concurrency greater than one, token output is
buffered in the response artifacts and only concise completion progress is
printed, avoiding interleaved terminal streams. A request failure is recorded
for its fixture while unrelated requests continue.
