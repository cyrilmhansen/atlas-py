# Atlas architecture boundaries

Status: **current architectural direction, reconciled with the existing Atlas Core model**  
Decision date: **2026-09-06**

This document defines the boundary between Atlas, Atlas Agent, and specialized execution services for the next development phase.

It does **not** redefine Atlas Core as a semantic coordinator. The repository already defines Atlas as an experimental **semantic computational knowledge system**, and Core V1 already gives Atlas Core concrete semantic responsibilities: identities and descriptions, facts and relations, snapshots and provenance, structured rules and grounding, finite decision/selection, and explanations reconstructed from effective dependencies.

The new coordination work extends that product model. It does not replace it.

The governing distinction is:

> **Atlas owns semantic representation, interpretation, decision, and coordination. Atlas Agent guarantees how an authorized operation is executed, isolated, recorded, qualified, and materialized.**

---

## 1. System shape

```text
                              ATLAS
                semantic computational knowledge system

          ┌───────────────────────────────────────────┐
          │ Atlas semantic core                       │
          │                                           │
          │ identity / descriptions / values          │
          │ facts / relations / provenance            │
          │ snapshots / rules / grounding             │
          │ decision / selection / explanation        │
          └───────────────────────────────────────────┘
                              │
                              │ supports
                              ▼
          ┌───────────────────────────────────────────┐
          │ semantic coordination capabilities         │
          │                                           │
          │ goals / decisions / representation of work│
          │ decomposition / dependencies / obligations│
          │ code understanding / impact / traceability│
          │ assurance planning / orchestration        │
          └───────────────────────────────────────────┘
                              │
                              │ commands + observations
                              ▼
                         ATLAS AGENT
                 deterministic execution subsystem

          admission / ownership / capabilities / sandbox
          model and qualified-tool execution
          transactional journal / recovery
          qualification execution
          Git materialization / checkpoint
          operation and artifact provenance
                              │
                              ▼
                    SPECIALIZED SERVICES / TOOLS

          Codex / other models / rust-analyzer / Pyright
          Git / compilers / test runners / linters / others
```

Atlas Agent is a subsystem used by Atlas and by other software projects. It is not the semantic core of Atlas.

---

## 2. Atlas semantic core responsibilities

The semantic core retains the responsibilities already established by the Atlas specification and Core V1 profile.

These include, at the current implementation level:

- nominal semantic identities that are distinct from content equality;
- descriptions, values, facts, relations, vocabulary, scopes, and provenance;
- explicit epistemic states, including the open-world distinction among `TRUE`, `FALSE`, and `UNKNOWN`;
- multivalued relations and explicit ordering where order is semantic;
- validated persistent knowledge with immutable snapshots;
- supersession and historical/stale interpretation relative to snapshots;
- structured rules and grounding;
- finite decision problems and exact selection for the supported Core V1 profile;
- derivation dependencies and explanations reconstructed from the dependencies actually used.

The semantic core is therefore more fundamental than software code navigation. Language-server observations are one possible source of structured evidence for Atlas; they are not a replacement for Atlas's semantic model.

---

## 3. Semantic coordination responsibilities

Atlas is also gaining product-level coordination capabilities built on and around the semantic core.

These include:

- the current objective and bounded completion criteria;
- accepted product decisions and unresolved product questions;
- representation of work and decomposition into obligations or tasks;
- dependency and resource reasoning;
- semantic understanding of software and project structure;
- interpretation of code-navigation observations;
- impact reasoning;
- selection of specialized agents and strategies;
- deciding what evidence is needed before work can be considered complete;
- semantic traceability and progressive explanation / semantic zoom;
- higher-level orchestration, including non-agentic scheduling when appropriate.

This coordination state should reuse Atlas semantic concepts where they genuinely fit, but it must not force every operational observation into the persistent Knowledge Store merely because Atlas can represent knowledge.

Observations may remain ephemeral, become referenced evidence, or be admitted as durable Atlas knowledge according to an explicit semantic and provenance decision.

Atlas should not maintain a manually duplicated prose model of every source file or symbol. Structural knowledge should be derived from source, compilers, language services, Git, tests, and explicit product decisions wherever possible.

---

## 4. Atlas Agent responsibilities

Atlas Agent owns deterministic execution and materialization concerns, including:

- prompt/request admission;
- operation ownership;
- capability and policy resolution;
- sandbox and runtime selection;
- model execution;
- qualified tool execution;
- transactional workflow journal;
- historical replay/rebuild of its own durable records;
- recovery of explicitly supported incomplete transactions;
- qualification recipe execution;
- Git materialization and checkpoint transitions;
- runtime, tool, execution, and artifact provenance;
- truthful requested / resolved / observed runtime facts where applicable.

Atlas Agent does **not** own the semantic meaning of the project being changed. It may expose qualified semantic services to Atlas, but Atlas interprets their observations in the context of its semantic model, current goals, decisions, and obligations.

The existing V1 rule remains:

```text
one controlled repository/workflow
→ at most one RUNNING generation
```

Tool-level concurrency and future isolated generation-level concurrency are separate architectural questions.

---

## 5. Specialized services and tools

Specialized tools supply computations or observations under explicit execution authority.

Examples include:

- `rust-analyzer`;
- Pyright;
- compilers;
- test runners;
- linters;
- Git;
- Codex and other model runtimes.

A tool may know more than Atlas Agent about a language or build system. Atlas Agent should not reimplement that knowledge. Conversely, a tool does not gain authority over Atlas lifecycle or product decisions merely because Atlas Agent launches it.

---

## 6. Semantic observation example

A semantic navigation request should cross the component boundary approximately as follows:

```text
Atlas coordination
  asks: references(Foo::bar)

Atlas Agent
  resolves an authorized qualified semantic service
  verifies backend/workspace/runtime identity
  executes the request with bounded resources
  returns bounded observation + provenance + completeness status

rust-analyzer
  computes the language-specific observation

Atlas coordination
  interprets the result in the context of the current goal,
  semantic model, affected invariants, obligations, and next action

Atlas semantic core
  may receive selected durable facts/evidence only when Atlas
  explicitly chooses to represent them as knowledge
```

This distinction is important:

- the language server owns language-specific analysis;
- Atlas Agent owns qualified execution of that service;
- Atlas owns the semantic use of the resulting observation;
- persistence into Atlas knowledge is an explicit semantic act, not an automatic side effect of an LSP response.

A missing language-server capability must be distinguishable from an empty semantic answer.

---

## 7. Qualification example

Post-generation assurance is also split across the boundary.

Atlas may decide:

```text
this material affects subsystem X
→ obligations A and B remain open
→ focused + integration qualification is required
```

Atlas Agent then executes only authorized qualification operations:

```text
recipe R
against material M
in environment E
→ observed result
→ evidence/provenance
```

Atlas interprets whether the evidence satisfies the semantic obligation, subject to operator policy. Atlas Agent records and materializes the authorized durable transition.

Passing tests are evidence, not proof of product correctness. A Git checkpoint is a neutral material snapshot, not a success certificate.

---

## 8. Implementation-language and migration direction

The current implementation strategy is intentionally asymmetric.

### 8.1 Existing Python Atlas Core

The existing Python Core V1 implementation, specification, profile, tests, and persisted examples are not discarded by the creation of a Rust repository.

They should be treated as:

```text
prototype / reference implementation
+ executable semantic oracle where appropriate
+ conformance evidence
+ historical design record
```

The specification and profile remain the semantic authority above language-specific implementation details.

### 8.2 New Rust Atlas Core

New production Atlas Core development should begin in **Rust** rather than growing a second large production generation in Python with an assumed future translation.

Working repository/component name:

```text
atlas-core
```

The repository is the intended production home for the Rust implementation of the existing Atlas semantic core and for new product capabilities built around it. The repository name does not redefine Atlas Core as code navigation or coordination alone.

Migration should be behavior-by-behavior and contract-by-contract:

```text
existing semantic contract
        ↓
reference Python behavior / fixtures / tests
        ↓
Rust implementation
        ↓
conformance comparison
```

Do not translate Python files mechanically. Rust types, ownership, errors, and resource models should express the semantic invariants directly.

### 8.3 Atlas Agent

The existing Atlas Agent implementation remains in **Python for now**.

Current repository name:

```text
atlas-py
```

Likely future repository name:

```text
atlas-agent
```

Do not rename the repository merely for cosmetic consistency. Rename when the Core/Agent boundary is concrete enough that the change improves clarity rather than creating migration noise.

Do not rewrite Atlas Agent in Rust before beginning the Rust Core. If Agent is later migrated, prefer incremental replacement behind explicit contracts, using its tests, journals, fixtures, error codes, and state transitions as conformance evidence.

---

## 9. Core/Agent interface direction

The Rust Atlas implementation must not depend on importing Atlas Agent's internal Python objects.

The boundary should become explicit and versioned. Initially, a process/CLI boundary with structured JSON is acceptable if it provides the required semantics.

Conceptual messages include:

```text
request
resolved operation
observation
execution outcome
error
artifact reference
```

This is a boundary requirement, not a decision to create a general RPC framework.

Do not create a separate `atlas-protocol` repository until multiple real consumers demonstrate that an independently versioned protocol package is useful.

---

## 10. Semantic navigation as an Atlas capability

Semantic Code Navigation is primarily an **Atlas product capability**, implemented using qualified services supplied through Atlas Agent.

Its purpose is broader than post-generation test selection. It changes how Atlas understands and explores software:

```text
where is this symbol defined?
who references it?
what implements this trait/interface?
what diagnostics apply?
what declarations changed?
what code should be inspected next?
```

It should therefore not be delayed until every remaining Atlas Agent reliability or assurance feature is complete.

At the same time, it is not the semantic foundation of Atlas. The existing Atlas model already defines semantic identity, knowledge, provenance, rules, decisions, and explanation independently of programming-language analysis.

A Rust-oriented semantic observation path is an appropriate early integration test of the new Rust implementation and the Core/Agent boundary while semantic-core migration proceeds in parallel.

---

## 11. Current non-goals

Do not treat this architectural clarification as authorization for:

- renaming the current repository immediately;
- rewriting Atlas Agent in Rust immediately;
- discarding or mechanically translating the existing Python Core V1 implementation;
- moving all existing Python tests to Rust at once;
- treating LSP observations as automatically admitted Atlas facts;
- introducing a standalone protocol repository;
- building a new graph database;
- building a second persistent code-intelligence database that duplicates the Atlas Knowledge Store;
- implementing a universal language-neutral semantic database;
- implementing parallel generation mutation in one checkout;
- folding semantic coordination into `Workflow.execute()` or any equivalent Atlas Agent execution function;
- expanding Atlas Agent until it becomes Atlas.

---

## 12. Development rule

When deciding where a new responsibility belongs, ask:

1. **Does this define semantic identity, knowledge, rules, decision, explanation, or what the project means?**  
   Prefer the Atlas semantic core.

2. **Does this decide what should happen next, what evidence is sufficient, or how semantic observations affect the task?**  
   Prefer Atlas coordination.

3. **Does this authorize, execute, isolate, record, qualify, or materialize an operation?**  
   Prefer Atlas Agent.

4. **Does an existing specialized tool already implement the domain computation?**  
   Use that tool through an explicit qualified boundary rather than rebuilding it in either layer.

This boundary should be refined from real usage. It is deliberately smaller than a complete final architecture.
