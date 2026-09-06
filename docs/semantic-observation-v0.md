# Semantic Observation v0

Status: **design baseline for semantic observation / Agent qualified-tool integration**  
Decision date: **2026-09-06**  
Reconciled with the existing Atlas Core model: **2026-09-06**

This document defines the smallest useful boundary for Atlas to obtain semantic code observations through Atlas Agent.

It is deliberately narrower than a general code-intelligence protocol and narrower than Atlas Core itself.

Atlas already has a semantic model covering identity, descriptions, facts, relations, provenance, snapshots, rules, grounding, decisions, and explanations. Semantic Observation does **not** replace or redefine that model. It supplies structured external observations that Atlas coordination can interpret and, when semantically justified, relate to or admit into Atlas knowledge with explicit provenance.

The governing component rule is:

> **Atlas asks and interprets semantic questions. Atlas Agent qualifies and executes the semantic service. The language service computes the language-specific observation. Persistence as Atlas knowledge is a separate semantic decision.**

---

## 1. Role in the wider Atlas architecture

Semantic Observation is an early product capability for software-oriented coordination.

It exists because repeatedly exploring repositories through whole-file dumps and lexical search wastes model context and loses semantic structure. It should provide targeted observations such as definitions, references, implementations, and diagnostics while keeping the authority boundary explicit.

Conceptually:

```text
Atlas semantic coordination
    ↓ structured request
Atlas Agent
    ↓ qualified service execution
rust-analyzer
    ↓ language-specific result
Atlas Agent
    ↓ bounded observation + provenance
Atlas semantic coordination
    ↓ interpretation in task/product context
Atlas semantic core
    ↓ optional explicit representation of selected durable knowledge/evidence
```

The final arrow is **not automatic**. Most exploratory LSP results may remain observations rather than persistent Atlas facts.

Semantic Observation and migration of the existing Python Atlas Core to Rust may proceed in parallel. Neither should be described as the definition of the other.

---

## 2. First implementation slice

The first real backend is `rust-analyzer` against a representative Rust repository.

Rust is not merely a fixture language:

- the new production Atlas Core implementation is beginning in Rust;
- existing Atlas-managed Rust projects are valid integration subjects;
- Rust semantic tooling is strong enough to pressure-test the boundary early.

The implementation may first prove the Core/Agent message boundary with deterministic fixtures or a fake backend, but completion of the slice requires a qualified real `rust-analyzer` path.

---

## 3. Initial query kinds

Semantic Observation v0 supports only:

```text
definition
references
implementations
diagnostics
search_text
```

`search_text` is an explicit lexical fallback. Its results must never be presented as semantic references.

Deferred beyond v0:

```text
callers / callees
workspace symbol search
document symbol browsing
impact graph
automatic test selection
semantic traceability graph
parallel query execution
Pyright
persistent code-intelligence index
```

A future persistent code-intelligence index must not silently become a second manually maintained semantic source of truth beside the Atlas Knowledge Store.

---

## 4. Request contract

The wire syntax is intentionally not frozen yet. A request must nevertheless carry enough information to identify the operation without relying on shared Python objects.

Minimum conceptual fields:

```text
protocol_version
request_id
query_kind
workspace_ref
query
result_bounds
```

### `protocol_version`

Identifies the observation contract version, not the version of rust-analyzer, Atlas Agent, or the Atlas semantic model.

### `request_id`

Caller-provided operation identity used to correlate the response. It is not semantic authority and is not automatically an Atlas knowledge identity.

### `query_kind`

One of the v0 query kinds.

### `workspace_ref`

Identifies the source workspace/material view against which the observation is requested.

This identity is distinct from an Atlas **Knowledge Store snapshot**. A repository/material snapshot and a semantic-knowledge snapshot may later be related, but they are not the same concept and must not be conflated merely because both use snapshot-like terminology.

For v0, `workspace_ref` may be a controller-validated repository/workspace identity rather than a universal content-addressed material manifest. Do not solve the complete future material-identity problem inside Semantic Observation.

The response must make clear which workspace view was actually used.

### `query`

Language/query-specific input. v0 should use the smallest representation needed by each query kind, such as a source position or exact text pattern.

Do not require Atlas to encode rust-analyzer-specific protocol objects directly.

### `result_bounds`

Explicit limits for consumer/model-facing results, such as maximum records and maximum excerpt bytes.

The full backend response need not be exposed when a bounded normalized observation is sufficient.

---

## 5. Response contract

Every response must distinguish operation status from the returned result set.

Minimum conceptual fields:

```text
protocol_version
request_id
query_kind
workspace_observed
backend
status
results
completeness
truncation
error
```

### Status

v0 must distinguish at least:

```text
OK
UNSUPPORTED
INCOMPLETE
BACKEND_FAILURE
INVALID_REQUEST
```

An empty `OK` result means the backend successfully answered the semantic question and found no matching result.

`UNSUPPORTED` means the capability is not available for the selected backend/configuration. It must never be normalized to an empty `OK` result.

`INCOMPLETE` means Atlas received a useful but known-incomplete observation.

`BACKEND_FAILURE` means the semantic service failed to provide a valid answer.

Exact serialized names may change before implementation, but these distinctions are normative.

### Results

Each result should use a compact normalized source-location representation sufficient for Atlas to request or display the relevant source later.

Conceptually:

```text
path
range
symbol/display label when available
bounded excerpt when useful
relationship/query-specific metadata
```

Do not create a universal language-neutral semantic object model in v0. Atlas already has its own semantic representation; backend normalization should expose useful observations without pretending that language-server protocol objects are Atlas ontology.

### Completeness and truncation

Backend semantic incompleteness and Atlas output truncation are different facts.

A result can be semantically complete but output-truncated, or semantically incomplete without being truncated.

The response must preserve that distinction.

---

## 6. Observation versus Atlas knowledge

A semantic observation is evidence about source state, not automatically an admitted Atlas `Fact`, `Relation`, or other knowledge item.

Three broad dispositions are possible:

```text
ephemeral observation
    used for immediate navigation/reasoning and then discarded

referenced evidence
    retained or referenced because a decision/qualification depends on it

durable Atlas knowledge
    explicitly normalized/admitted under Atlas semantic rules and provenance
```

The admission boundary must preserve the existing Atlas rules for identity, vocabulary, provenance, epistemic status, scope, and historical interpretation.

For example, `rust-analyzer` returning zero references does not by itself establish a timeless Atlas fact that a symbol is unused. It is an observation produced by a particular backend, configuration, and source view.

---

## 7. Backend identity and qualification

Atlas Agent owns backend execution authority.

For a semantic observation, Agent should be able to report enough backend provenance to answer:

```text
which qualified semantic service produced this observation?
against which workspace/configuration?
with which relevant capabilities available?
```

The initial backend identity should include, where applicable:

```text
backend kind
qualified executable identity/version
workspace root or validated workspace identity
relevant launch/configuration identity
capability availability
```

Do not make Atlas responsible for locating arbitrary user-installed language servers.

Do not interpret an executable path alone as sufficient qualification identity.

The exact durable provenance record can reuse or extend Atlas Agent's existing qualified-tool concepts after implementation pressure demonstrates what must be persisted.

---

## 8. Workspace and material identity

Semantic observations are only meaningful relative to source state.

However, this slice must not attempt to define the final universal `MaterialRef` before assurance and candidate-material workflows exist.

For v0, the required invariant is smaller:

> Atlas Agent must be able to state which repository/workspace view the semantic service observed, and Atlas must not silently reuse the observation after that view becomes incompatible or unknown.

At minimum, v0 should support a validated repository/workspace reference plus enough state identity to detect obvious drift during an observation session.

Future material-bound qualification may introduce a stronger exact material identity. Semantic Observation should be able to adopt that identity later without changing the ownership boundary.

Repository/material identity remains distinct from Atlas Knowledge Store snapshot identity even when later links are introduced between them.

---

## 9. Source access and expansion

Semantic Observation is intended to reduce repeated whole-file dumping, not eliminate source reading.

Atlas will still need exact source for:

- function/body behavior;
- ordering and control flow;
- error handling;
- macros and generated constructs;
- configuration and fixtures;
- rationale comments;
- unresolved dynamic behavior.

A bounded observation therefore returns locations and small excerpts, not an obligation to embed entire files.

If expansion/range retrieval is needed, it should remain an explicit later request rather than silently increasing every semantic result.

---

## 10. rust-analyzer lifecycle

The first implementation should prefer correctness and truthful status over clever lifecycle optimization.

Atlas Agent may initially start a qualified rust-analyzer instance for a bounded observation session and terminate it deterministically afterward.

Long-lived server reuse, index caching, incremental cross-snapshot reuse, and parallel query scheduling are optimization questions for later milestones.

If rust-analyzer requires build scripts, procedural macros, compiler access, or writable caches to provide a requested capability, Agent must expose that requirement truthfully through its qualified capability model. A query that is logically read-only with respect to source may still require controlled execution resources internally.

Disabling such capabilities must not silently produce an apparently complete answer when coverage is actually reduced.

---

## 11. Error and authority boundary

Atlas may request an observation. It does not authorize itself to launch tools or enlarge capabilities.

Atlas Agent may reject a request because:

```text
request invalid
workspace unavailable or incompatible
backend unavailable/unqualified
required capability not granted
backend failed
result could not be normalized safely
```

These are operation outcomes, not product-semantic conclusions.

Atlas decides how the observation affects task reasoning and whether any selected content becomes durable semantic knowledge.

---

## 12. Initial transport

The first Rust/Python implementation may use a process/CLI boundary with structured JSON.

Requirements:

- versioned request and response envelope;
- one unambiguous machine-readable response per request;
- stdout/stderr behavior that does not corrupt the structured response;
- stable error/status distinctions;
- no dependency on importing Python internals from Rust;
- no requirement for a general RPC framework.

A later daemon or richer transport may replace the process boundary without changing the semantic ownership model.

Do not create a separate `atlas-protocol` repository for v0.

---

## 13. First implementation exit criteria

Semantic Observation v0 is complete when, against a representative Rust project:

1. the Rust Atlas implementation can issue each implemented v0 request through the explicit Atlas/Agent boundary;
2. Atlas Agent selects and executes a qualified rust-analyzer backend rather than an arbitrary user-state binary;
3. `definition`, `references`, and `implementations` return bounded normalized source locations where supported;
4. `diagnostics` returns bounded normalized diagnostics with backend identity;
5. `search_text` remains explicitly lexical and distinguishable from semantic results;
6. unsupported, empty, incomplete, backend-failure, and truncated outcomes cannot be silently confused;
7. observations identify the workspace/source view actually observed strongly enough to detect incompatible reuse;
8. observations are not automatically persisted as Atlas semantic facts;
9. no new persistent code-intelligence database, impact engine, parallel scheduler, Pyright integration, or generalized RPC framework is introduced.

The implementation should use the smallest deterministic test corpus necessary to prove the boundary, then exercise it on at least one real Rust repository.

---

## 14. Questions intentionally left open until implementation

The following should be refined from the first vertical slice rather than decided speculatively:

- exact JSON field names and schema layout;
- whether source positions or symbol handles are the most useful primary request form;
- exact backend launch/session lifetime;
- how much normalized rust-analyzer capability metadata must be durable;
- the smallest useful workspace drift identity before full `MaterialRef` exists;
- output record and excerpt limits;
- whether range/source expansion belongs in this protocol or in a generic repository-observation service;
- which rust-analyzer operations should be added immediately after v0;
- which observations, if any, deserve direct adapters into durable Atlas knowledge rather than remaining evidence or working state.

These open questions do not weaken the component boundary. They deliberately avoid freezing implementation details before real consumers exist.
