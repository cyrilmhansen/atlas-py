# Semantic Observation v0

Status: **design baseline for C1 / A2.1**  
Decision date: **2026-09-06**

This document defines the smallest useful boundary for Atlas Core to obtain semantic code observations through Atlas Agent.

It is deliberately narrower than a general code-intelligence protocol. Its purpose is to let the first Rust Atlas Core capability consume qualified semantic observations without importing Atlas Agent's Python internals and without turning Atlas Agent into the semantic coordinator.

The governing component rule remains:

> **Atlas Core asks and interprets semantic questions. Atlas Agent qualifies and executes the semantic service. The language service computes the language-specific observation.**

---

## 1. First vertical slice

The first implementation slice is:

```text
Atlas Core (Rust)
    ↓ structured request
Atlas Agent (Python)
    ↓ qualified service execution
rust-analyzer
    ↓ language-specific result
Atlas Agent
    ↓ bounded observation + provenance
Atlas Core
    ↓ interpretation in task/product context
```

The first real subject should be a representative Rust repository. Rust is not merely a fixture language: Atlas Core itself is intended to begin in Rust, and existing Atlas-managed Rust projects are valid integration targets.

---

## 2. Initial query kinds

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
persistent semantic index
```

These may be added after the first vertical slice demonstrates the right boundary.

---

## 3. Request contract

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

Identifies the observation contract version, not the version of rust-analyzer or Atlas Agent.

### `request_id`

Caller-provided operation identity used to correlate the response. It is not semantic authority.

### `query_kind`

One of the v0 query kinds.

### `workspace_ref`

Identifies the source workspace/material view against which the observation is requested.

For v0, this may be a controller-validated repository/workspace identity rather than a universal content-addressed material manifest. Do not solve the complete future material-identity problem inside C1.

The response must make clear which workspace view was actually used.

### `query`

Language/query-specific input. v0 should use the smallest representation needed by each query kind, such as a source position or exact text pattern.

Do not require Atlas Core to encode rust-analyzer-specific protocol objects directly.

### `result_bounds`

Explicit limits for model-facing/consumer-facing results, such as maximum records and maximum excerpt bytes.

The full backend response need not be exposed when a bounded normalized observation is sufficient.

---

## 4. Response contract

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

Each result should use a compact normalized source-location representation sufficient for Atlas Core to request or display the relevant source later.

Conceptually:

```text
path
range
symbol/display label when available
bounded excerpt when useful
relationship/query-specific metadata
```

Do not create a universal language-neutral semantic object model in v0.

### Completeness and truncation

Backend semantic incompleteness and Atlas output truncation are different facts.

A result can be semantically complete but output-truncated, or semantically incomplete without being truncated.

The response must preserve that distinction.

---

## 5. Backend identity and qualification

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

Do not make Atlas Core responsible for locating arbitrary user-installed language servers.

Do not interpret an executable path alone as sufficient qualification identity.

The exact durable provenance record can reuse or extend Atlas Agent's existing qualified-tool concepts after implementation pressure demonstrates what must be persisted.

---

## 6. Workspace and material identity

Semantic observations are only meaningful relative to source state.

However, C1 must not attempt to define the final universal `MaterialRef` before assurance and candidate-material workflows exist.

For v0, the required invariant is smaller:

> The controller must be able to state which repository/workspace view the semantic service observed, and Atlas Core must not silently reuse the observation after that view becomes incompatible or unknown.

At minimum, v0 should support a validated repository/workspace reference plus enough state identity to detect obvious drift during an observation session.

Future material-bound qualification may introduce a stronger exact material identity. Semantic Observation should be able to adopt that identity later without changing the ownership boundary.

---

## 7. Source access and expansion

Semantic Observation is intended to reduce repeated whole-file dumping, not eliminate source reading.

Atlas Core will still need exact source for:

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

## 8. rust-analyzer lifecycle

The first implementation should prefer correctness and truthful status over clever lifecycle optimization.

Atlas Agent may initially start a qualified rust-analyzer instance for a bounded observation session and terminate it deterministically afterward.

Long-lived server reuse, index caching, incremental cross-snapshot reuse, and parallel query scheduling are optimization questions for later milestones.

If rust-analyzer requires build scripts, procedural macros, compiler access, or writable caches to provide a requested capability, Agent must expose that requirement truthfully through its qualified capability model. A query that is logically read-only with respect to source may still require controlled execution resources internally.

Disabling such capabilities must not silently produce an apparently complete answer when coverage is actually reduced.

---

## 9. Error and authority boundary

Atlas Core may request an observation. It does not authorize itself to launch tools or enlarge capabilities.

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

Atlas Core decides how the observation affects task reasoning. For example, zero references may be evidence that a symbol appears unused, but Agent must not turn that observation into a product decision or deletion authorization.

---

## 10. Initial transport

The first Core/Agent implementation may use a process/CLI boundary with structured JSON.

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

## 11. First implementation exit criteria

C1 / A2.1 v0 is complete when, against a representative Rust project:

1. Atlas Core can issue each implemented v0 request through the explicit Core/Agent boundary.
2. Atlas Agent selects and executes a qualified rust-analyzer backend rather than an arbitrary user-state binary.
3. `definition`, `references`, and `implementations` return bounded normalized source locations where supported.
4. `diagnostics` returns bounded normalized diagnostics with backend identity.
5. `search_text` remains explicitly lexical and distinguishable from semantic results.
6. unsupported, empty, incomplete, backend-failure, and truncated outcomes cannot be silently confused.
7. observations identify the workspace/source view actually observed strongly enough to detect incompatible reuse.
8. no persistent semantic database, impact engine, parallel scheduler, Pyright integration, or generalized RPC framework is introduced.

The implementation should use the smallest test corpus necessary to prove the boundary, then exercise it on at least one real Rust repository.

---

## 12. Questions intentionally left open until implementation

The following should be refined from the first vertical slice rather than decided speculatively:

- exact JSON field names and schema layout;
- whether source positions or symbol handles are the most useful primary request form;
- exact backend launch/session lifetime;
- how much normalized rust-analyzer capability metadata must be durable;
- the smallest useful workspace drift identity before full `MaterialRef` exists;
- output record and excerpt limits;
- whether range/source expansion belongs in this protocol or in a generic repository-observation service;
- which rust-analyzer operations should be added immediately after v0.

These open questions do not weaken the component boundary. They deliberately avoid freezing implementation details before the first real consumer exists.
