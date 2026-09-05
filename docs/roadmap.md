# Atlas / Atlas Agent — Roadmap

Document version: **0.6**  
Planning date: **2026-09-06**  
Code baseline: **`2c97e706f394b9392f27eae3d50ca210b3daeeac`** (`M1 Core Hygiene`)  
Architecture boundary: [`docs/architecture-boundaries.md`](architecture-boundaries.md)

This roadmap supersedes the single M3–M12 sequence from version 0.5.

The previous roadmap treated Atlas and Atlas Agent too much like one evolving component. The M2 Astra Medium review made useful observations about execution outcomes, material identity, evidence, and qualification, but its prompt and source package were dominated by Atlas Agent and blurred the product boundary. Its proposed global milestone order is therefore advisory rather than authoritative.

The current planning model separates two development tracks:

```text
Atlas Core        semantic coordination product
Atlas Agent       deterministic execution subsystem
```

They have explicit dependencies, but Atlas Core development must not be indefinitely postponed by unrelated Atlas Agent hardening.

---

## 1. Architectural boundary

The governing rule is:

> **Atlas decides what must be understood or accomplished. Atlas Agent guarantees how an authorized operation is executed, recorded, and materialized.**

See [`architecture-boundaries.md`](architecture-boundaries.md) for the detailed ownership model.

At a high level:

```text
                         ATLAS CORE
                   semantic coordination

 goals / decisions / work representation / obligations
 code understanding / impact / traceability / planning
 agent strategy / assurance planning / orchestration

                             │
                             ▼

                         ATLAS AGENT
                 deterministic execution

 admission / ownership / capabilities / sandbox
 model + tool execution / journal / recovery
 qualification execution / Git materialization
 provenance / durable runtime facts

                             │
                             ▼

                    SPECIALIZED SERVICES

 Codex / models / rust-analyzer / Pyright / Git
 compilers / test runners / linters / other tools
```

Semantic services are a useful example of the split:

```text
Atlas Core       asks and interprets semantic questions
Atlas Agent      qualifies and executes the service
rust-analyzer    computes Rust semantic observations
```

Atlas Agent must not grow until it absorbs Atlas Core responsibilities.

---

## 2. Completed foundation

### 2.1 Atlas Agent hardening baseline

The following work is complete and remains the foundation for future execution services:

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

### 2.2 M1 Core Hygiene — DONE

M1 intentionally changed no product semantics. It removed a small amount of stale/dead material, tightened deterministic test assertions, and refreshed documentation status.

The M1 stop rule remains important:

> Once a bounded task satisfies its decided contract, required witnesses, and required qualification, close it. Do not convert task closure into generalized hardening.

### 2.3 M2 architecture review — completed, scope-corrected

The Astra Medium M2 review produced useful architecture observations, especially:

- execution status, material value, and qualification status are distinct;
- primary execution failure must not be hidden by secondary collection/parsing failure;
- qualification evidence must be bound to the material it qualifies;
- operational journal, evidence artifacts, and Git commits have different roles;
- requested / resolved / observed remains a useful runtime distinction;
- semantic navigation should expose backend capability and completeness rather than treating unsupported as empty.

However, M2 was prompted as if Atlas itself were evolving from the transactional controller. That is not the current product boundary. Therefore M2 does **not** decide that Atlas Agent assurance work must precede Atlas Core semantic navigation.

The owner clarification following M2 is now authoritative: **Atlas Core and Atlas Agent are separate layers.**

---

## 3. Implementation-language and repository direction

### 3.1 Atlas Core

New Atlas Core development should begin in **Rust**.

Working repository/component name:

```text
atlas-core
```

The name is provisional and descriptive. Do not block development on final naming.

Python was acceptable as a prototyping and long-lived implementation language for Atlas Agent. It should not automatically become the production language for a new Atlas Core merely because the current repository is Python.

### 3.2 Atlas Agent

The existing implementation remains Python for now.

Current repository:

```text
atlas-py
```

Likely future repository name:

```text
atlas-agent
```

Do not rename the repository yet solely for cosmetic consistency.

### 3.3 Migration rule

Do not perform a big-bang Python-to-Rust rewrite of Atlas Agent before beginning Atlas Core.

If Atlas Agent is later migrated, prefer incremental replacement behind explicit versioned boundaries. Existing Python tests, journals, fixtures, error codes, and state transitions can serve as conformance evidence for replacement components.

Atlas Core must not depend on importing internal Python objects from Atlas Agent. The Core/Agent boundary should be explicit and versioned; a simple process/CLI + structured JSON boundary is acceptable initially.

---

# 4. Atlas Core track

The Core track is labeled **C1–C5**. It describes product capabilities rather than implementation-language layers.

## C1 — Semantic Observation

### Goal

Give Atlas a compact, structured way to observe code semantics instead of repeatedly rediscovering repositories through text search and whole-file dumps.

This is the first major Atlas Core capability and the first intended Rust implementation milestone.

### C1.1 Semantic Observation v0

Initial capability:

```text
definition
references
implementations
diagnostics
search_text
```

The precise wire/API syntax is not frozen yet.

Each observation should be able to report, as applicable:

```text
workspace/material identity
backend identity
query kind
supported / unsupported / incomplete
bounded result set
truncation / expansion information
source locations
```

The model-facing contract must distinguish:

```text
unsupported capability
empty valid answer
incomplete answer
backend failure
```

### Backend order

1. `rust-analyzer`;
2. Pyright or equivalent Python semantic backend;
3. syntax/AST helpers where language-server semantics are insufficient;
4. exact text search as an explicit fallback.

Rust is not merely a fixture language here. The new Core itself is intended to be Rust, and real Rust repositories such as existing Atlas-managed projects are valid integration subjects.

### C1.1 non-goals

Do not include yet:

- persistent semantic database;
- whole-program language-neutral graph;
- complete impact analysis;
- automatic test selection;
- parallel LSP query execution;
- Pyright in the first Rust backend slice;
- semantic traceability UI;
- generalized RPC framework.

### Exit criteria

Against a representative Rust project, Atlas can ask the initial semantic questions through an explicit Atlas/Agent boundary, receive bounded qualified observations, and fall back to exact text search without silently confusing lexical and semantic results.

---

## C2 — Semantic Coordinator

### Goal

Represent enough task semantics that Atlas can coordinate work without rebuilding the problem from conversation history and repository exploration at every step.

Candidate durable/working concepts include:

```text
objective
accepted decision
open product question
obligation
constraint
candidate next action
relevant semantic anchors
```

The coordinator should preserve what matters to the task, not create a prose twin of the repository.

### Human authority

The human/operator retains authority over consequential product ambiguity, scope changes, new privileges, risk acceptance, and externally meaningful side effects.

Models may propose decomposition, next actions, engineering choices, and review strategy within granted policy.

### Exit direction

A bounded development task can be resumed from explicit task state and targeted semantic observations rather than requiring the coordinator to reconstruct the entire situation from scratch.

---

## C3 — Assurance Planning

### Goal

Let Atlas decide what evidence is needed for a candidate change.

Atlas owns reasoning such as:

```text
this material affects subsystem X
→ obligations A/B are open
→ focused + integration qualification is required
```

Atlas Agent owns execution of authorized recipes and truthful recording of results.

Semantic navigation can improve impact reasoning, but passing static analysis or finding no callers must never silently erase mandatory qualification rules.

### Non-goal

Core must not acquire unrestricted host shell authority merely because it can reason about which tests should run.

---

## C4 — Semantic Traceability / Semantic Zoom

### Goal

Connect important product intent to implementation and evidence without maintaining a parallel manually curated requirements database.

Useful links include:

```text
scenario
→ decision
→ invariant
→ enforcement boundary
→ symbol
→ witness test
→ qualification evidence
```

Important distinctions:

- human-asserted links;
- tool-derived links;
- model-inferred links.

Inference must not silently become authority.

Semantic zoom should permit progressive disclosure from user intent down to exact code and proof evidence.

Do not begin with a graph database. Start with stable identifiers and links only when a real consumer requires them.

---

## C5 — Higher-level Orchestration

### Goal

Use the semantic/task representation to coordinate larger work:

- dependency graphs;
- resource constraints;
- specialized agent assignments;
- deterministic scheduling where agent reasoning is unnecessary;
- bounded replanning when evidence or product decisions change.

This is the later Atlas Core layer corresponding to the broader orchestration vision. It should be built from real C1–C4 primitives, not designed as a speculative general scheduler first.

---

# 5. Atlas Agent track

The Agent track is labeled **A1–A7**. Work here improves deterministic execution services and can proceed when it either blocks Core or closes a concrete operational defect.

## A1 — Executor Outcome Robustness

### Goal

Make execution outcomes truthful even when output/report collection also fails.

Known motivating case:

```text
primary event: model quota / service failure
secondary event: oversized JSONL/tool-output record
bad presentation: EXECUTOR_OUTPUT_MALFORMED hides primary cause
```

Required direction:

1. preserve the primary execution/process/service failure;
2. record report/parser/telemetry/collection failure separately;
3. bound output reinjected into model context;
4. retain full useful output as an artifact where feasible;
5. support explicit bounded/range retrieval;
6. keep historical outcome records readable without current runtime assets.

A1 is important maintenance, but it is **not a prerequisite for beginning C1** unless implementation discovers a direct dependency.

---

## A2 — Qualified Tool Services

### Goal

Expose long-lived or structured development services through explicit qualified Agent boundaries rather than allowing models to launch arbitrary user-state tools.

### A2.1 Semantic service runtime

This is the Agent-side dependency for C1.

For a language server, Agent should own or report, where relevant:

```text
qualified executable identity
version
workspace root / material binding
configuration
environment/capabilities
process lifecycle
resource bounds
response bounds
backend capability discovery
```

The first consumer is `rust-analyzer`.

Language servers may themselves execute build scripts, procedural macros, interpreters, or other helpers. Source-read semantics therefore do not automatically imply zero execution capability. Such behavior must be represented truthfully by the Agent service contract rather than hidden behind the word “read-only”.

### A2.2 Additional semantic backends

Add Pyright after the Rust contract has demonstrated useful shape. The second backend is intentionally a test of whether the interface generalizes across language semantics.

---

## A3 — Qualification Execution and Evidence

### Goal

Execute authorized project qualification recipes against identified candidate material and record evidence without making Agent responsible for deciding product correctness.

Candidate recipe classes include:

```text
focused
affected
live
full
hygiene
```

Proof attempts should distinguish at least outcomes such as:

```text
UNTESTED
SANDBOX_PASS
SANDBOX_SKIP_HOST_REQUIRED
HOST_PASS
HOST_FAIL
LIVE_PASS
```

with timeout/cancellation/infrastructure failure represented separately rather than collapsed into pass/fail.

Evidence must be bound to the material and environment it actually observed.

Automatic checkpointing may eventually depend on policy plus evidence, but Git commits remain neutral material snapshots.

---

## A4 — Tool Concurrency

### Goal

Permit safe intra-generation concurrency without weakening the V1 single-`RUNNING`-generation rule.

Likely effect distinctions include:

```text
PURE_ANALYSIS
IMMUTABLE_SEMANTIC_READ
MUTABLE_WORKSPACE_READ
WORKSPACE_WRITE
DURABLE_CONTROL_WRITE
EXTERNAL_SIDE_EFFECT
```

Concurrency should preserve requested / resolved / observed behavior.

Initial implementation should remain serial even if request structures become concurrency-ready. Qualified semantic reads are the preferred first real parallel workload once A2/C1 works serially.

The journal must not invent total causal order merely because durable event records are sequential.

---

## A5 — Distribution / Install / Doctor

Provide a supported installation path for the qualified Agent runtime and its machine prerequisites.

This remains important productization work but should not block early Core development on a machine where the current qualified environment already works.

Future responsibilities include:

- qualified runtime artifact distribution;
- deterministic installation;
- machine-level install doctor;
- stable launcher/activation;
- explicit controller/runtime provenance.

---

## A6 — Policy / Network / Timeouts / Routing

Refine policies only where concrete usage requires them.

Topics include:

- separate model/tool/generation/qualification timeouts;
- truthful network requested/resolved/enforced/observed semantics;
- per-dispatch model/reasoning/service-tier routing;
- versioned prompt/project/role overlays.

Avoid turning this milestone into a generalized policy framework before real consumers exist.

---

## A7 — Isolated Parallel Generations

Generation-level parallelism remains later work.

The V1 invariant stays:

```text
one RUNNING generation per controlled repository/workflow
```

Future parallelism requires explicit repository/workspace isolation, with independently controlled Git topology, journal ownership, caches, qualification, and integration.

Worktree support, if desired, belongs here as an architectural feature rather than as an opportunistic Bubblewrap patch.

---

# 6. Cross-track dependencies

The roadmap is no longer one total ordering.

Important dependencies are:

```text
A2.1 qualified semantic service
        ↕
C1 Semantic Observation

C1 observations
        → C2 coordinator can reason with better repository structure
        → C3 assurance planning can improve impact selection
        → C4 can derive symbol-level traceability

C3 assurance planning
        ↔ A3 qualification execution/evidence

A2/C1 serial semantics
        → A4 parallel semantic reads

C1 + C2 + C3 + C4
        → C5 higher-level orchestration
```

A1 executor robustness is an important independent maintenance lane. It should not automatically move in front of C1.

A5/A6 are also largely independent until a Core feature actually requires their missing capability.

---

# 7. Immediate next implementation

The next implementation target is a **joint C1 / A2.1 vertical slice**:

> **Semantic Observation v0 with rust-analyzer**

The purpose is not merely to add an LSP wrapper. It is to validate the new component boundary in real code:

```text
Rust Atlas Core
    asks a semantic question

Python Atlas Agent
    authorizes and executes a qualified semantic service

rust-analyzer
    produces the language-specific observation

Rust Atlas Core
    receives and interprets the structured result
```

Before implementation, define only the minimum boundary needed by this slice.

### Initial operations

```text
definition
references
implementations
diagnostics
search_text
```

### Required qualities

- explicit versioned Core/Agent message shape;
- qualified backend identity;
- workspace/material identity sufficient for the observation;
- bounded deterministic presentation;
- explicit unsupported/incomplete/error states;
- exact text search remains distinguishable from semantic references;
- serial execution initially.

### Explicit non-goals

- callers/callees if they materially complicate the first slice;
- complete semantic impact analysis;
- automatic test selection;
- post-generation qualification automation;
- semantic graph/database;
- tool concurrency execution;
- Pyright;
- Atlas Agent Rust rewrite;
- repository renaming;
- standalone protocol project.

The slice should be small enough that architectural lessons can change the next step without invalidating a large framework.

---

# 8. Durable principles retained from hardening

## 8.1 Requested / resolved / observed

Where runtime preference and actual behavior may differ, preserve the distinction rather than collapsing them.

## 8.2 Historical validity is not reproducibility

Historical Agent audit/rebuild uses archived facts and authorities. It does not require old cloud services, models, or tool binaries to remain executable forever.

## 8.3 Historical validity, execution success, material value, and qualification are separate

An interrupted execution can leave valuable material. Qualification can later succeed or fail against that material without rewriting the historical execution outcome.

## 8.4 Git checkpoint is not certification

A Git commit records material state. Proof/evidence/disposition are separate concepts.

## 8.5 Recoverability is not exhaustive auto-repair

Diagnose precisely, fail safe, recover supported transactions, and preserve practical routes back to stable state. Do not build theoretical crash repair without demonstrated need.

## 8.6 Semantic observation is not semantic authority

LSP, AST, text search, compilers, tests, and models produce observations. Product decisions and accepted invariants remain distinct authority.

## 8.7 Scope discipline

Once the decided contract, witnesses, and required qualification for a bounded task are satisfied, close it.

Do not use the existence of remaining possible hardening as evidence that Atlas Core must wait.

---

# 9. Review strategy

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

Astra results are advisory architecture input, not automatic product authority. Prompt scope must explicitly distinguish Atlas Core from Atlas Agent in future architecture reviews.

---

# 10. Naming and future repository layout

Current working direction:

```text
cyrilmhansen/
├── atlas-core        # Rust — semantic coordination product
└── atlas-py          # Python — current Atlas Agent implementation
```

Likely later:

```text
cyrilmhansen/
├── atlas-core
└── atlas-agent
```

Do not create `atlas-protocol` until a real independently versioned shared package is justified.

The final name of `atlas-core` may change after the first Core milestones. Naming should follow architecture rather than block it.
