# Atlas / Atlas Agent — Roadmap

Document version: **0.12**
Planning date: **2026-09-14**
Agent code baseline: **`9830692efc96d7e49916bd3f490668a65ee7350e`** (`Qualify rust semantic PVC tablet v0`)

Architecture boundary: [`docs/architecture-boundaries.md`](architecture-boundaries.md)
PVC observation baseline: [`docs/pvc-observation-v0.md`](pvc-observation-v0.md)
Semantic navigation baseline: [`docs/semantic-observation-v0.md`](semantic-observation-v0.md)
Specialized-service qualification workflow: [`docs/qualified-service-workflow.md`](qualified-service-workflow.md)
Release procedure: [`docs/atlas-release-process.md`](atlas-release-process.md)
Project deployment: [`docs/deploy-existing-project.md`](deploy-existing-project.md)

This roadmap supersedes version 0.11.

Version 0.12 records the following completed work since 0.11:

- **A6.1 selectable model execution profiles — COMPLETE.** The qualified
  profile layer separates compute selection from action/security authority.
  Retained profiles are `luna-high`, `sol-medium`, and `astra-medium`.
  The implementation/default policy remains deliberately small; not every
  model/reasoning combination is supported.
- **PVC typed context follow-up — COMPLETE FOR CURRENT NEEDS.** The
  model-context boundary now supports `SOURCE → image`, and `TASK`, `DIFF`,
  and `SEMANTIC → authenticated text`. TASK + DIFF review-package v0 was
  qualified at `8e8300c706501404432739e754e93ba4b6f4d5b6` (`Qualify PVC review
  package v0`). PVC/model context is not automatically Atlas semantic truth.
- **S1b.1 rust-analyzer semantic query v0 — QUALIFIED.** Checkpoint
  `f0bd8cd7ae32a783840855b2003db4816e80e6a2` (`Qualify rust-analyzer semantic
  query v0`) qualifies exactly `definition`, `references`, and `hover`.
  It has explicit executable authority, a fresh bounded LSP process per query,
  UTF-8 LSP positions, witnessed repository bytes, canonical deterministic
  `atlas-rust-semantic/1` output, normalized definition/reference/hover,
  path/URI authority, strict JSON/JSON-RPC, and complete timeout/cleanup.
  Implementations, diagnostics, `search_text`, Pyright, persistent reuse, and
  automatic selection are not implemented.
- **S1b.2 SEMANTIC PVC tablet v0 — QUALIFIED.** Checkpoint
  `9830692efc96d7e49916bd3f490668a65ee7350e` (`Qualify rust semantic PVC
  tablet v0`) carries `atlas-rust-semantic/1` through a SEMANTIC tablet and
  authenticated PVC `_TextAuthority` transport to exact model-facing context.
  The media type is `application/vnd.atlas.rust-semantic+json`. Canonical
  validation, deterministic identity, digest binding to authenticated
  payload SHA-256, exact byte preservation, effective-input binding, SOURCE
  IMAGE + SEMANTIC TEXT coexistence, and typed-PVC cleanup/lifetime are
  qualified. Final host suite: `1263 passed`.

The current planning model has three related lanes:

```text
R — Rust Atlas Core implementation
    production implementation of the existing semantic core

S — Semantic coordination capabilities
    software observations, task/obligation state, assurance planning,
    traceability, semantic zoom, orchestration

A — Atlas Agent infrastructure
    deterministic execution, isolation, qualification,
    journal/recovery, materialization, tool services
```

These lanes have explicit dependencies, but none is a universal prerequisite for all the others.

---

# 1. Product model

## 1.1 Atlas

Atlas remains the semantic computational knowledge system described by the existing specification and Core V1 profile.

The current semantic-core responsibilities include:

```text
identity / descriptions / values
facts / relations / vocabulary
scope / provenance / epistemic state
knowledge snapshots / supersession
rules / grounding
decision problems / selection
derivation dependencies / explanation
```

The new coordination work adds product capabilities around that semantic foundation:

```text
goals / accepted decisions / open questions
work representation / obligations / dependencies
software observations / impact reasoning
assurance planning
semantic traceability / semantic zoom
higher-level orchestration
```

Semantic coordination is therefore an extension of Atlas, not a replacement definition of Atlas Core.

## 1.2 Atlas Agent

Atlas Agent remains deterministic development and assurance infrastructure.

The governing split is:

> **Atlas owns semantic representation, interpretation, decision, and coordination. Atlas Agent guarantees how an authorized operation is executed, isolated, recorded, qualified, and materialized.**

Atlas Agent must not grow until it absorbs Atlas semantic responsibilities.

## 1.3 Specialized services

Tools and services such as:

```text
pi-visual-context (PVC)
rust-analyzer
Pyright
compilers
test runners
Git
Codex / other models
```

supply qualified domain material or results. A specialized-service result may
be:

- consumed directly as model context;
- interpreted by Atlas as an observation/evidence source;
- used in both ways.

The context path is:

```text
service material → model context → model reasoning
```

The observation path is:

```text
service result → Atlas interpretation/evidence → optional semantic admission
```

These paths may overlap, but neither implies the other. Atlas Agent qualifies
and executes the service; Atlas semantic admission remains a separate explicit
decision. PVC's primary near-term path is direct multimodal model context.

PVC is the first real one-shot context-compilation consumer. `rust-analyzer`
is now the first qualified interactive semantic-service consumer. Their
different lifecycle shapes should exercise common qualification principles
without forcing a premature universal provider framework.

---

# 2. Completed Atlas Agent foundation

The current Agent baseline remains the result of the v0.1.2 hardening, qualified-toolchain tranche, Astra Low review/adjudication, P0.6x closure, and M1 hygiene.

| Capability / tranche | Status | Representative checkpoint |
| --- | --- | --- |
| manual checkpoint correctness | DONE | `3aad255` |
| config/trust/auth/session isolation | DONE | `b4cc45c` |
| safe reuse fallback | DONE | `fd0073c` |
| per-dispatch Fast service tier | DONE | `cc1b9cd` |
| accepted-generation cancellation | DONE | `cde171f` |
| truthful scratch semantics | DONE | `833d275` |
| qualified development toolchains/caches | DONE | `046e182` |
| historical validity C1/C2/C4 | DONE | `846c344` |
| serialized run admission + C5 | DONE | `41c3718` |
| cache lock authority C6 | DONE | `25d4590` |
| full-suite regression migration | DONE | `2fd88d5` |
| M1 Core Hygiene | DONE | `2c97e70` |

Astra Low finding C3 remains **V1-COMPLIANT AS IS**: diagnosis and practical recoverability are required; exhaustive automatic repair of every crash window is not.

M1 closed with:

```text
967 passed
journal/state: MATCH
repository witness: MATCH
doctor: OK
```

The M1 stop rule remains authoritative:

> Once a bounded task satisfies its decided contract, required witnesses, and required qualification, close it. Do not convert task closure into generalized hardening.

---

# 3. M2 architecture review — completed, scope-corrected

The Astra Medium M2 review produced useful architecture observations, especially:

- execution status, material value, and qualification status are distinct;
- primary execution failure must not be hidden by secondary collection/parsing failure;
- qualification evidence must be bound to the material it qualifies;
- operational journal, evidence artifacts, and Git commits have different roles;
- requested / resolved / observed remains a useful runtime distinction;
- semantic navigation should expose backend capability and completeness rather than treating unsupported as empty.

However, the M2 prompt and source package were dominated by Atlas Agent and framed Atlas as if it were evolving from the transactional controller. That distorted milestone ordering and underrepresented the pre-existing Atlas Core semantic model.

Therefore:

```text
M2 findings about Agent mechanics/evidence       useful input
M2 global milestone ordering                    advisory only
existing Atlas specification/Core V1 semantics  retained authority
owner clarification after M2                    current architecture direction
```

Future architecture prompts must state explicitly that Atlas Agent is a subsystem of Atlas and that Atlas Core already has semantic responsibilities independent of Agent.

---

# 4. Implementation-language and repository direction

## 4.1 Existing Python Atlas Core

The existing Python Core V1 implementation is not discarded.

Its specification, profile, tests, fixtures, persistent examples, and behavior should serve as:

```text
active product-learning implementation
prototype / reference implementation
semantic design history
executable oracle and conformance evidence where appropriate
```

The semantic specification/profile remains above host-language details.
Python is not merely historical reference material or an oracle for a
predetermined Rust port. It is the active environment for learning which
semantic/context abstractions, recurring queries, authority boundaries,
ephemeral-versus-persistent state, and coordination concepts survive actual
use. It need not remain the production language forever; Rust should
preferentially encode contracts demonstrated by that experience rather than
mechanically porting current Python abstractions.

## 4.2 New Rust Atlas Core

New production Atlas Core development is intended to begin in **Rust**, but
substantial semantic-core implementation is **DEFERRED UNTIL SUFFICIENT
PYTHON DOGFOOD**. Rust remains the architectural destination and a roadmap
lane, not an active parallel implementation front before the required Python
product-learning cycle.

Repository:

```text
cyrilmhansen/atlas-core
```

Initial Rust bootstrap commit:

```text
52f69d5  chore: initialize Atlas Core Rust crate
```

The repository name is descriptive and may remain provisional. It is intended to host the production Rust implementation of the existing semantic core and product capabilities built around it; it does not redefine Core as code navigation alone.

Migration rule:

```text
semantic contract
    ↓
Python reference behavior / fixtures / tests
    ↓
Rust implementation
    ↓
conformance comparison
```

Do not translate Python files mechanically and do not require a big-bang port before new Atlas product work can continue.

## 4.3 Atlas Agent

Atlas Agent remains Python for now.

Current repository:

```text
atlas-py
```

Likely future name:

```text
atlas-agent
```

Do not rename it yet solely for cosmetic consistency.

If Agent is later migrated to Rust, prefer incremental replacement behind explicit contracts and reuse its existing tests/journals/fixtures as conformance evidence.

---

# 5. R track — Rust semantic-core implementation (deferred until sufficient Python dogfood)

The **R** track moves the existing Atlas semantic core toward its intended production Rust implementation.
It remains an architectural destination and roadmap lane, with substantial
implementation deferred until sufficient Python dogfood has produced
experience-backed contracts.

## R0 — Rust Core baseline

### Goal

Establish the Rust repository as a real Atlas Core implementation rather than an unrelated greenfield application.

### Scope

- document the relationship to the Atlas specification and Core V1 profile;
- establish minimal crate/module boundaries without prematurely reproducing the Python file layout;
- select the smallest existing semantic contract suitable for differential/conformance testing;
- establish a way to reuse or translate stable fixtures/test vectors without duplicating product semantics manually.

### Non-goals

- porting the entire Knowledge Store;
- reproducing all Python APIs;
- rewriting Atlas Agent;
- designing a universal plugin/RPC architecture;
- mixing observation-backend details into fundamental semantic types.

### Exit direction

At least one small existing semantic behavior is represented idiomatically in Rust and checked against the established Atlas contract/reference evidence.

---

## R1 — Semantic identity and value foundation

Candidate first semantic behaviors include the stable, highly local invariants already defined by Core V1:

```text
nominal IDs are distinct from content
host-language equality does not silently define Atlas equality
TRUE / FALSE / UNKNOWN remain distinct
ordered sequence != finite set
validated value forms do not rely on implicit host coercions
```

The exact first slice should be chosen from existing implementation/tests rather than invented anew.

---

## R2 — Knowledge / provenance / snapshots

Port the persistent semantic substrate only after the Rust value/identity model has proved stable enough.

Responsibilities eventually include:

- validated admission;
- provenance;
- vocabulary;
- immutable snapshots;
- supersession;
- historical/stale interpretation;
- dependency traversal.

SQLite remains a Core V1 implementation choice, not the semantic definition.

---

## R3 — Rules / grounding / decision / explanation

Migrate the higher semantic behavior:

```text
structured rule evaluation
grounding
finite decision problem construction
selection
reconstructed explanation from effective dependencies
```

Preserve the distinction between semantic requirements and Core V1 implementation choices.

---

# 6. S track — semantic coordination capabilities

The **S** track adds coordination capabilities around the Atlas semantic foundation. It can progress while R migration is still incomplete, provided it respects the existing Atlas semantic model instead of creating a competing one.

## S1 — Software Context and Observation

### Goal

Give Atlas and its model-facing workflows compact structured access to useful
software context and observations without repeatedly rediscovering the same
material through whole-file dumps, ad-hoc rendering, or lexical search.

Specialized software services can serve two distinct product paths:

```text
context path
    service material → model context → model reasoning

observation path
    service result → Atlas interpretation/evidence
    → optional semantic admission
```

The paths may overlap, but neither implies the other. S1a PVC and S1b
semantic code navigation therefore remain distinct capabilities.

### S1a — Visual Context Compilation / PVC

Near-term product goal: construct compact multimodal context for Atlas/model
work. PVC transforms selected source/reference material into SOURCE tablets
and long task/specification material into TASK tablets. VC IDs, source/line
ranges, and conservative symbol anchors provide an address map into supplied
context, not authoritative language semantics or Atlas facts.

The prototype is `cyrilmhansen/pi-visual-context`, baseline:

```text
818786a3a702cf314c2e18528b7b613523c316a6
fix: separate runtime and rendering work roots
```

Classical, PVC, and hybrid context modes remain first-class. Critical instructions, authorization boundaries, and small exact constraints normally remain text; normal tools remain available for exact, local, current, omitted, and verification material. A secondary role is portable visual-source context material that Atlas may later interpret as observation/evidence, but prepared context is not automatically admitted to Atlas semantic storage.

PVC and `rust-analyzer` are complementary: PVC provides broad dense visual
context and addressable tablets; rust-analyzer provides precise interactive
language semantics.

See [`pvc-observation-v0.md`](pvc-observation-v0.md).

Current model-facing context primitives are complementary and are not
automatically composed or selected:

```text
SOURCE   broad visual/source context
TASK     exact task/specification material
DIFF     exact repository transformation
SEMANTIC precise language-semantic result
```

### S1b — Semantic Code Navigation

Give Atlas compact structured access to software semantics through language-aware backends.

The qualified v0 query kinds are exactly:

```text
definition
references
hover
```

Later backend/query expansion remains open:

1. `rust-analyzer`;
2. Pyright or equivalent Python semantic backend;
3. syntax/AST helpers where needed;
4. exact text search as an explicit lexical fallback.

Normative distinctions include:

```text
unsupported capability
empty valid answer
known-incomplete answer
backend failure
output truncation
```

Semantic observations are not automatically Atlas facts. They may remain ephemeral, become referenced evidence, or later be explicitly admitted as semantic knowledge with provenance.

See [`semantic-observation-v0.md`](semantic-observation-v0.md).

### S1b subdivision

```text
S1b.1 — Semantic acquisition v0                 COMPLETE
S1b.2 — Semantic PVC transport v0                COMPLETE
S1b.3 — Semantic context selection/composition   NEXT
```

S1b.1 and S1b.2 are qualified bounded milestones, not invitations to
generalized hardening. S1b.3 has two explicit roles.

**Product capability.** One model-facing execution consumes an explicitly
selected composition of already-qualified context types:

```text
TASK + DIFF + SOURCE + SEMANTIC
```

The composition preserves ordering, provenance, authority, and exact payload
semantics. Selection is initially explicit and caller-driven.

**Product-learning / dogfood capability.** S1b.3 is part of the evidence loop
through which Atlas learns what to stabilize and potentially reimplement in
Rust. Its first important consumer is Atlas development itself; it is not
merely plumbing before later work. Use should expose which abstractions and
queries are useful, what is redundant or missing, how TASK, DIFF, SOURCE, and
SEMANTIC interact, what belongs to Atlas versus Atlas Agent, and which state
and coordination concepts survive sustained use. Observe and refine those
semantic, context, and coordination contracts before Rust implementation and
conformance work. No automatic optimizer is defined now.

### S1 non-goals

- persistent code-intelligence database;
- whole-program language-neutral graph;
- complete impact analysis;
- automatic test selection;
- parallel semantic-service execution;
- Pyright in the first real semantic backend slice;
- generalized RPC/provider framework;
- folding PVC artifact storage into Atlas semantic storage.

---

## S2 — Semantic Coordinator task state

### Goal

Represent enough task semantics that Atlas can coordinate work without reconstructing the complete problem from conversation history and repository exploration at every step.

Candidate concepts include:

```text
objective
accepted decision
open product question
obligation
constraint
candidate next action
relevant semantic anchors
```

Use existing Atlas semantic concepts where they genuinely fit. Do not automatically force transient operational state into the Knowledge Store.

Human/operator authority remains necessary for consequential product ambiguity, scope changes, new privileges, risk acceptance, and externally meaningful side effects.

---

## S3 — Assurance Planning

### Goal

Let Atlas decide what evidence is needed for a candidate change.

Atlas may reason:

```text
this material affects subsystem X
→ obligations A/B remain open
→ focused + integration qualification is required
```

Atlas Agent executes authorized qualification recipes and records evidence; it does not decide product correctness.

Software observations can improve impact reasoning, but no visual/static-analysis result may silently erase mandatory qualification policy.

---

## S4 — Semantic Traceability / Semantic Zoom

### Goal

Connect product intent, semantic knowledge, implementation, observations, tests, and evidence without maintaining a parallel manually curated requirements database.

Useful links may include:

```text
scenario
→ decision
→ invariant
→ enforcement boundary
→ source/symbol observation
→ witness test
→ qualification evidence
```

Keep human-asserted, tool-derived, and model-inferred links distinct.

Do not begin with a new graph database. Reuse existing Atlas identities/knowledge when appropriate and introduce additional anchors only when a real consumer needs them.

---

## S5 — Higher-level orchestration

### Goal

Use semantic/task representations for larger work:

- dependency graphs;
- resource constraints;
- specialized agent assignments;
- deterministic scheduling where agent reasoning is unnecessary;
- bounded replanning when evidence or product decisions change.

Build this from real R/S/A primitives rather than designing a speculative general scheduler first.

---

# 7. A track — Atlas Agent infrastructure

Agent work should proceed when it blocks Atlas product work or closes a concrete operational defect. Remaining possible hardening is not by itself a reason to postpone R or S work.

## A1 — Executor Outcome Robustness

Known motivating defect:

```text
primary event: model quota / service failure
secondary event: oversized JSONL/tool-output record
bad presentation: EXECUTOR_OUTPUT_MALFORMED hides primary cause
```

Required direction:

1. preserve primary execution/process/service failure;
2. record parser/report/telemetry/collection failures separately;
3. bound output reinjected into model context;
4. retain full useful output as an artifact where feasible;
5. support bounded/range retrieval;
6. keep historical outcome records readable without current runtime assets.

A1 is important maintenance but does **not** automatically precede S1.

---

## A2 — Qualified Tool Services

A2 develops the controlled execution substrate and then uses it for context compilation and semantic services. Share qualification and authority machinery where it genuinely fits; do not force one universal runtime abstraction.

### A2.0 — One-shot qualified tool-operation substrate — COMPLETE

Completed at checkpoint `6a0d300dbf0d40ea1666280109350d366c823ee2`
(historical; the current validated-result checkpoint is `b3a6f4d`):

```text
qualified controller-owned one-shot non-model operation
explicit argv
CapabilityPlan command/mount authority
isolated Bubblewrap execution
private operation scratch
bounded stdout/stderr, process ownership, timeout/process teardown
narrow PVC prepare adapter
```

A2.0 establishes substrate only. It does not complete snapshot validation,
durable operation-result/bundle publication, or full PVC qualification.

### A2.1a — Qualified real PVC execution — COMPLETE

Checkpoint: **`6a0d300`** (`feat(agent): add qualified PVC prepare execution`).
The completed tranche records:

- qualified runtime `cyrilmhansen/pi-visual-context` at
  `54777ee0254c6f3f4bc04ea8a5cdb2d58cf43221`;
- deterministic `pvc probe`, CapabilityResolver/CapabilityPlan authority, and
  exact command identity without ambient `PATH` fallback;
- read-only source project and controller-owned bundle, work, state,
  stdout, and stderr;
- a real Bubblewrap host witness for qualified PVC → `pvc prepare`.

This is qualified execution evidence, not a validated bundle and not Atlas
semantic observation/admission. See
[`pvc-observation-v0.md`](pvc-observation-v0.md) and
[`qualified-service-workflow.md`](qualified-service-workflow.md).

### A2.1b — Validated/materialized PVC result — IN PROGRESS

The **validated-result tranche is COMPLETE** at checkpoint
**`b3a6f4d`** (`atlas-agent: validate and retain qualified PVC results`).
The validated boundary includes real qualified PVC prepare, retained result
bytes, canonical `SourceContextSnapshot` validation, artifact integrity,
validated-state authority, deep immutability/alias isolation, and a real host
witness. It preserves the distinction:

```text
process success ≠ validated result ≠ semantic interpretation
```

The overall A2.1b materialized-result milestone remains open for durable
publication/materialization and lifecycle/recovery:

- durable materialization/publication;
- lifecycle and recovery as required.

### A2.2 — Multimodal model-context injection — CORE COMPLETE

The core SOURCE-tablet path is complete.

Representative implementation checkpoints:

```text
b724c398d9359de92f1c6b1ae3c0310947d7116a
Integrate validated PVC source context into Atlas execution

5af7774fde08e9a629cac5d8f6d2d2929a71f345
Use original image detail for PVC source context
```

A real Atlas generation can now consume an explicitly selected subset of a
validated PVC result as multimodal context. The qualified boundary includes:

- validated-result-only selection;
- deterministic ordered tablet selection and provenance framing;
- sealed controller-owned image descriptors exposed through `/proc/self/fd/N`;
- preservation of Bubblewrap runtime/server/lock/scratch semantics and
  `pass_fds`;
- repeated Codex `--image` transport with `--image-detail original`;
- fail-closed rejection of forged, stale, tampered, unsealed, or
  cross-executor image authority;
- unchanged text-only execution when no PVC context is selected;
- a real host witness where SOURCE tablets were semantically useful to the
  model.

This closes the core requirement that qualified PVC material can reach a real
model invocation without becoming Atlas semantic truth merely by transport.

Remaining PVC work is bounded follow-up, not a prerequisite for the next
product milestone:

- deterministic headless TASK-tablet preparation/injection when long task
  material needs a different preparation shape;
- model-facing address/index refinements only for demonstrated consumers;
- classical/PVC/hybrid comparative dogfood when useful to quantify quality,
  context coverage, latency, render cost, quota/accounting, task time, and
  tool-call trade-offs;
- A2.1b durable publication/lifecycle work only when a concrete consumer needs
  it.

Do not build an automatic context-selection optimizer or universal visual
context framework without evidence from real consumers.

### A2.3 — Persistent semantic service runtime

The first rust-analyzer semantic-service substrate is qualified through S1b.1,
but v0 deliberately starts a fresh bounded rust-analyzer process per query.
Persistent service lifecycle/reuse remains later A2.3 work only if repeated
real usage justifies it. Agent owns qualification, workspace/material binding,
configuration, capabilities, lifecycle, bounds, and truthful backend status;
Atlas interprets semantic results.

### A2.4 — Additional semantic backends

Add Pyright or an equivalent backend after the first service contract is demonstrated.

## A3 — Qualification Execution and Evidence

Execute authorized qualification recipes against identified material and record evidence without making Agent responsible for semantic sufficiency.

Candidate recipe classes:

```text
focused
affected
live
full
hygiene
```

Proof/evidence must distinguish sandbox, host, live, skip/host-required, failure, timeout, cancellation, and infrastructure failure truthfully.

### Operator-facing identity explanation — planned support, non-priority

The existing `doctor` and `status` commands provide workflow/state,
provenance, and repository-witness checks; they do not yet provide a
toolchain-diff command. Extend the existing doctor/qualification-evidence
concepts rather than creating a duplicate diagnostic architecture. Eventually
support should, when evidence permits, localize the mismatch to the smallest
concrete identity component rather than reporting only a whole-toolchain
mismatch. For the selected authority, diagnostics should explain:

```text
authority/component → identity expected → identity observed
                    → status/mismatch reason
                    → smallest safe corrective action when determinable
```

Useful components include an individual identity file, executable,
qualification probe, source revision/Git identity, source-root authority, or
selected capability manifest/qualification binding. Evidence may include the
selected capability manifest, qualification string, source-root authority,
source revision where applicable, executable and identity-file fingerprints,
and qualification probe. A generic
`ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH` alone is not sufficient when Atlas
Agent already possesses evidence that can localize the mismatch. Diagnostics
explain rejection; they do not weaken fail-closed qualification or authorize
an unqualified execution.

If Atlas Agent retains capability manifests, cryptographic hashes, probes,
source authority, identity-file sets, and repository witnesses, rapid
mismatch localization is part of the required operational return on that
complexity. Security that says only “no” is incomplete operationally when the
available evidence can explain precisely why. Simplification remains an
explicit option where retained complexity does not produce enough identifiable
value. This planned support remains non-priority unless a concrete defect
blocks current product work. Do not prescribe a new storage model or
fingerprint-manager subsystem.

Git commits remain neutral material snapshots.

---

## A4 — Tool Concurrency

Permit safe intra-generation concurrency without weakening the V1 single-`RUNNING`-generation rule.

Potential effect classes include:

```text
PURE_ANALYSIS
IMMUTABLE_SEMANTIC_READ
MUTABLE_WORKSPACE_READ
WORKSPACE_WRITE
DURABLE_CONTROL_WRITE
EXTERNAL_SIDE_EFFECT
```

Design request/observation structures so requested / resolved / observed concurrency can be represented, but execute serially first.

Qualified observation/semantic reads are the preferred first real parallel workload after the relevant A2/S1 paths work serially.

### Provider-neutral quota/capacity telemetry — FUTURE SUPPORT

Later Agent/orchestration support should be able to observe available model
capacity before an execution fails or unnecessarily consumes scarce premium
capacity. This is planning only and is advisory operational input, not
authorization. It remains distinct from model capability, monetary price, task
importance, security policy, and semantic correctness.

The provider-neutral concept should cover an observed provider and
account/credential scope with an observation time, one or more allowances, and
possible recovery options. An allowance may describe a rolling window, weekly
allowance, reserve, credits, or reset entitlement, scoped provider-wide, to a
product, model family, or specific model, with remaining/capacity, unit,
reset/expiry times, and availability where known. Recovery options may include
reset, banked reset, credits, waiting for reset, or another provider-supported
option. Allowances must preserve availability as `available`, `exhausted`,
`unavailable`, or `unknown` rather than fabricating precision. `exhausted`
means the allowance is known to exist but its currently usable capacity is
depleted; it remains distinct from `unavailable` and `unknown`. Provenance
should record source, freshness, and confidence/authority
using Atlas's existing provenance and epistemic principles; this is a
conceptual contract, not a frozen type or implementation.

OpenAI is the first planned adapter. Where actually exposed, desired
observations include rolling five-hour remaining/reset, weekly
remaining/reset, Luna Reserve presence/remaining/reset, credits, and banked
reset presence/count/expiry/resulting reset semantics. The implementation must
first determine which values are available through supported, stable,
authorized interfaces; it must not require scraping or brittle UI automation,
and today's OpenAI taxonomy is not a universal model.

Data quality must remain explicit:

```text
AUTHORITATIVE       provider-supported structured authority, where available
OBSERVED            current value from a supported client/status surface
INFERRED            estimate from historical consumption or behavior
UNKNOWN/UNAVAILABLE provider exposes insufficient information
```

Atlas must never present inferred quota as authoritative or fabricate
precision. Likely consumers include model selection, scheduling, avoiding
avoidable exhaustion, choosing Luna/Sol/Astra or deferring work, and explaining
a lower-cost/lower-capacity route. This later support item does not block current product work by default.

---

## A5 — Distribution / Install / Doctor

### A5.0 — Qualified-host release/install baseline — COMPLETE

Atlas Agent now has a supported immutable release/activation path on the
qualified development host.

Historical release baseline:

```text
cc0d687a1c94c926ade7ed6262b98a81c62e757c
Qualify rebuilt Codex runtime
```

The release chain now covers:

```text
qualified Codex source recipe / exact lineage
    ↓
reconstruct detached clean source worktree
    ↓
build with pinned effective cargo/rustc identities
    ↓
bounded release-version-only Cargo.lock refresh + restoration
    ↓
verify ELF/version/CLI contract
    ↓
prepare immutable runtime + update policy digest
    ↓
preflight policy/assets/native resolution + Luna/Sol/Astra smoke
    ↓
repository-boundary promotion
    ↓
git-archive immutable controller installation
    ↓
stable ~/.local/bin/aa activation
    ↓
installation verification + stripped-environment status/doctor witness
```

The active qualified runtime is:

```text
/home/john/luna/codex-atlas/releases/atlas-codex-20260913-1/codex
sha256 27b9ce2f13b4f344207250cb913457549bee8ef56525ec9617e8092a64acb568
```

The reconstruction contract pins exact source lineage, the effective build
toolchain, bounded Cargo.lock behavior, public runtime contract, policy digest,
and qualification witnesses. Byte identity across arbitrary absolute build
paths is not required for this historical release because the non-stripped
binary embeds build paths; repeated builds in the qualified environment are
stable.

This baseline is a qualified-host release/install path, not yet a claim of
cross-platform packaging or a general-purpose installer. Further release
hardening should occur only for a concrete defect or distribution consumer.

### A5.1 — Graphical operator golden path — FUTURE

Derive a compact one-page flow/state reference from
[`operator-cheatsheet.md`](operator-cheatsheet.md): show the complete normal
lifecycle at a glance, beginning with fresh shell/bootstrap into a ready
operator environment, plus interruption and checkpoint-recovery branches.
Optimize it for human scanning and deliberate use as multimodal prompt context;
use stable, machine-readable labels where practical. Keep the textual
cheat sheet canonical so a future SVG/PDF/PNG or equivalent can be regenerated
and checked for drift; do not choose tooling until a documentation pipeline is
justified. Retained operational complexity must provide identifiable value
(authority/security, deterministic operation, recovery, provenance, lower
operator cognitive load, or removal of manual failure modes); otherwise
simplification remains an explicit option.

---

## A6 — Policy / Network / Timeouts / Routing

Refine policy only where concrete usage requires it.

### A6.1 — Selectable model execution profiles — COMPLETE

The qualified profile layer provides small, explicit model/reasoning selection
without coupling compute choice to security authority. Retained profiles are:

```text
luna-high
sol-medium
astra-medium
```

The implementation/default policy remains deliberately small:

- preserve all existing action defaults when no profile is requested;
- allow a bounded named profile to select only model/reasoning and, where
  already supported, service tier;
- keep sandbox, network authority, capabilities, session/storage semantics,
  tool allowlists, and approval policy owned by the action/policy rather than
  by the compute profile;
- fail closed on unknown or incompatible profile/model combinations;
- preserve requested / resolved / observed identity in execution evidence;
- avoid immediately encoding a large Luna/Sol/Astra × reasoning-level matrix.

Do not imply that every model/reasoning combination is supported. Broaden the
matrix only after real usage shows which additional profiles are worth
retaining.

### A6.2 — Later policy refinements

Possible later work remains:

- distinct timeout classes;
- truthful network requested/resolved/enforced/observed semantics;
- broader per-dispatch model/reasoning/service-tier routing;
- versioned project/role prompt composition.

Avoid a generalized policy framework without consumers.

## A7 — Isolated Parallel Generations

The V1 rule remains:

```text
one RUNNING generation per controlled repository/workflow
```

Future generation-level parallelism requires explicit repository/workspace isolation. Worktree support, if desired, belongs here as an architectural feature rather than an opportunistic Bubblewrap patch.

---

# 8. Cross-lane dependencies

The roadmap is intentionally not one total ordering.

```text
existing Atlas semantic contract / Python reference
        ↓
Python product learning / dogfood
        ↓
R0 → R1 → R2 → R3

A2.0 one-shot qualified tool-operation substrate
        ↕
S1a PVC visual context compilation

A2.3 qualified semantic service
        ↕
S1b semantic code navigation

S1 observations
        → S2 coordinator gets better software structure/context
        → S3 assurance planning gets better impact evidence
        → S4 can derive source/symbol-level traceability

S2/S3/S4 may reuse R semantic concepts where appropriate
but must not wait for complete Rust migration if the contract already exists
and Python dogfood has demonstrated the need

S3 assurance planning
        ↔ A3 qualification execution/evidence

A2/S1 serial operation semantics
        → A4 parallel observation/semantic reads

R semantic substrate + S coordination primitives
        → S5 higher-level orchestration
```

A2.0 may inform A2.1, but completing every PVC-specific lifecycle concern is not a prerequisite for semantic navigation. Reuse only the substrate demonstrated common by both consumers.

A1 is an independent maintenance lane unless a concrete S/R implementation hits the defective outcome boundary.

A5/A6 are also largely independent until a product slice requires them.

---

# 9. Immediate development direction

Version 0.12 keeps the release/install baseline closed unless a concrete defect
appears. Under the stop rule, the following bounded tasks are closed rather
than converted into generalized hardening:

- **A6.1**: selectable execution profiles are qualified;
- **PVC TASK/DIFF**: the current authenticated text transport is qualified;
- **S1b.1**: the bounded semantic query contract is qualified;
- **S1b.2**: the SEMANTIC tablet/model-context transport is qualified.

## 9.1 PVC — bounded closure only

The model-facing PVC context boundary is qualified for SOURCE image and TASK +
DIFF authenticated text. Remaining PVC work should be selected only when it
provides concrete product value:

```text
TASK tablets if long task material needs them
comparative classical/PVC/hybrid dogfood
small address/index refinements for real consumers
durability/lifecycle only when required
```

PVC is no longer the global next milestone, and TASK is no longer merely
future work.

## 9.2 S1b.3 — Explicit semantic context composition / dogfood — next

The caller explicitly selects a qualified semantic query/result and combines
the already-qualified context types through one model-facing execution:

```text
TASK + DIFF + SOURCE + SEMANTIC
```

Preserve provenance, ordering, and authority, and dogfood the result on Atlas
development. Do not add automatic query selection, composition, or optimizer
logic at this stage.

## 9.3 Richer S1b semantic navigation — later, evidence-led

Explore relevant-symbol/location selection and richer semantic queries only
where S1b.3 usage demonstrates the need. Persistent A2.3 service lifecycle and
reuse likewise remain later work only if repeated real usage justifies them.

## 9.4 R0/R1 — Rust Core conformance, deferred until sufficient Python dogfood

R0/R1 remains an architectural destination and roadmap lane, but is
**DEFERRED UNTIL SUFFICIENT PYTHON DOGFOOD**. Do not treat it as an immediately
available parallel product front or begin substantial Rust semantic-core work
after S1b.3 merely because the composition plumbing is complete. First use
S1b.3 for Atlas-on-Atlas Python dogfood, observe and refine the S1/S2
contracts, perform additional Python product work where justified, and
stabilize contracts demonstrated by actual use. There is no fixed quantitative
dogfood threshold.

After that experience, choose one small already-specified Atlas semantic
behavior and establish the first Rust conformance slice against the
Python/specification evidence.

Prefer stable local invariants with little persistence coupling, such as:

```text
nominal identity
TRUE / FALSE / UNKNOWN
sequence versus finite set
validated value forms without implicit host coercion
```

Do not block S1b on a complete Python-to-Rust migration.

## 9.5 Practical near-term sequence

```text
A6.1 selectable compute profiles — COMPLETE
        ↓
PVC TASK/DIFF follow-up — COMPLETE FOR CURRENT NEEDS
        ↓
S1b.3 explicit semantic/context composition
        ↓
sustained Atlas-on-Atlas Python dogfood
        ↓
refine S1/S2 contracts from observed use
        ↓
additional Python product work as justified
        ↓
stabilize contracts demonstrated by actual use
        ↓
R0/R1 Rust implementation/conformance only after contracts are sufficiently
experience-backed
```

The current next-priority sequence is therefore:

```text
S1b.3 explicit semantic/context composition
        ↓
sustained Atlas-on-Atlas Python dogfood
        ↓
refine S1/S2 contracts from observed use
        ↓
additional Python product work as justified
        ↓
stabilize contracts demonstrated by actual use
        ↓
R0/R1 only after contracts are sufficiently experience-backed
```

A2.3 richer/persistent lifecycle work remains demand-driven: pursue it only
when S1b.3 and dogfood demonstrate a concrete need. A1 and other open Agent
maintenance items remain non-prerequisites unless a concrete defect blocks
product work. R0/R1 is not a current parallel implementation priority;
additional Agent hardening is not required before the Python product-learning
cycle.

After these primitives are exercised by real consumers, continue toward:

```text
S2 task / obligation state
→ S3 assurance planning
→ S4 semantic traceability / semantic zoom
→ S5 higher-level orchestration
```

Do not reopen release hardening, generalized provider frameworks, or speculative
multi-agent scheduling without a concrete blocker or consumer.

---

# 10. Durable principles retained from hardening and Core V1

## 10.1 Semantic authority is explicit

Host-language equality, ordering, coercion, persistence behavior, PVC/LSP output, model prose, and test success do not silently define Atlas semantics.

## 10.2 Requested / resolved / observed

Where runtime preference and actual behavior may differ, preserve the distinction rather than collapsing them.

## 10.3 Historical validity is not reproducibility

Historical Agent audit/rebuild uses archived facts and authorities. Historical Atlas knowledge remains interpretable under its own snapshot/provenance rules. Neither requires arbitrary external model/tool behavior to remain re-executable forever.

## 10.4 Execution success, material value, and qualification are distinct

An interrupted execution may leave useful material. Qualification may later succeed or fail without rewriting the execution history.

For observation services, process success, observation validity, publication/materialization, and qualification are likewise distinct.

## 10.5 Git checkpoint is not certification

A Git commit records material state. Semantic correctness, proof/evidence, and disposition are separate concepts.

## 10.6 Recoverability is not exhaustive auto-repair

Diagnose precisely, fail safe, recover supported transactions, and preserve practical routes back to stable state. Do not build theoretical crash repair without demonstrated need.

## 10.7 Observation is not semantic authority

PVC produces context material/results that may serve as input to
Atlas-interpreted observations or evidence; materialization alone does not
create an Atlas observation. LSP, AST, exact text search, compilers, tests,
and models may produce observations. Admission as Atlas knowledge or
acceptance as a product decision remains explicit.

## 10.8 Avoid duplicated representations

Do not build a second manually maintained prose/code-intelligence world beside the Atlas semantic model and actual source/tooling. Link or derive where possible.

## 10.9 Scope discipline

Once the decided contract, witnesses, and required qualification for a bounded task are satisfied, close it.

---

# 11. Review strategy

Use review effort proportionally:

```text
micro deterministic correction
    → Luna Medium by default

local feature
    → Luna Medium; Sol Medium if nontrivial review is useful

cross-module execution/lifecycle change
    → Luna implementation + bounded Sol Medium review

systemic checkpoint
    → Astra Low only when the system-level question justifies scarce quota

architecture / representation decision
    → Astra Medium only when owner reasoning + cheaper models cannot resolve it efficiently
```

Astra results are advisory architecture input, not automatic product authority.

Future architecture review packages must include enough of the **Atlas semantic specification/Core profile** to prevent the Agent implementation from dominating the apparent product model.

Handoffs and reviews must preserve both product intent and engineering
contract; see [`agent-workflow.md`](agent-workflow.md).

---

# 12. Repository naming and layout

Current working layout:

```text
cyrilmhansen/
├── atlas-core        # Rust — production Atlas Core implementation
└── atlas-py          # Python — current mixed historical repository + Atlas Agent
```

Likely later:

```text
cyrilmhansen/
├── atlas-core
└── atlas-agent
```

Do not rename `atlas-py` yet merely for symmetry.

Do not create `atlas-protocol` until a real independently versioned shared package is justified by multiple consumers.

The final boundaries inside `atlas-core` should be learned from Rust semantic conformance work and multiple real observation consumers rather than frozen from repository naming alone.

## S1b.3 integrated context implementation note

The integrated execution boundary is implemented in Python using the existing
PVC/context-plan authority. See [integrated context](integrated-context.md) for
ordering, exact-byte semantics, selection bounds, operator inspection, legacy
compatibility, and the first Atlas parser dogfood scenario. Qualification and
checkpoint transitions remain Atlas-owned. Next: real-task dogfood of selection
quality, not additional language-server capabilities or a Rust migration.
