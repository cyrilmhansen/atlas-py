# Atlas local agent workflow — W1

W1 is a local, human-driven state machine. It launches no agent and contains no
Codex/Luna/Sol/model selection. W2 may add an executor later.

`events.jsonl` is the only durable logical authority. Every mutation takes the
single POSIX `fcntl` lock, validates the complete journal, replays it through
one canonical projection, checks the spool, and compares `state.json` with that
projection. `state.json` is only an atomically replaced, fsynced cache. A stale,
missing, incomplete, or falsified projection fails closed; `rebuild-state`
recreates it only after journal and spool validation. `doctor` is read-only.

Each filesystem transition writes `TRANSITION_PREPARED`, fsyncs it, atomically
renames the file, fsyncs both parent directories, then writes the terminal
logical event (`PROMPT_ACCEPTED`, `PROMPT_REJECTED`, `RUN_STARTED`,
`RUN_COMPLETED`, or `RUN_INTERRUPTED`) with the transaction id and fsyncs it.
There is no separate commit event. Recovery takes the same lock and checks the
expected SHA-256 of both source and destination; ambiguous, missing, or
incorrectly hashed paths fail closed. Recovery with no outstanding transaction
is a true no-op; a completed recovery is idempotent.

The journal has a closed event set, exact envelope fields, strict sequence,
timestamp, payload, previous hash, and event hash validation. Hash chaining is
an internal integrity check, not external authentication. Prompts are archived
as received bytes in `prompts/`; lifecycle files are validated by one
`validate_spool` function. Accepted, running/action, completed, and interrupted
locations are mutually exclusive. Lifecycle filenames are exactly
`g000001-<64hex-sha256>.txt`; prompt archives and reports are exact sets, so
orphan archives, reports, filenames, and content are errors.

Every terminal event must consume exactly one preceding PREPARE with matching
transaction metadata; a terminal without PREPARE is invalid. Generations are
linear: generation 1 has parent `genesis`, and generation N
has parent N-1. Same generation and same bytes is `DUPLICATE_PROMPT`; a
different hash is `GENERATION_COLLISION`. Multi-inbox files are parsed
individually and valid prompts are processed by generation, hash, then name.
Prompt front matter delimiters are exact `+++` lines; the rest is free body.
Checkpoint ids use `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`.

The required UTF-8 `atlas-agent.toml` has a closed schema. Allowed untracked
entries are normalized relative Git paths, normally ending `/`; `corpus_miner/`
is allowed in this repository while `corpus_miner2/`, `foo/corpus_miner/`,
absolute paths, and traversal are not. The repository witness is byte-oriented
and content-sensitive: HEAD, semantic index state (including intent-to-add),
actual tracked worktree patch bytes, and unexpected untracked paths are
distinct. An implementation may change the
tracked worktree, but not HEAD, index, or unexpected untracked files.
`patch_review` and `state_audit` are read-only policies. `checkpoint` performs
no automatic add/commit/push. Classification remains opaque and results must
match generation, prompt hash, and action.

`doctor` also compares the current repository with the action-specific policy:
an implementation may have tracked worktree changes while its HEAD, index, and
unexpected-untracked witness remain fixed; the read-only actions require the
full start witness. Outside a run, the current witness must equal the latest
canonical boundary.

Runtime is `git rev-parse --git-path atlas-agent`, which also works for linked
worktrees. Users should use that command (or a CLI path display), never copy to
`.git/atlas-agent/` by assumption. Locking is POSIX-only; platforms without
`fcntl` report unsupported rather than silently disabling the lock.

Typical commands:

```text
python -m tools.atlas_agent init
git rev-parse --git-path atlas-agent
python -m tools.atlas_agent ingest
python -m tools.atlas_agent start-run 1
python -m tools.atlas_agent complete-run 1 --result '{"generation":1,"prompt_sha256":"…","action":"implementation","outcome":"done","classification":"manual"}'
python -m tools.atlas_agent doctor
```
