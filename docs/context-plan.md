# Explicit context plans: author → check → dispatch

The operator (or Atlas planning layer) chooses every member and semantic query.
Workflow and the executor do not discover relevant files, choose observations,
or substitute context. No new language-server capabilities are implied.

Run from the target repository using your qualified controller (`aa` in the
[operator cheat sheet](operator-cheatsheet.md)). During development, the public
checkout interface is `python -m tools.atlas_agent`:

```sh
# Source checkout only (the atlas package lives under src/):
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
python -m tools.atlas_agent --help
python -m tools.atlas_agent context-plan-example > /tmp/plan.json
# Read/edit /tmp/plan.json: replace placeholders; remove unwanted members.
python -m tools.atlas_agent context-plan-check --context-plan /tmp/plan.json
python -m tools.atlas_agent dispatch --context-plan /tmp/plan.json
```

`context-plan-example` prints only valid JSON and works without an initialized
repository. It is an **authoring template**, not an executable recommendation:
paths, coordinates, tablet IDs and version must be chosen by the operator.
Keep plan files outside the worktree to avoid introducing unrelated patch or
witness changes. Relative **plan file** paths are relative to the shell's cwd.

## Complete context-plan/2 template

```json
{
  "schema": "atlas-agent-context-plan/2",
  "members": [
    {"kind": "REVIEW"},
    {
      "kind": "SOURCE",
      "result_path": "/absolute/path/to/retained-pvc-result",
      "tablet_ids": ["APO-VC-000001"],
      "purpose": "Inspect the selected source image",
      "sources": ["atlas-agent.toml"]
    },
    {
      "kind": "SEMANTIC",
      "backend": "python",
      "query": {
        "kind": "definition",
        "path": "tools/atlas_agent/cli.py",
        "line": 0,
        "character": 0
      },
      "executable": "/absolute/path/to/pyright-langserver",
      "version": "operator-supplied Pyright version"
    }
  ]
}
```

Only `schema` and nonempty `members` are allowed at top level; unknown fields,
duplicate JSON keys and nonfinite numbers are rejected. `/1` remains supported
(Rust-only semantics, no `backend`, optional version); new plans should use `/2`.
A plan cannot authorize model, network, sandbox, session or execution policy.

### Members and authority

- **REVIEW**: requests the exact accepted prompt TASK and exact Git DIFF against
  its expected head, using existing review-package patch ownership rules. It is
  not a code review performed by a model and does not discover SOURCE images.
- **SOURCE**: borrows only explicitly named PNG tablets from an already-retained
  PVC result directory (containing `stdout`, `stderr` and the referenced bundle).
  `result_path` is absolute or repository-root-relative. `tablet_ids` selects exact
  IDs, not glob patterns or file names. `purpose` is a nonblank selection reason.
  Optional `sources` contains repository-relative source paths for the retained
  request; omission or an empty list uses the existing `atlas-agent.toml` default.
  These paths are validated, not used to discover or render additional context.
  No rasterizer runs, and the borrowed result is not deleted after dispatch.
- **SEMANTIC**: one explicit `definition`, `references` or `hover` query. `/2`
  requires `backend` (`python` for Pyright or `rust` for rust-analyzer), an
  **absolute executable path**, and a **nonblank version**. No PATH discovery,
  installation or fallback backend occurs. Use the language-server executable
  (e.g. `pyright-langserver`, not the `pyright` type-checker). Each request runs a
  fresh stdio server at dispatch. Version is **operator-asserted provenance**,
  not a binary hash, measured version, or verified claim. The static check only
  checks that the named executable exists and is executable; it never probes it.

Semantic `query.path` is a normalized repository-root-relative POSIX path, not
relative to the plan file. Absolute paths and `..` are rejected. Acquisition
also enforces the backend's repository file/symlink and result-location bounds.
`line` and `character` are **zero-based**; `character` counts **UTF-8 bytes from
the start of that line**, not displayed columns, Unicode characters or UTF-16
units. For the line `é😀 target`, `target` begins at byte 7 (2 + 4 + 1).
An ASCII editor position at line 12, column 5 becomes `line: 11, character: 4`.
Do not subtract one from a Unicode editor column and assume it is a byte offset.
The semantic adapters handle LSP encoding conversion, not query selection.

Requests are listed in plan order. Integrated rendering uses **TASK → DIFF →
SOURCE → SEMANTIC**, preserving member/tablet order within each category. TASK
is always supplied from the accepted prompt; without REVIEW, DIFF is not
synthesized. Missing SOURCE/SEMANTIC categories say `not selected`. See
[integrated context](integrated-context.md) for exact-byte/provenance guarantees.

## What the static check proves (and does not)

`context-plan-check --context-plan PLAN.json` reuses the dispatch parser,
backend query/authority types, retained SOURCE validator, and accepted-spool
lookup. It reads the workflow journal/state/spool and authenticates their
provenance, validates query/path shape and executable availability, and validates
any selected retained SOURCE payloads. Errors exit 1; member-level failures name
the one-based member index. No plan is rewritten, and no selection is added,
removed, deduplicated or relocated.

It previews the **lowest ACCEPTED generation**, action, checkpoint, expected
head and accepted-prompt digest, followed by requested members, coordinates,
executable/version and SOURCE tablet selections. A blocked generation is not
skipped. With no accepted generation it reports `target: none` /
`NO_DISPATCHABLE_GENERATION`; a valid static check still exits 0. This is not a
claim of dispatch readiness. Target selection is a point-in-time observation,
not a reservation: recheck after ingest/cancel or other lifecycle changes.

**Preview does not acquire semantic observations, construct a review package,
create temporary PVC resources, stage integrated rendering, or invoke an
executor.** It does not validate semantic file contents or coordinate bounds,
server identity/protocol/results, review diff applicability, aggregate rendering
limits, execution policy or repository admission. Reading/validating existing
SOURCE artifacts is not acquisition. There is no acquiring-preview mode in this
tranche: **dispatch is the acquiring operation** and revalidates at its existing
authority boundaries. Dispatch builds temporary REVIEW/SEMANTIC PVC resources,
cleans them up, and archives the actual execution input and provenance.

## Atlas-on-Atlas plan (no SOURCE needed)

For navigation to Atlas's prompt parser, inspect `tools/atlas_agent/prompt.py`.
At this revision `def parse_prompt` is on editor line 11 and begins at byte 4:

```sh
cat > /tmp/atlas-parser-plan.json <<'JSON'
{
  "schema": "atlas-agent-context-plan/2",
  "members": [
    {"kind": "REVIEW"},
    {
      "kind": "SEMANTIC", "backend": "python",
      "query": {"kind": "definition", "path": "tools/atlas_agent/prompt.py", "line": 10, "character": 4},
      "executable": "/usr/bin/pyright-langserver", "version": "pyright 1.1.412"
    }
  ]
}
JSON
cat /tmp/atlas-parser-plan.json
python -m tools.atlas_agent context-plan-check --context-plan /tmp/atlas-parser-plan.json
# Only after confirming the intended ACCEPTED generation and local tool authority:
python -m tools.atlas_agent dispatch --context-plan /tmp/atlas-parser-plan.json
```

The path/version above are explicit operator choices from the g198 host, not
portable defaults. Reconfirm them and the source coordinates on your host.
Do not create/cancel/dispatch a different generation merely to make a preview
show a target; Atlas owns lifecycle transitions during a running batch task.
