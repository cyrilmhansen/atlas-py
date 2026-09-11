# Qualified specialized-service workflow

This reusable qualification pattern for bounded services used by Atlas Agent
complements, and does not replace, the [release
process](atlas-release-process.md) or [existing-project
deployment](deploy-existing-project.md). Release engineering,
machine/project deployment, qualified service integration, and Atlas semantic
observation/admission remain distinct procedures.

## Gate sequence

```text
define bounded service contract
    → pin immutable service/runtime identity
    → define deterministic, side-effect-free qualification probe
    → bind command/runtime identity in machine capabilities
    → CapabilityResolver qualification
    → focused integration implementation
    → independent review
    → real-host execution witness
    → diagnose concrete integration failures without weakening authority
    → requalify changed service bytes when necessary
    → repeat the real witness
    → checkpoint only after review and the required real witness
```

A successful qualification probe is not a successful service operation. A
successful process is not a validated result. Keep source commit, command
bytes, helper/runtime bytes, and observed probe as distinct identities/evidence
where applicable.

Failed real-host gates stop checkpoint or publication. Do not weaken sandbox
authority to make a witness pass. If service bytes change, regenerate or
recheck qualification evidence before relying on it. Environment-caused skips
must be recorded as skips, not presented as real-host witnesses.

Retain execution material—logs, snapshots, artifacts, identities, and
lifecycle evidence—separately from Atlas semantic admission. Prepared service
material is not automatically an Atlas observation. This workflow learned from
PVC and is generic enough for future rust-analyzer- or Pyright-style services
without inventing a universal provider or RPC architecture.
