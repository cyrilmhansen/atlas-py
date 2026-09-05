# Atlas / Atlas Agent — Roadmap

Document version: **0.5**  
Planning baseline: **2026-09-05**  
Repository baseline: **`develop/core-v1` at `2fd88d5343c998439186c01fa5f4541040180276`**

This roadmap replaces the previous P0/P1-oriented sequencing. The earlier roadmap mixed foundational correctness, installability, executor robustness, ergonomics, and long-horizon architecture into one priority ladder. That was useful during the initial hardening phase, but it no longer describes the system we are building.

Atlas Agent has now crossed a planning boundary: the core transactional controller is sufficiently coherent that the next work should focus on semantic coordination, post-generation assurance, qualified developer tooling, and a cleaner separation between deterministic control and model reasoning.

This document is a prioritization and exit-criteria document. It is not a catalogue of every possible Atlas feature.

---

## 1. Current baseline

The current baseline is the state reached after the v0.1.2 hardening work, the qualified-toolchain tranche, the Astra Low systemic review, owner adjudication, Sol Medium qualification, and the P0.6x closure work.

### 1.1 Completed foundation

| Capability / tranche | Status | Representative checkpoint |
| --- | --- | --- |
| Manual checkpoint correctness | DONE | `3aad255` |
| Config/trust/auth/session isolation | DONE | `b4cc45c` |
| Safe reuse fallback | DONE | `fd0073c` |
| Per-dispatch Fast service tier | DONE | `cc1b9cd` |
| Accepted-generation cancellation | DONE | `cde171f` |
| Truthful scratch semantics | DONE | `833d275` |
| Qualified development toolchains/caches | DONE | `046e182` |
| Historical validity C1/C2/C4 | DONE | `846c344` |
| Serialized run admission + C5 | DONE | `41c3718` |
| Cache lock authority C6 | DONE | `25d4590` |
| Full-suite regression migration | DONE | `2fd88d5` |

Astra Low finding C3 remains explicitly **V1-COMPLIANT AS IS**: recoverability and diagnosis are required; exhaustive automatic repair of every crash window is not.

The closure suite at the planning boundary is:

```text
967 passed
journal/state: MATCH
repository witness: MATCH
doctor: OK
```

### 1.2 Core controller model now considered stable enough to build on

The current system provides, at minimum:

- immutable prompt admission;
- durable request/execution lifecycle;
- journal replay and state rebuild;
- crash-aware spool transactions;
- deterministic Git checkpointing;
- cancellation of unstarted accepted generations;
- fresh/reuse resolution with historical replay semantics;
- Bubblewrap execution isolation;
- truthful writable scratch capabilities;
- qualified development toolchains and persistent mutable caches;
- historical documentary validation independent of current runtime assets;
- one `RUNNING` generation per controlled repository/workflow in V1;
- host qualification proven against the complete test suite.

This baseline is not an invitation to continue generalized hardening. New foundation work should be driven by concrete failures or by an explicit dependency of a planned milestone.

---

## 2. Durable architectural principles

### 2.1 Deterministic controller, model-assisted coordination

Atlas should keep authority over deterministic operations:

```text
admission
resource grants
sandbox/runtime selection
journal transitions
host qualification
Git checkpointing
recovery boundaries
```

Models may reason, propose, inspect, diagnose, select among authorized operations, and produce material work, but they should not silently become the authority for controller state.

### 2.2 Coordinator is a semantic role, not an interactive shell

The long-term coordinator should maintain the semantic state of the task rather than repeatedly rediscovering the repository by opening arbitrary files.

Conceptually:

```text
human goal / ambiguous product decision
        ↓
semantic coordinator
        ↓
work decomposition / review level / proof obligations
        ↓
specialized model agents
        ↓
deterministic Atlas controller
        ↓
repository / tools / qualifications / journal
```

The coordinator owns questions such as:

- what is the current objective;
- which product decisions are already fixed;
- which obligations remain open;
- which invariants are affected;
- which agent/review level is appropriate;
- what evidence is sufficient to close the task;
- whether to continue, correct, qualify, or checkpoint.

### 2.3 Requested, resolved, observed are distinct dimensions

Where runtime behavior may legitimately differ from preference, Atlas should preserve all three layers rather than collapse them.

Examples include:

```text
session mode
model
reasoning effort
service tier
tool concurrency
network capability
```

The generic shape is:

```text
requested
resolved
observed
```

A supported fallback is not automatically an execution failure.

### 2.4 Historical validity is not historical reproducibility

Historical report/audit/rebuild must use archived facts and authorities rather than requiring the current runtime, current assets, or current cloud service to still exist.

Atlas does **not** promise arbitrary historical re-execution or bit-for-bit reproducibility of external model behavior.

### 2.5 Historical validity, execution success, and content quality are different

An interrupted execution is still history. It may also have produced legitimate durable material.

Therefore:

```text
historical validity ≠ execution success ≠ content quality
```

Git commits remain neutral snapshots of material state; they are not success certificates.

### 2.6 Recoverability is not automatic recovery

V1 requires:

- reliable inconsistency/corruption diagnosis;
- fail-safe stop at invalid authority boundaries;
- practical return to or identification of a known stable state;
- recovery of important interrupted transactions where explicitly supported.

V1 does not require automatic repair of every theoretically possible crash point.

### 2.7 One RUNNING generation per repository remains the V1 rule

Parallelism is useful, but concurrent writers in one controlled checkout are not part of the current model.

Near-term rule:

```text
one controlled repository/workflow
→ at most one RUNNING generation
```

Future generation-level parallelism should use explicit workspace/repository isolation.

### 2.8 Tool-level concurrency is a separate concern

Multiple tool calls inside one running generation may be concurrent when their effect classes permit it. This does not weaken repository-level generation serialization.

### 2.9 Proof states must be explicit

A skipped sandbox test is not equivalent to a passed host proof.

Planned proof vocabulary:

```text
UNTESTED
SANDBOX_PASS
SANDBOX_SKIP_HOST_REQUIRED
HOST_PASS
HOST_FAIL
LIVE_PASS
```

A required proof that is skipped remains an open obligation.

### 2.10 Semantic traceability should be linked, not duplicated

Atlas should avoid creating a second manually maintained prose representation of the software.

Prefer navigable links between:

```text
scenario
→ decision
→ invariant
→ enforcement boundary
→ implementation symbol
→ witness test
→ qualification evidence
```

Text at different resolutions should be generated from or anchored to this graph where practical.

### 2.11 Scope discipline is part of correctness

The stop rule for normal engineering work is:

> Once a ticket satisfies its decided contract, required witnesses, and required qualification, close it. Do not turn task closure into an open-ended search for additional hardening.

Architecture work is different: its purpose may be to refine the representation itself. The process should not impose architecture-review weight on routine bounded work.

---

# M1 — Core Hygiene

## Goal

Reduce debt accumulated during the discovery/hardening phase **without changing product semantics**.

M1 is deliberately small. It prepares the codebase and documentation for the architecture review that follows; it is not a refactoring programme.

## Scope

Allowed work includes:

- comments that became false, misleading, or stale;
- small helpers that remove obvious semantic duplication;
- dead or redundant internal APIs now known not to have a public compatibility contract;
- overly broad test assertions where a deterministic `WorkflowError` exists;
- naming that still confuses admission, execution, replay, reconstruction, or historical validation;
- documentation of established distinctions such as:
  - authority vs observation;
  - requested / resolved / observed;
  - current admission vs historical replay;
  - `RUNNING` as controller ownership;
  - Git snapshot vs success certification.

Explicitly out of scope:

- redesign of `Workflow.execute()`;
- new lifecycle features;
- generalized mount/sandbox redesign;
- installer/distribution work;
- LSP implementation;
- post-generation automation;
- tool concurrency implementation.

## Exit criteria

- no intended product-semantic change;
- focused tests for touched code pass;
- full host suite passes;
- `git diff --check` passes;
- comments/documentation no longer contradict the current lifecycle model.

## Deliverable after M1

Create **Repomix v2** for architectural review, containing at least:

```text
tools/atlas_agent/workflow.py
tools/atlas_agent/journal.py
tools/atlas_agent/spool.py
tools/atlas_agent/policy.py
tools/atlas_agent/toolchains.py
tools/atlas_agent/bubblewrap.py
tools/atlas_agent/executor.py
tools/atlas_agent/codex_executor.py
tools/atlas_agent/repository.py
tools/atlas_agent/cli.py
tools/atlas_agent/prompt.py
```

Include the relevant architecture/context notes and the current roadmap.

---

# M2 — Atlas 2026 architecture review — Astra Medium

## Goal

Use a bounded architecture review to decide how Atlas should evolve from a reliable transactional controller into a semantic coordinator without weakening deterministic control boundaries.

This is not another broad bug hunt. Its output is architectural decisions and sequencing guidance, not implementation patches.

## Required review topics

### M2.1 Coordinator role

Clarify responsibilities between:

```text
human operator
semantic coordinator
specialized model agents
deterministic controller
external tools/runtimes
```

### M2.2 Semantic Code Navigation

Decide the architecture for semantic repository observation using:

```text
LSP / compiler semantic services
AST / syntax structure
text search fallback
```

### M2.3 Post-generation lifecycle

Define the transition from model completion to qualified material state:

```text
model result
→ diff understanding
→ impacted surface
→ proof selection
→ host qualification
→ disposition
→ checkpoint
```

### M2.4 Semantic traceability / semantic zoom

Decide how to preserve navigable links among scenarios, decisions, invariants, code symbols, tests, and qualification evidence without maintaining a parallel prose model of the software.

### M2.5 Tool-call concurrency

Account for runtimes/models capable of issuing asynchronous or concurrent tool calls. Distinguish tool concurrency from generation concurrency.

### M2.6 Journal and evidence architecture

Clarify boundaries among:

- operational journal;
- derived/projected state;
- execution reports;
- qualification evidence;
- future Git-versionable documentary exports.

## Exit criteria

- explicit architectural decisions for the six topics above;
- unresolved product questions identified separately from implementation questions;
- revised dependency order for M3+ if needed;
- no code change required to declare M2 complete.

---

# M3 — Semantic Code Navigation substrate

## Goal

Give the coordinator and reviewers a compact semantic interface to the codebase so that normal inspection does not depend on repeated `rg`/file-dump exploration.

## Minimal conceptual API

```text
code.definition(symbol)
code.references(symbol)
code.callers(symbol)
code.callees(symbol)
code.implementations(symbol)
code.document_symbols(file)
code.workspace_symbols(query)
code.diagnostics(scope)
code.search_text(query)
```

The exact interface is an M2 decision; this list describes required capability, not frozen syntax.

## Backend strategy

Initial intended order:

1. `rust-analyzer`;
2. Pyright or equivalent Python semantic backend;
3. structured syntax/AST helpers where LSP is insufficient;
4. exact text search as an explicit fallback.

Rust is a useful first target even though Atlas Agent is implemented in Python because Rust semantic tooling is strong and immediately useful on real Atlas-managed projects.

## Qualification model

Language servers are controller-managed qualified tools. A model should not silently launch arbitrary language-server binaries from user state.

Atlas should bind, where relevant:

- executable identity;
- version;
- workspace root;
- configuration;
- environment;
- response bounds.

## Exit criteria

For representative projects, a reviewer can answer questions such as:

```text
where is this symbol defined?
who calls it?
what implementations satisfy this interface/trait?
what diagnostics affect it?
```

without normal reliance on iterative whole-file dumping.

---

# M4 — Post-generation Assurance

## Goal

Move the currently manual coordination loop into an explicit Atlas lifecycle.

Today the human/coordinator often performs:

```text
agent completed
→ inspect report
→ inspect diff
→ infer affected area
→ select host tests
→ run qualification
→ decide disposition
→ request checkpoint
```

M4 should make this a first-class deterministic workflow with model assistance where reasoning is useful.

## M4.1 Versioned qualification recipes

Projects should be able to define authorized recipes such as:

```text
focused
affected
live
full
hygiene
```

The controller executes recipes. Models may recommend or select among authorized recipes; they do not receive unrestricted host shell authority merely because qualification is needed.

## M4.2 Explicit proof states

Implement durable or reportable proof-state distinctions, including host-required status for sandbox skips.

## M4.3 Qualification selection

Use diff information and, where available, semantic navigation to derive candidate affected areas and tests.

The model can reason about sufficiency; the controller owns execution and records the evidence.

## M4.4 Diff disposition

Support an explicit outcome vocabulary such as:

```text
ACCEPT
NEEDS_REVIEW
NEEDS_FIX
NEEDS_HOST_PROOF
REJECT
```

Exact names are not frozen before M2/M4 design.

## M4.5 Automatic checkpoint eligibility

When all required obligations are closed, Atlas should be able to advance to checkpoint without repeated operator ceremony.

The Git commit remains a neutral material snapshot. Qualification evidence is separate metadata.

## M4.6 Crash-safe material preservation

The lifecycle must account for:

- agent termination after useful changes;
- qualification interruption;
- unexpected operator changes;
- checkpoint interruption;
- useful patch with failing qualification.

Do not require exhaustive automatic repair; preserve evidence and maintain a diagnosable path to continuation.

## Exit criteria

A normal bounded implementation can proceed from completed generation to qualified checkpoint with no ad hoc host commands beyond explicitly authorized/operator-selected exceptions.

---

# M5 — Executor Reliability and runtime identity

M3 and M5 may be reordered after M2. They can also proceed partially in parallel if their interfaces remain independent.

## M5.1 Preserve primary executor failures

A secondary report/parser failure must never mask the primary executor failure.

Known motivating case:

```text
primary event: model quota / service failure
secondary event: oversized JSONL/tool-output record
bad presentation: EXECUTOR_OUTPUT_MALFORMED hides primary cause
```

Required rule:

> If execution fails and result/report extraction also fails, Atlas preserves and presents the primary execution failure while separately recording the secondary observation failure.

## M5.2 Bounded model-facing tool output

Large tool output should be retained durably but reinjected into model context through bounded observations.

Conceptually:

```text
full output
→ durable spool/blob + identity

bounded excerpt/summary
→ model context

explicit range retrieval
→ when needed
```

Limits should be large enough for modern development workflows and should not repeat the overly aggressive historical tiny-output limits.

## M5.3 Refresh the qualified controller/runtime boundary

Replace development-time dependence on an old frozen controller checkout with a current qualified runtime boundary and explicit provenance.

## M5.4 Per-dispatch model/reasoning/tier selection

Make selection explicit and provenance-aware:

```text
requested model / reasoning / tier
resolved model / reasoning / tier
observed model / reasoning / tier
```

This supports deliberate routing of routine implementation, bounded review, systemic review, and architecture work.

## Exit criteria

Executor failures remain truthful under secondary collection failures, tool-output context is bounded without discarding durable evidence, and dispatch provenance can represent model/reasoning/tier selection explicitly.

---

# M6 — Tool concurrency

## Goal

Support safe intra-generation concurrency for runtimes/models that can issue asynchronous tool calls, without weakening the V1 one-`RUNNING`-generation rule.

## Policy model

Do not model this as an unqualified `async = true` flag.

A likely policy shape is:

```text
tool concurrency requested
tool concurrency resolved
tool concurrency observed
```

with a requested mode similar to:

```text
serial
parallel-safe
```

Exact names remain an M2/M6 design decision.

## Effect classes

Concurrency decisions should consider operation effects, for example:

```text
READ
PURE_ANALYSIS
WORKSPACE_WRITE
DURABLE_CONTROL_WRITE
EXTERNAL_SIDE_EFFECT
```

Several semantic-navigation reads may safely run concurrently. Git index mutation, checkpoint transitions, and journal authority writes generally require stronger serialization.

## Partial order

Concurrent tool execution means request order, completion order, and model-consumption order may differ.

Atlas must not fabricate a false sequential causal history.

Conceptually:

```text
batch 17
  A requested
  B requested
  C requested

  B completed
  C completed
  A completed

model continuation
```

## Runtime fallback

If concurrency is requested but unsupported by the selected runtime:

```text
requested = parallel-safe
resolved = serial
reason = runtime_unsupported
```

This is an expected fallback, not necessarily an error.

## Exit criteria

Safe read/analysis tools can execute concurrently under an explicit controller policy; mutating/control operations remain correctly ordered; journal/evidence representation preserves causal truth.

---

# M7 — Semantic Traceability and Semantic Zoom

## Goal

Make product intent, invariants, implementation, tests, and qualification evidence navigable as one linked system without duplicating the software in a manually maintained requirements database.

## Core graph

A minimal useful graph connects:

```text
scenario
↕
decision
↕
invariant
↕
enforcement boundary
↕
implementation symbol
↕
witness test
↕
qualification evidence
```

Example:

```text
INV-RUN-001
"one RUNNING generation per repository"

implemented by:
  Workflow._admit_run_start

reachable from:
  Workflow.start_run
  Workflow.execute
  Workflow.dispatch
  Workflow.recover

witnessed by:
  lifecycle admission/recovery tests

introduced by:
  41c3718

qualified by:
  host full suite
```

## Semantic zoom

The same semantic object should be viewable at multiple resolutions:

```text
one-line intent
user scenario
product rule
formal invariant
enforcement boundaries
tests
implementation symbols
qualification history
```

Comments should preserve rationale/invariants, not restate code.

## Exit criteria

A coordinator or reviewer can navigate from a user-facing rule to current enforcement code and proof evidence, and back, without relying on a separately maintained prose matrix.

---

# M8 — Versionable documentary evidence

## Goal

Keep the operational journal local and authoritative while producing a compact immutable documentary export that can be versioned with Git.

Do **not** put the raw operational `.git/atlas-agent/events.jsonl` into Git as the normal mechanism.

A future execution/decision manifest should be able to bind, as appropriate:

- Git commit;
- relevant generations;
- decision/invariant identifiers;
- qualification results;
- important immutable artifact identities;
- controller/runtime provenance.

This is documentation and audit traceability, not a promise of model-output reproducibility.

## Exit criteria

A later reader can understand why an important commit exists and what qualified it without requiring the original live Atlas workflow directory.

---

# M9 — Distribution and operator experience

Distribution remains important, but it is deliberately moved after the semantic/assurance architecture instead of dominating the immediate roadmap.

## M9.1 Qualified runtime distribution

Provide immutable retrievable qualified runtime artifacts with explicit source/version/SHA association.

Initial platform remains Linux x86_64 unless evidence justifies broadening earlier.

## M9.2 Installation

Turn the current manual deployment knowledge into a supported machine-level operation.

A successful install should not require:

```text
manual PYTHONPATH
source-tree archaeology
manual asset copying
hand-built activation scripts
```

## M9.3 Install doctor

Keep project `doctor` and machine installation diagnosis distinct.

Installation diagnosis should cover static identity, a zero-token production probe, and an optional authenticated smoke.

## M9.4 Persistent project → runtime discovery

Normal operation should reconstruct controller/runtime identity without requiring the user to remember ephemeral shell environment.

The current development `aa` function remains useful but is not the final product UX.

## Exit criteria

A fresh supported host can install, diagnose, and activate Atlas through persistent qualified identities without maintainer-only knowledge.

---

# M10 — Policy composition, network, and timeouts

## M10.1 Timeout dimensions

Treat separately:

```text
model timeout
tool timeout
generation timeout
qualification timeout
```

An interruption must not imply that legitimate material output never existed.

## M10.2 Network authority

Current networking restrictions partly rely on Codex/runtime behavior. Atlas should state precisely:

```text
requested network capability
resolved capability
enforcement authority
observed status
```

Do not claim stronger isolation than the actual enforcement boundary provides.

## M10.3 Prompt / policy composition

Clarify and version composition among:

```text
project authority/policy
role/profile contract
generation request
runtime capability
```

Avoid an opaque accumulation of prompt layers.

## Exit criteria

Timeouts and network capabilities have explicit authority/provenance semantics, and prompt/policy composition is inspectable rather than implicit.

---

# M11 — Parallel isolated generations

## Goal

Revisit generation-level parallelism only after the single-workflow assurance model is mature.

The problem is not simply "launch two models". Correct parallelism requires isolation of:

- repository/workspace state;
- Git topology;
- journal ownership;
- caches;
- qualification outputs;
- checkpoint/integration operations.

A likely first architecture is:

```text
one running generation
→ one explicitly isolated repository/workspace
```

rather than two writers sharing one checkout.

Worktree support, explicitly outside the P0.6 sandbox contract, may return here as one possible implementation mechanism, but only as a designed capability with correct Git and sandbox semantics.

## Exit criteria

Two generations can progress concurrently only when Atlas can prove their writable/control domains are isolated and their integration path is explicit.

---

# M12 — Atlas Core orchestration

Reserve the broad "Atlas Core" orchestration milestone for the point at which the lower-level primitives exist and are qualified.

At that stage Atlas should have, in some form:

- durable workflow state;
- qualified capabilities;
- semantic code navigation;
- specialized agents/review levels;
- post-generation assurance;
- semantic traceability;
- tool-level concurrency;
- versionable evidence;
- possibly isolated parallel executions.

Then a more general orchestration model can be built:

```text
goal
↓
decomposition
↓
dependency graph
↓
resource scheduling
↓
agent assignments
↓
deterministic execution
↓
qualification
↓
integration
```

The intended direction is an agent-configured but increasingly non-agentic execution substrate: models decide and parameterize work; deterministic planners/solvers/controllers handle ordering, resources, and mechanical execution where possible.

---

## 13. Development operating model

The development process should scale its review weight to the actual class of change.

| Change class | Default implementation | Default review | Qualification |
| --- | --- | --- | --- |
| Deterministic micro-correction | Luna Medium | none by default | focused + checkpoint |
| Local feature | Luna Medium | Sol Medium when useful | affected |
| Cross-module semantic change | Luna Medium | Sol Medium | affected + full when required |
| Systemic checkpoint / coherence review | — | Astra Low | full |
| Architecture / representation | — | Astra Medium | decision package, not code |

Sol High remains an escalation tool, not a routine mandatory stage.

Astra is scarce and should be used where representation, decomposition, or system-wide coherence is the question rather than for ordinary local correctness checks.

### 13.1 Process metrics

Do not estimate progress primarily as "number of generations remaining".

Track instead:

```text
open proof/product obligations
remaining sequential dependencies
marginal cost of the next cycle
human attention required
```

Routine bounded cycles should remain cheap and predictable. Architecture/refinement cycles may remain substantially more variable.

---

## 14. Current dependency order

The current intended sequence is:

```text
BASELINE 2fd88d5
      │
      ▼
M1  Core Hygiene
      │
      ▼
    Repomix v2
      │
      ▼
M2  Astra Medium architecture
      │
      ├──────────────┐
      ▼              ▼
M3 Semantic Nav    M5 Executor Reliability
      │              │
      └──────┬───────┘
             ▼
M4 Post-generation Assurance
             │
             ▼
M6 Tool Concurrency
             │
             ▼
M7 Semantic Traceability
             │
             ▼
M8 Versionable Evidence
             │
             ▼
M9 Distribution / Install / Doctor
             │
             ▼
M10 Policy / Network / Timeouts
             │
             ▼
M11 Parallel Isolated Generations
             │
             ▼
M12 Atlas Core
```

M2 is explicitly allowed to revise the dependency order. In particular, M3 and M5 may be swapped or partially parallelized if the architecture review concludes that executor interfaces must stabilize before semantic-navigation services are integrated.

---

## 15. Immediate next action

The next implementation milestone is **M1 — Core Hygiene**.

Before beginning M1, this roadmap itself is the new planning authority for sequencing. M1 must remain semantically conservative and should end with the Repomix v2 package required for M2.

No new architectural feature should be pulled into M1 merely because it appears elsewhere in this roadmap.
