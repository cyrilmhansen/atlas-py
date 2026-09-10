# PVC visual-source observation — Atlas Agent integration v0

Status: design baseline for the first Atlas Agent dogfood integration of `pi-visual-context` (PVC).

PVC source baseline:

```text
cyrilmhansen/pi-visual-context
818786a3a702cf314c2e18528b7b613523c316a6
fix: separate runtime and rendering work roots
```

This document does not redefine Atlas, Atlas Core, or PVC. It defines the narrow integration boundary by which Atlas Agent may execute PVC as a qualified one-shot observation service and materialize its portable output.

## 1. Architectural role

The ownership split is:

```text
PVC
    specialized visual-source observation / representation service

Atlas Agent
    authorization
    qualified tool identity
    deterministic subprocess execution
    isolation / capabilities
    lifecycle / cancellation / recovery
    operational provenance
    artifact validation and materialization

Atlas
    interpretation
    semantic representation
    coordination / decision
    optional later admission of observations as durable knowledge
```

A PVC snapshot is an observation. It is not automatically an Atlas fact, decision, obligation, graph edge, or qualification result.

## 2. Headless PVC contract consumed by Agent

The initial operation is:

```text
pvc prepare \
    --cwd <authorized-project-root> \
    --output <private-operation-scratch>/bundle \
    --work-root <private-operation-work-root> \
    [--profile normal|conservative] \
    <validated-relative-sources...>
```

PVC provides the following process contract:

```text
stdout    machine JSON only
stderr    progress / diagnostics
success   exit code 0
failure   non-zero exit; stdout empty
```

Successful `prepare` produces atomically:

```text
bundle/
    snapshot.json
    artifacts/
        artifact-sha256-....png
```

The portable snapshot contract is `SourceContextSnapshot` `schemaVersion: 1`.

The package's historical npm version is not the snapshot-contract authority. Agent must distinguish at least the qualified PVC runtime identity, observed/runtime version metadata where available, and snapshot `schemaVersion`.

## 3. Runtime and work-root invariant

PVC commit `818786a...` establishes the prerequisite invariant required by Atlas Agent:

```text
runtimeRoot
    immutable / may be read-only
    package code, Typst assets, fonts, compiled helpers

workRoot
    writable
    execution-local
    may be outside runtimeRoot
    rendering intermediates and an ephemeral Typst template copy
```

Atlas Agent must not make the qualified PVC runtime writable merely to satisfy execution scratch requirements.

For the first dogfood integration, persistent PVC project state and cache under `.pi/visual-context` remain separate from this runtime/work-root distinction and are not redesigned here.

## 4. Existing Atlas Agent mechanism to reuse

The integration must reuse the existing qualified-toolchain/capability-plan mechanism rather than introducing a second qualification system.

Conceptually:

```text
CapabilityResolver / CapabilityPlan
        ↓
qualified PVC command identity
        ↓
small controller-owned one-shot tool-operation runner
        ↓
PVC-specific observation adapter
```

PVC must not be found by opportunistic ambient `PATH` discovery for the qualified path.

The one-shot runner is not a second model executor and should not be forced into Codex-specific prompt/session/report semantics.

It may reuse existing Agent implementation techniques where appropriate, including explicit argv execution, bounded stdout/stderr files, process-group ownership, bounded SIGINT/SIGKILL cancellation, controlled environment construction, and existing qualified toolchain mounts.

Do not introduce a generic provider registry, daemon, HTTP/RPC layer, or marketplace for this slice.

## 5. Required execution distinctions

Do not collapse the following into one boolean:

```text
process execution outcome
stdout/stderr collection outcome
snapshot structural acceptance
bundle/artifact validation outcome
materialization outcome
qualification status
```

In particular:

```text
exit code 0 != valid qualified observation
```

A successful process with missing, malformed, contradictory, or corrupt output must remain distinguishable from a process failure.

## 6. Snapshot and bundle validation

PVC remains responsible for the complete semantic validation of `SourceContextSnapshot v1` before publication.

Atlas Agent must not reimplement the full TypeScript validator in Python. Agent nevertheless owns its ingestion/materialization boundary and therefore must minimally verify:

```text
stdout is bounded and valid JSON
supported schemaVersion == 1
expected top-level shape is present
stdout bytes match bundle/snapshot.json bytes for prepare
snapshot.json itself is hashed
artifact paths are safe and remain inside the bundle
referenced artifacts exist
media type is expected for this integration
artifact hashes match actual bytes
artifact byteLength matches when supplied
bundle is closed to unexpected path escape/symlink behavior
```

Agent should not independently reimplement the `snapshotId` derivation algorithm merely to duplicate PVC's validator. Preserve `snapshotId` as PVC contract data and independently record the hash of the exact `snapshot.json` bytes received/materialized.

Treat the bundle as one publication unit with `snapshot.json` as manifest and PNG files as child artifacts. Do not create a PVC-specific artifact store.

## 7. Sources and initial path policy

For the first integration, Atlas Agent should pass explicit validated source paths rather than exposing PVC glob expansion as an authority boundary.

Before invocation, reject at least:

```text
absolute source paths
`..` traversal
source paths escaping the authorized workspace
symlink source/path escapes
```

Initial Atlas-side source requests should therefore be normalized relative paths. Glob support may be added later if a real consumer requires it.

PVC-generated source identities (`contentSha256`) are observations from the prepared snapshot. Agent should additionally bind the operation to the repository/workspace witness or material identity available at invocation so later consumers can reason about drift.

## 8. Environment and sandbox

The initial qualified PVC execution should require no network access.

The effective environment should expose only the runtime/tool components PVC actually needs. PVC currently depends on Node plus rendering/helper tools such as Typst, ImageMagick, Poppler/font utilities, Git where provenance is collected, and the PVC compacting helpers. Qualification should reuse existing Agent capability/toolchain mechanisms rather than ambient user configuration.

A logical read/observation operation may still need narrowly writable execution locations:

```text
private work root
private output bundle staging
PVC cache/project state where explicitly permitted
```

Writable scratch does not make the qualified runtime mutable.

## 9. Operational lifecycle and recovery

The existing Atlas Agent journal has a closed event model centered on generation lifecycle. PVC introduces the first controller-owned one-shot qualified tool operation that is not itself a model generation.

The implementation may extend the existing operational authority with the smallest durable lifecycle needed to prevent ambiguous crash states. The exact event names are implementation details, but the semantics must distinguish at least:

```text
operation admitted/started
result identity prepared before durable publication
operation completed
operation interrupted/failed
```

Do not introduce the future generalized observability/event-stream design merely for this slice.

Process-group ownership must cover child processes launched by PVC. Timeout or cancellation must be bounded and reap the whole owned group.

Recovery must never silently rerender an observation. A started operation without a trustworthy terminal state is historical interruption unless an already-prepared publication can be proven byte-identical and safely finalized under the chosen transaction contract.

An observation that was validly materialized remains historical evidence even if a surrounding Atlas generation or later task is subsequently cancelled; cancellation must not rewrite prior observation history.

## 10. Materialization

Do not place PVC bundle files arbitrarily into Codex execution-report directories if doing so violates the existing closed spool/report contract.

Use an Agent-controlled observation/tool-operation materialization location with immutable historical identity after publication, conceptually:

```text
<atlas-runtime>/observations/<operation-id>/
    operation.json
    stdout.log
    stderr.log
    bundle/
        snapshot.json
        artifacts/...
```

The precise path may follow existing repository/runtime conventions discovered during implementation. The invariant is more important than the spelling: stage privately, validate, bind the intended destination and hashes, then publish atomically/durably according to the existing Agent transaction style.

Relative artifact paths inside the PVC bundle must remain valid after materialization.

## 11. Metadata-only resolution

After `prepare`, `SourceContextSnapshot v1` is portable and independent of original sources, PVC cache, Pi conversation state, and original cwd.

Therefore Atlas Agent must not turn metadata-only navigation into a rerender.

For v0:

```text
prepare
    always through qualified Agent/PVC execution

metadata resolution
    may be performed directly by a trusted consumer of snapshot v1

exact PVC navigation semantics
    `pvc resolve-tablet`, `resolve-symbol`, and `symbols`
    remain available as reference operations when needed
```

Do not reimplement PVC symbol-resolution semantics in Agent merely to avoid a cheap metadata subprocess.

The symbol-extraction states remain semantically distinct:

```text
unsupported
successful empty observation
partial
failed
```

`success + symbols=[]` must never be promoted to a claim that the source has no symbols.

## 12. Provenance identities

Record enough identity to distinguish portable contract from execution provenance. Initial useful fields include:

```text
requested tool identity
resolved qualified executable/runtime identity
PVC source/release identity when available
qualified executable/script hash
relevant capability-plan identity
Node/runtime identity where meaningful
snapshot schemaVersion
snapshotId
snapshot.json byte hash
artifact hashes and sizes
source contentSha256 values
repository/workspace/material witness
```

Renderer/helper identities may be recorded as execution provenance where the existing qualification mechanism naturally exposes them. Do not make every transitive version a new semantic contract field.

## 13. First-slice tests

The first Atlas Agent integration should cover at least:

```text
qualified PVC resolution; no ambient PATH fallback
explicit source-path admission/rejection
successful prepare -> valid snapshot v1 + PNG publication
stdout/snapshot.json contradiction rejection
exit 0 + malformed/invalid snapshot distinction
missing/corrupt artifact rejection
non-zero process exit
bounded timeout/cancellation and child reaping
no implicit overwrite of an existing publication
crash/recovery around prepared publication boundary
historical materialization survives later task cancellation
metadata resolution does not rerender
```

Use small fixtures. Do not turn this into a broad renderer benchmark or generalized Agent hardening exercise.

## 14. Explicit non-goals

This slice does not design or implement:

- Atlas graph or semantic zoom;
- generalized event-stream/TUI observability;
- provider/plugin/marketplace framework;
- PVC daemon or persistent server;
- HTTP/RPC transport;
- Rust port of PVC;
- new visual codecs or formats;
- new symbol extractors;
- generalized artifact-store architecture;
- full relocation/redesign of `.pi/visual-context` state/cache;
- rust-analyzer lifecycle itself.

## 15. Relationship to semantic navigation

PVC and `rust-analyzer` exercise complementary forms of the same larger Agent capability boundary:

```text
PVC
    one-shot
    artifact-heavy
    portable immutable snapshot
    local project state/cache

rust-analyzer
    longer-lived / interactive
    small structured observations
    incremental semantic state
    language-server protocol
```

PVC is therefore the first real consumer of a narrow one-shot qualified-tool-operation substrate. It should inform, but not over-generalize, the later semantic-service runtime used by `rust-analyzer`.

The stop rule remains: once the bounded PVC integration contract, required witnesses, and qualification are satisfied, close the slice rather than converting it into generalized service hardening.
