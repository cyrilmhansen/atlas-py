# Atlas

Atlas is an experimental **semantic computational knowledge system**.

Its purpose is to represent, qualify, discover, select, compose, and eventually
execute reusable computational components from explicit semantic evidence
rather than from implementation names or backend-specific conventions.

Atlas is deliberately split into two concerns:

- **Atlas Core** — the semantic model and computational knowledge system;
- **Atlas Agent** — development and assurance infrastructure used to build and
  validate Atlas and other software projects with qualified AI agents.

Atlas Agent is not the semantic core of Atlas and should eventually become
boring infrastructure that fades into the background.

## Current development state

### Atlas Core

The current Core V1 work focuses on semantic identity, descriptions and facts,
semantic relations, alternative realizations, applicability and qualification,
resource dependencies and sharing, specialization, provenance, and evidence.

The next major Core phase will increasingly use real external computational
corpora to pressure-test the semantic model.

See:

- [`docs/core-v1-profile.md`](docs/core-v1-profile.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`knowledge.md`](knowledge.md)

### Atlas Agent

Atlas Agent v0.1.1 established a qualified Linux/Bubblewrap execution path
through the Atlas Codex runtime.

The v0.1.2 hardening tranche is driven by sustained real-project use and has
already completed:

- manual checkpoint correctness;
- immutable Codex config / mutable runtime-state isolation;
- safe automatic reuse fallback;
- per-dispatch Fast service tier;
- durable cancellation of unstarted accepted generations;
- truthful writable scratch semantics.

The next P0 item is **qualified development toolchains and caches**.

The roadmap also tracks installation, reboot-safe activation,
controller/runtime identity, profile-driven timeouts, project prompt
composition, and the stopping rule for returning primary effort to Atlas Core.

See:

- [`docs/roadmap.md`](docs/roadmap.md)
- [`docs/agent-workflow.md`](docs/agent-workflow.md)
- [`docs/security-policy.md`](docs/security-policy.md)
- [`docs/deploy-existing-project.md`](docs/deploy-existing-project.md)
- [`docs/atlas-release-process.md`](docs/atlas-release-process.md)

## Development principles

A few boundaries are intentional:

- semantic meaning must remain independent of execution backend;
- qualified immutable inputs must not mutate themselves;
- runtime identity is explicit and verifiable;
- project workflow history is durable authority, not disposable scratch state;
- active workflows should remain bound to a compatible controller until an
  explicit migration boundary;
- normal operation after a reboot should be reconstructible from persistent
  project/runtime metadata rather than remembered shell variables;
- new Atlas Agent sophistication must be justified by concrete repeated
  development friction.

## Status

This repository is experimental and under active development.

The authoritative prioritization and current implementation boundary are in
[`docs/roadmap.md`](docs/roadmap.md).

## License

Atlas is licensed under the
[PolyForm Noncommercial License 1.0.0](LICENSE).

Noncommercial use, modification, and redistribution are permitted under the
terms of that license. Commercial use requires a separate license from the
copyright holder.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
