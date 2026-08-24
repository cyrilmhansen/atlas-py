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

## W2.1 — generic Codex executor

W2.1 adds an explicit executor boundary without choosing a model, role, or
fresh/reuse policy. The locally installed Codex CLI was inspected rather than
assuming an older interface: `/usr/bin/codex` reports `codex-cli 0.149.1`, and
its non-interactive form is `codex exec`. It accepts a prompt argument or `-`
on stdin, supports `--json`, `--model`, `--sandbox`, `--ephemeral`, `--cd`, and
`-o`; the current help also exposes `--approve-for-me` and a separate dangerous
bypass option, neither of which W2.1 enables. `resume` is a separate command.
JSONL output
may expose a thread/session id. These are capabilities of the observed local
installation, not a promise about every Codex version.

`tools/atlas_agent/executor.py` defines the versioned generic boundary and a
`FakeExecutor` used by tests. `codex_executor.py` builds an explicit argv with
no shell interpolation, streams stdout and stderr directly to bounded-on-disk
logs, and returns structured execution metadata. `execute GENERATION` is an
explicit user operation; there is no watcher or daemon. It runs W1 preflight,
starts the W1 lifecycle transition, launches the configured executor, stores
`reports/executions/<execution_id>/execution.json`, `stdout.log`, `stderr.log`,
and `result.json`, and completes or interrupts the W1 run from the process
result. A non-zero exit, signal, or launcher exception is interrupted. A
launcher crash after `RUN_STARTED` remains visible to doctor/rebuild and is not
reported as completed.

W2.1 deliberately leaves model/role selection and fresh/reuse session policy
to W2.2. It does not dispatch Codex/Luna/Sol automatically, and it does not
add an executor-specific commit event to the W1 journal.

Every W2.1 launch is a hermetic, headless permission envelope. The executor
always requests `--strict-config`, `--ignore-rules`,
`approval_policy="never"`, `approvals_reviewer="user"`, and an explicit
sandbox. For `workspace-write`, it also passes an explicit
`sandbox_workspace_write.network_access=true|false`; the boolean records the
requested sandbox setting, not an end-to-end guarantee that DNS or network
access works. W2.1 does not map actions to these policies; callers provide an
explicit sandbox configuration. Unsupported non-interactive settings fail
closed, and `--approve-for-me` is not enabled by default.

The durable `result.json` contains `permission_envelope`,
`permission_observation_status` (`observed`, `partial`, or `unavailable`), and
`permission_failures`. Codex 0.149.1 may refuse a tool command while still
returning process exit 0 with no JSONL or stderr signal. Therefore exit 0 means
only that the executor process/session ended normally; it does not mean all
tool commands succeeded. When no explicit refusal is published,
`permission_failures` is `null`, never an invented empty list. `usage.json`
and `usage/events.jsonl` remain limited to token/quota telemetry and do not
carry permission claims.

Headless execution has a configurable, non-aggressive watchdog. A timeout
interrupts the child, records `outcome: "timeout"`, and interrupts the W1
run; it never waits for a human approval. The fake executor implements the
same permission result fields so lifecycle tests do not have a second schema.

`prepare_execution()` is pure with respect to external execution: it validates
the request and constructs argv without launching Codex or discovering its
version. W1 preflight and `RUN_STARTED` happen first; version discovery and
the child process happen only after the run is `RUNNING`. A discovery failure
interrupts the run. Execution ids are checked against lifecycle owners and
existing report directories under the workflow lock; a collision fails closed
and never reuses a report directory.

`execution.json` and `result.json` are owner-bound artifacts. Their execution
id, generation, prompt hash, action, and permission metadata are checked by
spool validation/doctor. The lifecycle journal/state remains authoritative;
the JSON artifacts are evidence and cannot complete a run by themselves.
Historical W1 `RUN_STARTED` events without execution metadata remain without
an `execution` key during replay. The candidate performs no projection
migration and does not synthesize `execution: null`.

### W2.1 passive telemetry

Each execution also gets a versioned `usage.json` beside its execution logs.
The collector prefers the structured `codex exec --json` JSONL. In Codex
0.149.1 the observed JSONL includes `thread.started.thread_id` and
`turn.completed.usage` with `input_tokens`, `cached_input_tokens`,
`output_tokens`, `reasoning_output_tokens`, and sometimes `total_tokens`.
Missing fields remain null; totals are never estimated. Multiple conflicting
usage envelopes are retained as separate observations and marked partial.

Passive observations are appended to the non-authoritative
`usage/events.jsonl`, associated with execution id, generation, prompt hash,
action, checkpoint, requested model, observed model, thread id, Codex version,
source, and metrics. Requested and observed model are separate: a requested
model is configuration, not proof of what Codex used. Each `turn.completed`
usage observation is associated with the most recent supported
`thread.started`; unknown JSONL event types are ignored, including unknown
events that happen to contain a `usage` object. `usage.json` and history use
an explicit allow-list of fields, never a blacklist, so arbitrary metadata and
credential-shaped keys are discarded. Every JSONL consumer uses the shared
bounded reader with a 1 MiB maximum physical line payload; an oversized line
is discarded through its newline and counted malformed, so later records
remain parseable. `quota_before` and `quota_after` are
explicitly null/unavailable in this installation: the inspected `codex` and
`codex exec` help expose no machine-readable `/status`, `/usage`, or
`/statusline` surface, and W2.1 does not scrape the interactive TUI or call a
private backend. A telemetry parser failure produces an unavailable or partial
artifact and never changes a healthy executor lifecycle. A structural failure
writing a telemetry/report artifact is an execution failure: cleanup interrupts
the W1 run before reporting the secondary telemetry error. Secrets are
excluded from both telemetry artifacts. Log permission scanning is line-based
with bounded reads; it does not load complete stdout/stderr files into memory.
