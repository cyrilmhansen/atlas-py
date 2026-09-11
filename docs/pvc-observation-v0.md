# PVC visual context compilation — Atlas Agent integration v0

Status: design baseline for the first Atlas Agent dogfood integration of `pi-visual-context` (PVC).

The generic qualification gates are in
[`qualified-service-workflow.md`](qualified-service-workflow.md); machine
deployment and release engineering remain covered by
[`deploy-existing-project.md`](deploy-existing-project.md) and
[`atlas-release-process.md`](atlas-release-process.md).

PVC source baseline:

```text
cyrilmhansen/pi-visual-context
818786a3a702cf314c2e18528b7b613523c316a6
fix: separate runtime and rendering work roots
```

Historical prototype provenance is retained above. The qualified headless
runtime witnessed by Atlas Agent was:

```text
cyrilmhansen/pi-visual-context
54777ee0254c6f3f4bc04ea8a5cdb2d58cf43221
fix(cli): externalize headless project state
```

This document reframes the historical filename and contract around PVC's near-term purpose: compiling suitable source material and, where useful, long task material into dense multimodal tablets for Luna, Sol, and Astra. The prototype is an experiment/proof of concept whose visual representation aims to give multimodal models large amounts of useful context efficiently. It provides empirical evidence for, and motivates, a model-specific optimization strategy; visual encoding is not a universal guarantee of lower quota, latency, or cost.

## 1. Product and architectural role

PVC is a specialized visual context transformation and addressing service. It is not primarily an Atlas observation provider. The ownership split is:

```text
Atlas
    semantic representation, interpretation, decision, coordination

Atlas Agent
    authorization, qualification, controlled execution, context assembly,
    invocation provenance, materialization

PVC
    visual context transformation and VC/address metadata

model (Luna / Sol / Astra)
    consumes multimodal context and reasons over it
```

PVC distinguishes two artifact classes:

```text
SOURCE tablets
    rendered source/reference material

TASK tablets
    rendered natural-language prompt/task/specification material
```

Critical operational instructions, authorization boundaries, and small exact constraints should normally remain available as text. TASK tablets are useful primarily when long prompt/specification/context material benefits from rendering, not because every prompt must be encoded visually.

The preferred representation depends on model, task, source size, and need for lexical precision. Relevant measurements include model quality/answer correctness, context coverage, model input quota/accounting, latency, sequential tool-call count, render/preparation cost, and overall task time.

## 2. Context strategies and up-front context

The three first-class strategies are:

```text
Classical
    textual prompt + textual source excerpts + successive file/search/tool calls

PVC
    concise critical text instructions
    TASK tablets for long prompt material where useful
    SOURCE tablets for selected important files
    compact textual tablet/address index

Hybrid
    concise critical instructions in text
    important broad/stable source context as PVC tablets
    traditional tools for exact/local/current follow-up
```

PVC is not a mandatory replacement for normal tools. File/search/read operations remain preferable when they are cheaper, more exact, more current, or only a small amount of material is needed.

A key intended benefit is that Atlas Agent can supply principal relevant files at the beginning of an invocation in compact visual form. This gives the model a broad project view before reasoning rather than requiring a sequential chain of unoptimized discovery calls. Normal tools remain available afterwards for exact rereading, small source regions, omitted material, changed/current material, verification, and editing.

The primary flow is:

```text
Atlas / workflow
    ↓ task + candidate context
context strategy (classical | PVC | hybrid)
    ↓
Atlas Agent
    ↓ qualified PVC preparation where selected
TASK tablets + SOURCE tablets
snapshot.json + PNG artifacts + address metadata
    ↓ Agent validates provenance/bundle
assemble multimodal model context
    ↓
Luna / Sol / Astra invocation
    ↓
normal tools remain available for follow-up
```

Separately:

```text
snapshot / metadata
    ↓ optional Atlas interpretation
possible software observation/evidence
    ↓
never automatically promoted to durable Atlas knowledge
```

A PVC snapshot may become an Atlas observation, but model-context preparation does not itself imply semantic admission. Atlas Agent is not the owner of Atlas semantic interpretation.

## 3. Headless PVC contract

Interactive/legacy PVC defaults may keep project state below the project
directory. That is not the qualified Atlas Agent contract. Qualified headless
execution externalizes all operation-owned writable state:

```text
pvc prepare \
    --cwd <authorized-project-root> \
    --output <private-operation-scratch>/bundle \
    --work-root <private-operation-scratch>/work \
    --state-root <private-operation-scratch>/state \
    [--profile normal|conservative] \
    <validated-relative-sources...>
```

The roots have distinct authority and lifecycle:

```text
projectRoot
    authorized source input; read-only to PVC

runtimeRoot
    qualified immutable PVC runtime, assets, and helpers

workRoot
    ephemeral rendering intermediates

stateRoot
    writable PVC project state/cache for this controlled operation or a
    controller-defined lifecycle

output/bundle
    prepared result awaiting Atlas validation
```

`--cwd` identifies `projectRoot`; it is not permission to write project-local
state. Qualified Agent execution must not require
`<project>/.pi/visual-context`. Agent owns the private bundle, work, state,
stdout, and stderr locations and binds them to the operation record.

PVC provides:

```text
stdout    machine JSON only
stderr    progress / diagnostics
success   exit code 0
failure   non-zero exit; stdout empty
```

The Pi-facing prototype supports visual prompt/TASK rendering, but the headless Atlas Agent contract currently covers `pvc prepare ... <sources>`. Before Agent can visually package long prompts itself, PVC needs an appropriate deterministic headless TASK operation or an extension of that contract. This document does not prescribe its CLI syntax. TASK and SOURCE artifacts remain separate even when one invocation prepares both.

Successful source preparation produces atomically:

```text
bundle/
    snapshot.json
    artifacts/
        artifact-sha256-....png
```

The portable snapshot contract is `SourceContextSnapshot` `schemaVersion: 1`. The package's historical npm version is not the snapshot-contract authority; distinguish qualified runtime identity, observed/runtime version metadata where available, and snapshot schema version.

## 4. Addressing and navigation

VC IDs, source/line ranges, and conservative symbol anchors are primarily an address map into supplied visual context:

```text
tablet
file + line range
symbol -> tablet(s)
```

They permit inexpensive later references without automatically retransmitting
or rerendering the whole source set. Metadata-only resolution does not require
rerendering. An address does not by itself make PNG pixels available to every
future model invocation:

```text
same retained model conversation/session
    previously attached visual context may remain referable

new/fresh model invocation
    the relevant tablet may need to be attached again from the
    materialized bundle
```

Reattachment from an existing validated bundle is not a rerender. The exact
future model-session persistence mechanism is intentionally unspecified.
Symbol extraction is conservative/best-effort and anchors are not
authoritative language semantics or a complete semantic symbol table. Preserve
at least these outcomes:

```text
unsupported
successful empty
partial
failed
```

A successful empty symbol result is not a claim that the source has no symbols. After preparation, metadata-only navigation must not trigger a rerender; trusted consumers may resolve snapshot metadata directly, with exact PVC resolution operations available when needed.

## 5. Qualification, execution, and source policy

The integration reuses the existing qualified-toolchain/CapabilityPlan mechanism:

```text
CapabilityResolver / CapabilityPlan
        ↓ command and mount authority
qualified PVC command identity
        ↓
controller-owned one-shot tool-operation runner
        ↓
narrow PVC prepare adapter
```

PVC must not be found by opportunistic ambient `PATH` discovery. The qualified
operation uses explicit argv, isolated Bubblewrap execution, private operation
scratch, bounded stdout/stderr, process-group ownership, timeout/process
teardown, and controlled environment. It should require no network. The runner
is not a model executor and is not forced into Codex prompt/session/report
semantics. Do not introduce a provider registry, daemon, HTTP/RPC layer, or
marketplace.

Before invocation, reject absolute paths, `..` traversal, workspace escapes, and symlink source/path escapes. Pass explicit validated relative paths rather than exposing PVC glob expansion as an authority boundary. Bind generated source identities (`contentSha256`) to the repository/workspace witness or material identity available at invocation so drift is visible.

PVC's qualified runtime/work-root/state invariant is:

```text
runtimeRoot    immutable/read-only package code, assets, fonts, helpers
workRoot       writable execution-local intermediates and template copy
stateRoot      writable controlled PVC project state/cache
projectRoot    read-only authorized source input
```

The effective environment should expose only required qualified Node, Typst,
ImageMagick, Poppler/font, Git/provenance, and compacting helpers. Writable
scratch does not make the runtime mutable.

The A2.1a qualification established a deterministic `pvc probe`,
CapabilityResolver/CapabilityPlan authority, the exact qualified command
identity, and no ambient `PATH` fallback. The real host witness was:

```text
qualified PVC → CapabilityPlan → Bubblewrap → pvc prepare
```

It produced `snapshot.json`, a PNG artifact, and external `project.json` with
process success, exit code 0, and no timeout. The source project remained
read-only and unchanged: project-local `.pi` was absent, project status was
unchanged, and the tracked diff was unchanged. This execution evidence was
deliberately not yet semantic admission or a validated/materialized result:
`bundle_validated: false` and `output_interpreted: false`.

## 6. Validation, provenance, lifecycle, and materialization

Do not collapse these outcomes:

```text
process execution; stream collection; snapshot acceptance;
bundle/artifact validation; materialization; qualification status
```

Exit code 0 is not a valid qualified result by itself. PVC remains responsible for complete `SourceContextSnapshot v1` validation; Agent must minimally verify bounded valid JSON, supported schema, expected shape, stdout equality with `bundle/snapshot.json`, snapshot hash, safe in-bundle artifact paths, expected media type, artifact existence/hash/byte length, and closure against path escape/symlink behavior. Do not duplicate PVC's `snapshotId` algorithm; record the exact snapshot bytes hash.

Treat the bundle as one publication unit: `snapshot.json` is manifest and PNGs are child artifacts. Stage privately, validate, bind destination and hashes, then publish atomically/durably. A conceptual materialization is:

```text
<atlas-runtime>/tool-operations/<operation-id>/
    operation.json  stdout.log  stderr.log
    bundle/snapshot.json  bundle/artifacts/...
```

Relative artifact paths must remain valid after publication. Record requested and resolved tool/runtime identity, qualified executable/script hash, CapabilityPlan identity, relevant renderer/runtime identities, schemaVersion, snapshotId, snapshot byte hash, artifact hashes/sizes, source hashes, and repository/material witness.

The smallest durable lifecycle must distinguish admitted/started, result identity
prepared, completed, and interrupted/failed. Process-group ownership includes
children; timeout or process teardown reaps the owned group. A started operation
without trustworthy terminal state is historical interruption; never silently
rerender it. A validly materialized operation result/bundle remains historical
execution evidence; whether Atlas interprets or adopts it as an observation is
separate.

## 7. Metadata-only resolution and first dogfood

`prepare` is always through qualified Agent/PVC execution. Navigation of an existing snapshot is metadata-only and must not rerender. The first useful dogfood is an explicit deterministic policy: for a real Agent generation, choose a bounded set of principal files and optionally long task material, prepare through qualified PVC, validate the bundle, attach tablets to the model invocation, and retain normal tools. Compare classical, PVC, and hybrid context on the same representative task. Do not prematurely build an automatic context-selection optimizer.

The first integration should test qualified resolution/no PATH fallback, path admission, valid publication, contradictory or malformed output, missing/corrupt artifacts, process failure, bounded timeout/process teardown and child reaping, no overwrite, crash recovery, historical persistence, and no rerender during metadata resolution.

## 8. Non-goals

This documentation does not design or implement automatic source-selection planning, new codecs or rendering benchmarks, a generalized provider/plugin framework, rust-analyzer runtime, Atlas Core Rust implementation, semantic graph admission rules, model-specific hardcoded thresholds, or production code/tests.
