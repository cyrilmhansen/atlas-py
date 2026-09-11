# Atlas / Atlas Agent — Roadmap

Document version: **0.9**
Planning date: **2026-09-11**
Agent code baseline: **`6a0d300dbf0d40ea1666280109350d366c823ee2`** (`feat(agent): add qualified PVC prepare execution`)

Architecture boundary: [`docs/architecture-boundaries.md`](architecture-boundaries.md)
PVC observation baseline: [`docs/pvc-observation-v0.md`](pvc-observation-v0.md)
Semantic navigation baseline: [`docs/semantic-observation-v0.md`](semantic-observation-v0.md)
Specialized-service qualification workflow: [`docs/qualified-service-workflow.md`](qualified-service-workflow.md)
Release procedure: [`docs/atlas-release-process.md`](atlas-release-process.md)
Project deployment: [`docs/deploy-existing-project.md`](deploy-existing-project.md)

This roadmap supersedes version 0.8.

Version 0.9 reframes PVC around its near-term product purpose: optimizing context supplied to Luna, Sol, and Astra through dense multimodal SOURCE and TASK tablets. The prototype provides empirical evidence for a model-specific strategy, not a universal quota, latency, or cost invariant. PVC-derived context material remains optional and secondary as input to Atlas-interpreted observations.

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

PVC is the first real one-shot context-compilation consumer. `rust-analyzer` remains the first planned interactive semantic-service consumer. Their different lifecycle shapes should exercise common qualification principles without forcing a premature universal provider framework.

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
prototype / reference implementation
semantic design history
executable oracle where appropriate
conformance evidence for Rust
```

The semantic specification/profile remains above host-language details.

## 4.2 New Rust Atlas Core

New production Atlas Core development begins in **Rust**.

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

# 5. R track — Rust semantic-core implementation

The **R** track moves the existing Atlas semantic core toward its intended production Rust implementation.

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

Near-term product goal: construct compact multimodal context for Atlas/model work. PVC transforms selected source/reference material into SOURCE tablets and, once an appropriate deterministic headless TASK operation exists, long task/specification material into TASK tablets. VC IDs, source/line ranges, and conservative symbol anchors provide an address map into supplied context, not authoritative language semantics or Atlas facts.

The prototype is `cyrilmhansen/pi-visual-context`, baseline:

```text
818786a3a702cf314c2e18528b7b613523c316a6
fix: separate runtime and rendering work roots
```

Classical, PVC, and hybrid context modes remain first-class. Critical instructions, authorization boundaries, and small exact constraints normally remain text; normal tools remain available for exact, local, current, omitted, and verification material. A secondary role is portable visual-source context material that Atlas may later interpret as observation/evidence, but prepared context is not automatically admitted to Atlas semantic storage.

PVC and `rust-analyzer` are complementary: PVC provides broad dense visual context and addressable tablets; rust-analyzer later provides precise interactive language semantics.

See [`pvc-observation-v0.md`](pvc-observation-v0.md).

### S1b — Semantic Code Navigation

Give Atlas compact structured access to software semantics through language-aware backends.

Initial query kinds remain:

```text
definition
references
implementations
diagnostics
search_text
```

Backend order:

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

Completed at current repository HEAD (`6a0d300dbf0d40ea1666280109350d366c823ee2`):

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

### A2.1b — Validated/materialized PVC result — NEXT

The next tranche remains responsible for:

- accepting `SourceContextSnapshot`;
- stdout/snapshot equivalence;
- bundle/artifact validation, including path, hash, media, and length checks;
- provenance binding;
- durable materialization/publication;
- lifecycle and recovery as required.

### A2.2 — Multimodal model-context injection

Make a real model invocation consume selected context:

- SOURCE tablet injection;
- deterministic headless TASK tablet support/injection;
- model-facing tablet/address index;
- real Luna/Sol/Astra dogfood;
- explicit classical/PVC/hybrid context modes;
- measurement of quality, context coverage, quota/accounting, latency, render cost, task time, and sequential tool-call trade-offs.

The near-term dogfood milestone follows the A2.1b result boundary: for one
real Agent generation, explicitly choose a bounded set of principal files and
optionally long task material, prepare and validate it through qualified PVC,
attach the tablets to the model invocation, and retain normal tools. Compare
all three modes on the same representative task. Do not build an automatic
context-selection optimizer yet.

### A2.3 — Persistent semantic service runtime

First consumer: `rust-analyzer`. Agent owns qualification, workspace/material binding, configuration, capabilities, lifecycle, bounds, and truthful backend status; Atlas interprets semantic results.

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

---

## A5 — Distribution / Install / Doctor

Provide a supported installation and activation path for qualified Agent runtimes and machine prerequisites.

Important productization work, but not a blocker for early R/S work on a machine where the qualified environment already functions.

---

## A6 — Policy / Network / Timeouts / Routing

Refine policy only where concrete usage requires it:

- distinct timeout classes;
- truthful network requested/resolved/enforced/observed semantics;
- per-dispatch model/reasoning/service-tier routing;
- versioned project/role prompt composition.

Avoid a generalized policy framework without consumers.

---

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

Three early streams are now valid and complementary.

## 9.1 R0 — Rust Core foundation

The new `atlas-core` repository exists and has a clean Rust bootstrap.

Next R action:

> choose one small, already-specified Atlas semantic behavior and establish the first Rust conformance slice against existing Python/specification evidence.

Do not pick the semantic behavior by convenience alone; inspect the existing Core implementation/tests and prefer a stable local invariant with little persistence coupling.

## 9.2 S1a / A2.1 / A2.2 — PVC context dogfood

A2.0's one-shot substrate is complete. The next product slice is qualified PVC context preparation followed by multimodal model-context injection:

```text
real Agent generation
    ↓ explicit bounded source/task selection
qualified PVC preparation
    ↓ validate provenance and bundle
SOURCE + TASK tablets and address index
    ↓
Luna / Sol / Astra invocation
    ↓
normal tools remain available
```

The first comparison must run classical, PVC, and hybrid strategies on the same representative task and measure quality/coverage, quota/accounting, latency, preparation cost, task time, and tool-call count. Selection may initially be explicit and deterministic.

See [`pvc-observation-v0.md`](pvc-observation-v0.md).

## 9.3 S1b / A2.3 — Semantic Code Navigation v0

The existing semantic-observation design remains valid for `rust-analyzer`.

The intended boundary remains:

```text
Rust Atlas implementation
    asks a semantic question

Python Atlas Agent
    authorizes and executes a qualified semantic service

rust-analyzer
    produces the language-specific observation

Rust Atlas implementation
    receives and interprets the bounded structured result
```

A deterministic fake/fixture backend may prove transport and status normalization first, but completion requires the qualified real backend.

Initial operations remain:

```text
definition
references
implementations
diagnostics
search_text
```

The slice should be small enough that implementation experience can still change the protocol without invalidating a large framework.

## 9.4 Scheduling between R0, PVC, and semantic navigation

None of the three streams is a universal hard prerequisite of the others.

A practical near-term sequence is:

```text
PVC A2.1/A2.2 qualified context-preparation and model-invocation dogfood
→ use only demonstrated reusable one-shot substrate
→ continue rust-analyzer A2.3/S1b without inheriting PVC-only assumptions

in parallel / alternating:
R0 small semantic conformance slices
```

This is preferable to attempting a complete Python→Rust migration, a complete generic observation framework, or a complete language-navigation subsystem before obtaining feedback from real consumers.

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
