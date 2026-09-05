# Atlas architecture boundaries

Status: **current architectural direction**  
Decision date: **2026-09-06**

This document defines the product boundary that should guide the next phase of Atlas development.

The key distinction is simple:

> **Atlas decides what must be understood or accomplished. Atlas Agent guarantees how an authorized operation is executed, recorded, and materialized.**

The two are related, but they are not the same component.

---

## 1. System shape

```text
                         ATLAS
              semantic coordination system

   goals / decisions / representation of work
   decomposition / dependencies / obligations
   code understanding / impact / traceability
   agent selection / assurance planning

                          │
                          │ commands + observations
                          ▼

                     ATLAS AGENT
             deterministic execution subsystem

   admission / ownership / capabilities / sandbox
   model and tool execution
   transactional journal / recovery
   qualification execution
   Git materialization / checkpoint
   operation and artifact provenance

                          │
                          ▼

                SPECIALIZED SERVICES / TOOLS

   Codex / other models
   rust-analyzer / Pyright
   Git
   compilers
   test runners
   linters
   other qualified tools
```

Atlas is the product-level coordination system. Atlas Agent is one subsystem used by Atlas to perform controlled operations against repositories, tools, models, and host resources.

---

## 2. Atlas responsibilities

Atlas owns product-level and semantic coordination concerns, including:

- the current objective;
- accepted product decisions and unresolved product questions;
- representation of work and decomposition into obligations or tasks;
- dependency and resource reasoning;
- semantic understanding of code and project structure;
- interpretation of code-navigation observations;
- impact reasoning;
- selection of specialized agents and strategies;
- deciding what evidence is needed before work can be considered complete;
- semantic traceability and progressive explanation/semantic zoom;
- higher-level orchestration, including non-agentic scheduling when appropriate.

Atlas may ask models and tools for observations or proposals. Those observations do not become authority merely because a model or language server produced them.

Atlas should not maintain a manually duplicated prose model of every source file or symbol. Structural knowledge should be derived from source, compilers, language services, Git, tests, and explicit product decisions wherever possible.

---

## 3. Atlas Agent responsibilities

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

Atlas Agent does **not** own the semantic meaning of the project being changed. It may expose qualified semantic services to Atlas, but Atlas interprets their observations in the context of product goals and obligations.

The existing V1 rule remains:

```text
one controlled repository/workflow
→ at most one RUNNING generation
```

Tool-level concurrency and future isolated generation-level concurrency are separate architectural questions.

---

## 4. Specialized services and tools

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

## 5. Semantic observation example

A semantic navigation request should cross the component boundary approximately as follows:

```text
Atlas
  asks: references(Foo::bar)

Atlas Agent
  resolves an authorized qualified semantic service
  verifies backend/workspace/runtime identity
  executes the request with bounded resources
  returns bounded observation + provenance + completeness status

rust-analyzer
  computes the semantic observation

Atlas
  interprets the result in the context of the current goal,
  affected invariants, obligations, and proposed next action
```

This distinction is important:

- the language server owns language-specific analysis;
- Atlas Agent owns qualified execution of that service;
- Atlas owns the semantic use of the resulting observation.

A missing language-server capability must be distinguishable from an empty semantic answer.

---

## 6. Qualification example

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

Passing tests are evidence, not a proof of product correctness. A Git checkpoint is a neutral material snapshot, not a success certificate.

---

## 7. Implementation-language direction

The current implementation strategy is intentionally asymmetric.

### Atlas Core

The new Atlas Core should begin in **Rust** rather than creating a large new production subsystem in Python with the expectation of translating it later.

Working repository/component name:

```text
atlas-core
```

The name is descriptive and provisional. The architectural role matters more than freezing a final product name today.

### Atlas Agent

The existing Atlas Agent implementation remains in **Python for now**.

Current repository name:

```text
atlas-py
```

Likely future repository name:

```text
atlas-agent
```

The repository should not be renamed merely to satisfy this document. Rename when the Core/Agent boundary is concrete enough that the change improves clarity rather than creating migration noise.

### No big-bang rewrite

Do not rewrite Atlas Agent in Rust before beginning Atlas Core.

The existing Python implementation already contains substantial transactional behavior and a large regression suite. If Atlas Agent is later migrated, prefer incremental replacement behind explicit contracts rather than a monolithic port.

The existing tests and historical fixtures should become conformance evidence for any future Rust implementation.

---

## 8. Core/Agent interface direction

Atlas Core must not depend on importing Atlas Agent's internal Python objects.

The boundary should become explicit and versioned. Initially, a simple process/CLI boundary with structured JSON is acceptable if it provides the required semantics.

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

## 9. Semantic navigation as a product capability

Semantic Code Navigation is primarily an **Atlas capability**, implemented using qualified services supplied through Atlas Agent.

Its purpose is broader than post-generation test selection. It changes how Atlas understands and explores software:

```text
where is this symbol defined?
who references it?
what implements this trait/interface?
what diagnostics apply?
what declarations changed?
what code should be inspected next?
```

For this reason, semantic observation should not be delayed until every remaining Atlas Agent reliability or assurance feature is complete.

A minimal Rust-oriented semantic observation path is an appropriate first implementation test of the new Atlas/Agent boundary.

---

## 10. Current non-goals

Do not treat this architectural clarification as authorization for:

- renaming the current repository immediately;
- rewriting Atlas Agent in Rust immediately;
- moving all existing Python tests to Rust;
- introducing a standalone protocol repository;
- building a graph database;
- implementing a universal language-neutral semantic database;
- implementing parallel generation mutation in one checkout;
- folding the semantic coordinator into `Workflow.execute()` or any equivalent Atlas Agent execution function;
- expanding Atlas Agent until it becomes Atlas.

---

## 11. Development rule

When deciding where a new responsibility belongs, ask:

1. **Does this decide what the project means, what should happen, or what evidence is sufficient?**  
   Prefer Atlas.

2. **Does this authorize, execute, isolate, record, qualify, or materialize an operation?**  
   Prefer Atlas Agent.

3. **Does an existing specialized tool already implement the domain computation?**  
   Use that tool through an explicit qualified boundary rather than rebuilding it in either layer.

This boundary should be refined from real usage. It is deliberately smaller than a complete final architecture.
