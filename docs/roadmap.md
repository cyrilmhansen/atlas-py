# Atlas / Atlas Agent — Roadmap

Document version: **0.2**

This roadmap reflects the state reached after the Atlas Agent v0.1.1 release
and the deployment/release qualification work performed around it.

It is intentionally a prioritization document, not a complete inventory of
possible Atlas features.

The central rule is:

> Atlas Agent exists to make Atlas development reliable. Once Atlas Agent is
> installable, diagnosable, and proven on an external project, further Agent
> sophistication must not displace work on Atlas itself without concrete
> evidence that the infrastructure is blocking progress.

The immediate objective is therefore to finish a minimal, boring, reusable
Linux installation surface for Atlas Agent, validate it outside the Atlas
repository, then return development priority to the Atlas Semantic Core.

---

## 1. Scope and planning horizon

Current primary platform:

```text
OS:                 Linux
shell:              bash
architecture:       x86_64
sandbox backend:    Bubblewrap
model controller:   qualified Atlas Codex fork
```

Other operating systems and architectures remain legitimate future targets,
but they are not allowed to delay the current Linux deployment path.

This roadmap distinguishes four horizons:

```text
NOW
    finish the minimum machine-installation product

NEXT
    validate that product on Memoria and fix generic friction

THEN
    return priority to Atlas Core and external semantic use cases

LATER
    automation, portability, broader hardening, and optional ergonomics
```

---

## 2. Current baseline

Atlas Agent v0.1.1 established a significantly stronger baseline than v0.1.0.

The release qualified:

- an exact Atlas Agent source release;
- a machine-readable release manifest;
- a pinned Atlas Codex source release;
- an exact native Codex executable identity by SHA-256;
- versioned canonical Codex assets;
- versioned compact prompts;
- atomic CODEX_HOME provisioning;
- runtime identity checks before execution;
- a sealed executable authority;
- a stable runtime path compatible with Codex `current_exe()` helper dispatch;
- Bubblewrap execution through the real Codex exec-server;
- zero-token live helper execution;
- an authenticated Luna smoke;
- a release procedure based on explicit gates;
- a user deployment guide separating machine installation from project state.

This means the main remaining problem is no longer "can Atlas Agent execute a
qualified model safely enough for development?"

The immediate problem is now:

```text
can a user install and diagnose the already-qualified system
without reconstructing release-engineering knowledge by hand?
```

---

## 3. Planning principles learned from v0.1.1

### 3.1 Separate identities

The following are independent release/deployment dimensions:

```text
Atlas Agent source release
Atlas Agent commit
Atlas Codex source release
Atlas Codex commit
Codex native executable bytes
Codex executable SHA-256
canonical Codex assets
prompt set
project policy
user authentication
project workflow journal
Git publication/tag state
```

A roadmap item should say which identity it changes.

Changing one dimension must not silently imply changing another.

### 3.2 A new Agent release does not imply a new Codex release

If the Codex source and qualified binary are unchanged, reuse the exact
existing Codex release.

Do not manufacture a new Codex tag merely because Atlas Agent has a new tag.

### 3.3 Exact executable bytes are runtime authority

A pathname is a locator.

The executable SHA-256 is the runtime identity.

Therefore the same already-qualified native binary can legitimately be shared
between multiple independent Atlas Agent installations on the same machine.

### 3.4 Canonical assets and authentication are different classes of state

Canonical assets are versioned and immutable for a release.

Authentication is mutable user state.

The Atlas CODEX_HOME may reference user authentication after canonical asset
provisioning without making the secret part of the canonical asset set.

### 3.5 Project state is not machine-installation state

Machine state includes:

```text
Agent release checkout
qualified Codex executable
canonical CODEX_HOME
user auth reference
Bubblewrap/runtime prerequisites
```

Project state includes:

```text
atlas-agent-policy.toml
.git/atlas-agent journal and spool
repository witness
prompts
execution reports
checkpoint history
```

The two lifecycles must remain separate.

### 3.6 `doctor` and installation diagnosis are different responsibilities

`atlas-agent doctor` validates a project workflow.

It is not proof that the machine installation is complete.

A separate `install-doctor` is required.

### 3.7 Release qualification and user deployment are different workflows

Release qualification may use maintainers' test suites, source checkouts,
manual SHA checks, and explicit publication gates.

Normal users should not need to reproduce those steps.

The installer should consume release artifacts produced by that process.

### 3.8 Use external projects to reveal missing product surfaces

Atlas Agent developed inside Atlas can accidentally depend on prepared state
that is invisible to its maintainers.

A second project is therefore a product test, not merely another functional
smoke.

### 3.9 Do not let Atlas Agent become the product

After the minimum installation and external-project validation are complete,
Atlas Agent should move toward maintenance mode.

New Agent features require evidence of a recurring problem.

---

# NOW — finish the minimum installable Atlas Agent

## P0.1 — Publish or define distribution of the qualified Codex runtime

**Priority: critical**

The deployment guide exposed the largest remaining gap on a virgin machine:
the release manifest can identify the required native Codex executable, but an
ordinary user still needs a reliable way to obtain the exact qualified bytes.

A local rebuild is not equivalent to the qualified binary.

Even from the same source commit, rebuilt bytes may differ.

### Required outcome

For each supported production target, an Atlas Agent release must identify a
retrievable binary artifact whose SHA-256 is the value in `atlas-release.toml`.

Initial target:

```text
x86_64-unknown-linux-gnu
```

### Preferred properties

- immutable published artifact;
- deterministic association with the recorded Codex source tag and commit;
- SHA-256 recorded in Atlas release metadata;
- download path usable by `atlas-agent install`;
- no dependency on a maintainer's development checkout;
- no automatic trust based solely on filename or tag.

### Explicit non-goal

Do not make reproducible Codex builds a prerequisite for the first installer.

Reproducible builds may be valuable later, but distribution of already
qualified bytes solves the current deployment problem directly.

### Exit criterion

A fresh Linux machine can obtain the exact native Codex binary required by one
published Atlas Agent release and verify its digest without access to the Atlas
or Codex development working directories.

---

## P0.2 — Implement `atlas-agent install`

**Priority: critical**

This command turns the manual Linux/bash bootstrap in
`docs/deploy-existing-project.md` into a supported machine-level operation.

### Responsibilities

`atlas-agent install` should, for a selected Atlas Agent release:

- resolve the Atlas Agent release identity;
- read `atlas-release.toml`;
- select a supported local target;
- obtain or locate the exact qualified Codex executable;
- verify the executable SHA-256;
- install a stable Atlas Agent command;
- provision the canonical CODEX_HOME atomically;
- verify asset and prompt identities;
- establish the mutable authentication reference without copying secrets;
- verify basic host prerequisites;
- leave project repositories untouched.

### Installation layout

A normal installation should use a stable machine location such as:

```text
~/.local/share/atlas-agent/
├── releases/
│   └── atlas-agent-vX.Y.Z/
└── codex-homes/
    └── vX.Y.Z/
```

The exact directory convention may evolve, but versioned release state must not
be conflated with mutable project state.

### Idempotence

Re-running installation for an already correct release should succeed without
silently replacing qualified bytes.

An existing inconsistent destination should produce a diagnostic rather than
being partially repaired in place.

### Credentials

The installer must not:

- print credential contents;
- copy credentials into release assets;
- include credentials in release hashes;
- persist provider secrets in project repositories.

### Exit criterion

On a supported Linux host, a user can install a published Atlas Agent release
using one documented command path and obtain a stable `atlas-agent` invocation
without setting `PYTHONPATH` manually.

---

## P0.3 — Implement `atlas-agent install-doctor`

**Priority: critical**

The installation diagnostic must be independent from any project's
`.git/atlas-agent` journal.

### Diagnostic level A — static installation identity

Check at minimum:

```text
Atlas Agent release identity
release manifest validity
qualified Codex target selection
Codex executable regular-file status
Codex executable permissions
Codex SHA-256
CODEX_HOME ownership and permissions
canonical config digest
catalog digest
profile digests
asset-set identity
prompt-set identity
auth reference existence/readability
Bubblewrap presence
basic platform support
```

### Diagnostic level B — zero-token runtime qualification

Exercise the real production chain without calling a model:

```text
qualified Codex bytes
→ sealed runtime authority
→ stable controller-owned runtime path
→ Bubblewrap
→ Codex exec-server
→ current_exe helper dispatch
→ codex-linux-sandbox
→ /bin/true
→ exit 0
→ confirmed child/server reap
→ runtime cleanup
```

This should become a public product diagnostic rather than a pytest-only
maintainer operation.

### Diagnostic level C — optional authenticated smoke

Proposed interface:

```bash
atlas-agent install-doctor --authenticated
```

This may consume model tokens.

It should prove that the host-side Codex controller can authenticate and
complete a minimal model turn using the qualified installation.

The result must distinguish:

```text
installation OK
zero-token runtime OK
authenticated service OK
```

rather than collapsing them into one boolean.

### Exit criterion

A user can determine whether a machine is ready for Atlas-controlled execution
without initializing a project and without reading release-engineering docs.

---

## P0.4 — Add explicit version and installation identity reporting

**Priority: high, small scope**

Provide a stable operator surface such as:

```bash
atlas-agent --version
atlas-agent install-info
```

The exact command names may differ.

### Human-readable output should identify

```text
Atlas Agent tag/version
Atlas Agent commit
asset version
Codex tag
Codex commit
Codex target
Codex executable path
Codex executable SHA-256
CODEX_HOME
asset-set SHA-256
prompt-set SHA-256
Bubblewrap backend/version
```

### Machine-readable output

A JSON form should be available for diagnostics and future automation.

### Exit criterion

A bug report can state the effective installation identity without asking the
operator to reconstruct it from Git and shell variables.

---

# NEXT — validate deployment on Memoria

## P1 — Memoria external-project deployment

**Priority: immediate after the P0 minimum, but useful now with v0.1.1**

Memoria is the first deliberate second-project deployment used to distinguish
Atlas Agent product behavior from assumptions created by the Atlas development
machine state.

There are two valid objectives, and they must not be confused.

---

## P1.A — Fast path: use Atlas with Memoria immediately

Objective:

```text
use the already-qualified v0.1.1 installation on this machine
and initialize only the Memoria project state
```

Reuse:

```text
existing Atlas Agent v0.1.1 machine installation
existing canonical v0.1.1 CODEX_HOME
existing qualified Codex native binary
existing user authentication source
existing Bubblewrap host installation
```

Create independently for Memoria:

```text
project atlas-agent-policy.toml
new .git/atlas-agent workflow state
new repository witness
new prompts
new reports
new project checkpoints
```

This is the fastest route when the objective is to start using Atlas Agent on
Memoria rather than testing installation.

It is not sufficient evidence that the deployment guide works from scratch.

---

## P1.B — Procedure-validation path: isolated Memoria installation prefix

Objective:

```text
validate the v0.1.1 deployment procedure itself
without benefiting from the already-provisioned Atlas CODEX_HOME or Agent checkout
```

This is the preferred path for the current Memoria experiment.

Use an independent prefix:

```bash
export ATLAS_BASE="$HOME/.local/share/atlas-agent-memoria-test"
export ATLAS_AGENT_TAG="atlas-agent-v0.1.1"
export ATLAS_AGENT_SRC="$ATLAS_BASE/releases/$ATLAS_AGENT_TAG"
export ATLAS_CODEX_HOME="$ATLAS_BASE/codex-homes/v0.1.1"

export ATLAS_CODEX_EXECUTABLE="$HOME/luna/codex-atlas/codex-rs/target/release/codex"
```

Expected durable tree:

```text
~/.local/share/atlas-agent-memoria-test/
├── releases/
│   └── atlas-agent-v0.1.1/
└── codex-homes/
    └── v0.1.1/
```

### What must be independent

Do not reuse:

```text
~/.local/share/atlas-agent/releases/atlas-agent-v0.1.1
~/.local/share/atlas-agent/codex-homes/v0.1.1
Atlas development repository workflow journal
Atlas project's policy as project state
Atlas project's prompt/report history
```

The Memoria validation should perform a fresh:

```text
Atlas Agent checkout
→ tag/commit verification
→ release-manifest reading
→ canonical v0.1.1 asset source
→ fresh CODEX_HOME provisioning
→ fresh auth symlink
→ executor-info
→ Bubblewrap/helper qualification where practical
→ Memoria project policy
→ Memoria init
→ Memoria doctor
→ first Memoria execution
```

### What may intentionally be shared

The exact native Codex binary may be reused:

```text
$HOME/luna/codex-atlas/codex-rs/target/release/codex
```

Reason:

```text
its runtime identity is the validated SHA-256 of its bytes,
not ownership by one Atlas Agent installation prefix
```

Duplicating a ~1.3 GB file provides little additional deployment evidence when
both paths point to the same already-qualified bytes.

The user authentication source may also be shared:

```text
~/.codex/auth.json
```

Each independent CODEX_HOME should create its own symlink to that user-owned
mutable credential source.

Bubblewrap and normal host libraries are machine prerequisites and are also
shared.

### Why this test is stronger

This arrangement prevents accidental success caused by:

- a previously prepared Agent checkout;
- a previously populated CODEX_HOME;
- stale mutable Codex state from Atlas development;
- hidden manual fixes performed during the v0.1.1 release marathon.

At the same time it avoids testing irrelevant duplication of an executable
whose exact bytes are already the qualified authority.

### Result interpretation

If the isolated-prefix procedure succeeds, we have evidence that:

```text
the deployment guide is sufficient on this machine
for a fresh Atlas Agent release checkout and fresh CODEX_HOME
```

It does **not** yet prove virgin-machine deployment because the qualified Codex
binary and authentication already exist on the host.

That remaining gap is precisely why P0.1 and P0.2 exist.

---

## P1.1 — Memoria first project initialization

Before `atlas-agent init`:

- inspect Memoria's Git state;
- identify existing modified/untracked files;
- read repository instructions;
- install and review Memoria's `atlas-agent-policy.toml`;
- verify that the repository uses a supported real `.git/` directory;
- verify there is no conflicting project-local `.codex/config.toml`;
- establish a deliberate stable repository boundary.

Only then initialize the project workflow.

### Required checks after init

```text
doctor: OK
state: MATCH
repository witness: MATCH
executor-info resolves the intended installation
```

### Exit criterion

Memoria has a new project-specific Atlas workflow with no imported Atlas
journal/history and a clean, understandable initial witness.

---

## P1.2 — Memoria first real task

The first useful task should be bounded enough to audit but real enough to
exercise project integration.

Preferred cycle:

```text
implementation / Luna
→ project tests
→ patch_review / Sol
→ correction if required
→ review again if required
→ manual checkpoint
```

The purpose is not to benchmark Luna or Sol.

The purpose is to discover deployment and workflow assumptions outside the
Atlas repository.

### Record friction separately

Classify observed problems as:

```text
machine installation
installation diagnostic
project initialization
repository topology
repository witness
policy/defaults
prompt ergonomics
runtime execution
result diagnostics
checkpoint workflow
documentation
Memoria-specific project behavior
```

Do not modify Atlas Agent for a Memoria-specific inconvenience unless the same
problem plausibly affects other projects.

---

## P1.3 — Stabilization pass after Memoria

**Priority: high but strictly bounded**

After the first Memoria cycle, fix only generic problems demonstrated by the
external deployment.

Possible outcomes include:

- better error messages;
- safer defaults;
- installer fixes;
- install-doctor checks;
- documentation corrections;
- project bootstrap ergonomics;
- narrow support for a common Git topology if strongly justified.

Avoid broad redesign.

### Exit criterion

A second clean Memoria initialization/deployment path no longer requires
undocumented maintainer knowledge.

---

# THEN — close the remaining narrow Agent semantic debt

## P2 — Distinguish execution health from task success

**Priority: medium-high, deliberately narrow**

The current lifecycle can establish that a subprocess completed successfully.

It cannot always prove that the intended semantic task succeeded.

These are different statements:

```text
Codex process exited 0
Atlas execution lifecycle completed
model tool calls succeeded
requested project task succeeded
review accepted the result
```

### Required direction

Introduce the smallest structured result contract that can distinguish at
least:

```text
execution_health
observed_tool_failure
reported_task_outcome
review/checkpoint status
```

Do not build a general workflow orchestrator.

Do not make model self-reporting the sole authority for execution health.

### Exit criterion

Operator-facing status can explain the difference between:

```text
COMPLETED because execution infrastructure succeeded
```

and:

```text
task accepted as successful by the project workflow
```

---

## P2.1 — Freeze Atlas Agent feature expansion

Once P0/P1/P2 are sufficiently complete, Atlas Agent enters a maintenance-first
phase.

New Agent work should normally require one of:

```text
repeated external-project friction
security-policy enforcement gap
release/install reliability defect
blocking inability to develop Atlas Core
material observability problem
```

"Would be convenient" is insufficient by itself.

---

# THEN — return priority to Atlas Core

## P3 — Re-center development on Atlas

**Priority: strategic**

Atlas is not an agent orchestrator.

Its core purpose is to represent, qualify, search, select, compose, and
eventually execute reusable semantic computational components.

The development stack remains conceptually:

```text
applications / user intent
→ semantic specification
→ Atlas Semantic Core
→ qualified component catalogue
→ selection / synthesis / composition
→ materialized IR
→ validation / lowering
→ CPU / GPU / VM / other backends
```

Atlas Agent is infrastructure below the development process, not a layer in
this semantic architecture.

---

## P3.1 — External corpora and qualification pressure

**Priority: first major Atlas Core direction after Agent stabilization**

Use more external technical corpora and reusable computational components to
exercise the semantic model.

The objective is not corpus size for its own sake.

The objective is to force real questions about:

```text
identity
contracts
preconditions
postconditions
effects
algebraic properties
precision/error
determinism
memory
cost
alternative implementations
applicability
provenance
evidence
versioning
```

### Why before major semantic expansion

Core V1 already implements a substantial vertical slice.

External material should reveal which extensions are actually necessary.

Do not generalize the ontology merely because an abstraction seems elegant.

### Exit criterion

At least several independent external component families can be admitted,
qualified, queried, and compared without special-case code for their domain.

---

## P3.2 — Component search and candidate discovery

**Priority: high**

Make Atlas useful as a semantic catalogue rather than only a persisted reasoning
fixture.

Given a declared intention/problem, Atlas should be able to identify candidate
realizations from stored qualified components.

The initial focus should remain explainable and exact.

### Required properties

Search must not silently conflate:

```text
identity
semantic equivalence
similarity
applicability
admissibility
optimality
```

The system should explain why a candidate was found and why it was included or
excluded from a decision scope.

### Exit criterion

A real external query produces multiple qualified candidates and a structured
explanation of discovery and filtering.

---

## P3.3 — Selection and composition from real components

**Priority: high**

Extend the existing grounded-decision machinery under pressure from real
component choices.

Prefer cases where:

- multiple realizations satisfy one intent;
- resources or preprocessing can be shared;
- costs differ by context;
- applicability depends on explicit properties;
- composition changes total cost or feasibility.

Do not start by implementing every backend from the specification.

Use the smallest decision machinery justified by observed cases.

### Exit criterion

Atlas selects or composes a non-trivial real component solution that can be
reproduced from persisted semantic evidence.

---

## P3.4 — Black-box Core V1 conformance façade

**Priority: high once external consumers appear**

The Core V1 profile already requires conformance tests that do not depend on
SQLite internals or implementation classes.

Create a small stable black-box façade around the semantics that external
implementations or future backends must preserve.

### Initial conformance focus

```text
nominal identity
value validation
order and uniqueness semantics
participant-scoped property resolution
multivalued relations
TRUE/FALSE/UNKNOWN
negative assertion distinction
provenance and dependencies
snapshots and stale semantics
grounding completeness
selection correctness
restart/reproduction
```

### Exit criterion

Core V1 semantics can be validated through a public test surface independent of
its SQLite storage implementation.

---

## P3.5 — Materialization only after semantic selection is convincing

Do not prioritize MIR, RISC-V, WASM, GPU lowering, or other execution backends
merely because they are technically attractive.

Those are downstream consumers of Atlas decisions.

They become priority when Atlas can already select a meaningful semantic
realization whose materialization needs to be demonstrated.

---

# LATER — release automation

## P4 — Mechanize the release procedure

**Priority: medium**

The v0.1.1 release procedure is intentionally explicit and manual.

Do not immediately automate every gate.

Automate steps that are deterministic and repeatedly expensive.

Candidate automation:

```text
manifest validation
asset identity generation/verification
prompt/profile identity verification
focused test bundles
full-suite invocation
Codex binary identity capture
zero-token qualification
release-state audit
tag dereference verification
remote publication verification
artifact metadata generation
```

Human/operator gates should remain around decisions such as:

```text
release scope
Sol review disposition
security review disposition
authenticated smoke interpretation
final publication approval
```

### Exit criterion

A release requires less manual bookkeeping while preserving the explicit audit
trail and fail-closed gates learned from v0.1.1.

---

# LATER — targeted security closure

## P5 — Review enforcement against the security policy

**Priority: medium; evidence-driven**

The security policy now defines the authority model more clearly than the old
implicit implementation assumptions.

Perform focused audits for places where external configuration could enlarge
capabilities beyond the controller-owned ceiling.

Potential review areas:

```text
project Codex configuration
Codex rule/config discovery
hooks and MCP/tool surfaces
environment inheritance
credential exposure
network enforcement
filesystem grant mapping
repo metadata write authority
runtime substitution
```

### Constraint

Do not turn this into a general security framework project.

Fix concrete mismatches between documented authority and mechanical
enforcement.

### Exit criterion

No known configuration path can enlarge the effective capability grant beyond
the Atlas policy ceiling under the documented baseline threat model.

---

# LATER — operator ergonomics

## P6 — Simplify common project operations under evidence

**Priority: medium-low until Memoria evidence exists**

Possible improvements:

```text
project bootstrap command
policy template installation
prompt creation helpers
clearer status summaries
better error remediation text
installation/project path display
workflow-history navigation
```

These should be prioritized from observed friction, not hypothetical UX work.

Do not hide important authority decisions merely to reduce command count.

---

# LATER — Linux platform breadth

## P7 — Additional Linux targets and Git topologies

**Priority: low until x86_64 golden path is stable**

Candidates:

```text
Linux ARM64
linked Git worktrees
other supported repository layouts
container-hosted operation
additional Bubblewrap versions/distributions
```

Each target requires qualification of the complete execution boundary, not
merely proof that upstream Codex can run there.

### Linked worktree note

Workflow journal path discovery already understands `git rev-parse --git-path`,
but the current Bubblewrap execution backend requires a real repository-root
`.git/` directory.

Support should be added only with an explicit sandbox design for Git metadata
ownership, not by weakening the current topology check.

---

# LATER — other operating systems

## P8 — macOS, Windows, and alternate isolation backends

**Priority: deferred**

Codex portability does not imply Atlas execution-boundary portability.

A new OS requires a new Atlas isolation backend with equivalent explicit
capability semantics and qualification.

Do not block Linux usability or Atlas Core progress on this work.

---

# LATER — broader Atlas semantic capabilities

## P9 — Expand semantics only under demonstrated need

Core V1 intentionally leaves many areas open:

```text
quantification and intervals
rich state transitions
temporal planning and lifetimes
reactive truth maintenance
quantitative uncertainty
CP-SAT / SMT / MILP backends
multiobjective decisions
information acquisition / Semantic Recovery
code materialization and validation
general semantic equivalence
distributed stores and replication
concurrent update policies
```

These are not one backlog to implement sequentially.

They are candidate directions.

Promote one to active roadmap status only when a real use case requires it or
an experiment establishes a strong architectural reason.

---

## 10. Suggested release sequence

The following sequence is intentionally indicative rather than a version-number
promise.

### Atlas Agent v0.1.1 — completed baseline

```text
qualified runtime
versioned assets/prompts
stable Bubblewrap helper execution
release manifest
release procedure
manual deployable Linux path
```

### Next Agent tranche — installable Linux product

Possible release identity:

```text
v0.1.2
```

Candidate contents:

```text
qualified Codex artifact distribution
atlas-agent install
atlas-agent install-doctor
version/install-info surface
Memoria-derived generic deployment fixes
```

If the installer introduces sufficiently large product semantics, choosing
`v0.2.0` instead remains reasonable.

The number should follow the actual change, not determine its scope in advance.

### Following phase

Do not plan another large Agent release by default.

Move priority to:

```text
Atlas external corpora
component qualification
search/discovery
selection/composition
Core V1 conformance
```

---

## 11. Definition of "Atlas Agent sufficiently finished for now"

Atlas Agent can enter maintenance-first mode when all of the following are true:

```text
one published Linux x86_64 Agent release installs without dev-checkout knowledge
exact Codex binary retrieval and SHA verification are automated
canonical CODEX_HOME provisioning is automated
user authentication is connected without secret copying
install-doctor validates static installation state
install-doctor performs a zero-token runtime probe
an optional authenticated smoke works
project init/doctor remain separate from installation diagnostics
Memoria has completed at least one real implementation/review/checkpoint cycle
no undocumented Atlas-development state is required
execution health versus task outcome is understandable to the operator
```

This is a stopping criterion.

It is deliberately not a claim that Atlas Agent is feature-complete forever.

---

## 12. Definition of a successful Memoria deployment experiment

The current preferred experiment is the isolated-prefix procedure-validation
path.

Success requires:

```text
fresh Atlas Agent v0.1.1 checkout under atlas-agent-memoria-test
clean tag/commit validation
fresh v0.1.1 CODEX_HOME under atlas-agent-memoria-test
canonical asset provisioning succeeds
fresh auth symlink points to the existing user auth source
shared Codex binary matches the release SHA
executor-info reports the intended native runtime
Bubblewrap/helper execution succeeds
Memoria policy is established before init
Memoria gets a new workflow journal
Memoria doctor reports a coherent initial state
first real task executes through Luna
independent Sol review executes
checkpoint completes without importing Atlas project history
```

Any undocumented step needed to make this succeed is deployment friction and
should be recorded.

---

## 13. What the Memoria experiment intentionally does not test

It does not prove:

```text
virgin-machine Codex artifact download
first-time user authentication setup
Linux ARM64 support
macOS or Windows support
linked-worktree support
reproducible Codex builds
multi-user system installation
container distribution
```

Those claims require separate qualification.

The experiment remains valuable because it isolates the newly documented
release-checkout and CODEX_HOME provisioning path from Atlas's previously
prepared installation state.

---

## 14. Shared versus duplicated state for multiple projects on one machine

Normal long-term operation should prefer sharing qualified machine-level state.

### Share normally

```text
installed Atlas Agent release checkout, when using the same release
exact qualified Codex executable
user authentication source
Bubblewrap binary and host runtime
```

### Version separately by release

```text
canonical Atlas Codex CODEX_HOME
release manifests
release assets/prompts
```

### Always isolate by project

```text
atlas-agent-policy.toml as project policy
.git/atlas-agent journal
repository witness
accepted/running/completed prompts
execution reports
checkpoints
project-specific allowed-untracked configuration
```

### Test installations may deliberately duplicate machine state

An isolated deployment test may create a new Agent checkout and CODEX_HOME even
when equivalent qualified state already exists.

That duplication is testing instrumentation, not the recommended steady-state
layout.

---

## 15. Roadmap decision rule

Before adding an item above P6, ask:

```text
Does this block reliable installation?
Does this block external-project use?
Does this reveal an enforcement gap?
Does this block Atlas Core semantic work?
Has the problem occurred in more than one context?
```

If all answers are no, defer the work unless it is exceptionally small and
clearly reduces future maintenance.

---

## 16. Avoided roadmap traps

### Trap: continuously hardening the Agent before using it

Security work without a concrete policy/enforcement mismatch can consume
unbounded effort.

The current policy defines a baseline and optional hardening path.

Use it.

### Trap: building an orchestrator

Atlas Agent should not grow planners, queues, background autonomy, role graphs,
or general multi-agent scheduling merely because they are possible.

Those features need an actual Atlas development requirement.

### Trap: automating release before understanding repeated release patterns

v0.1.1 produced the first precise release procedure.

A few manual releases provide evidence about what should be automated.

### Trap: generalizing Atlas semantics from imagined future domains

Use external corpora and components first.

Let failures drive semantic extension.

### Trap: treating more backends as proof of Atlas value

A RISC-V, WASM, GPU, or VM backend can be technically successful while Atlas's
semantic selection remains unproven.

Backends should demonstrate a semantic decision, not replace one.

---

## 17. Current priority summary

```text
P0.1  qualified Codex artifact distribution
P0.2  atlas-agent install
P0.3  atlas-agent install-doctor
P0.4  version / install identity reporting

P1    isolated-prefix Memoria deployment
P1.1  Memoria project initialization
P1.2  first real implementation → review → checkpoint cycle
P1.3  bounded generic stabilization from observed friction

P2    execution-health versus task-success contract
P2.1  freeze broad Agent feature expansion

P3.1  external corpora and component qualification
P3.2  semantic candidate search/discovery
P3.3  real selection/composition
P3.4  black-box Core V1 conformance
P3.5  materialization only when semantically motivated

P4    selective release automation
P5    targeted security enforcement review
P6    evidence-driven operator ergonomics
P7    broader Linux targets/topologies
P8    other OS isolation backends
P9    broader Atlas semantics under demonstrated need
```

---

## 18. Immediate next concrete sequence

The practical sequence from the current repository state is:

```text
1. keep v0.1.1 immutable
2. use docs/deploy-existing-project.md against Memoria with an isolated prefix
3. record every undocumented/manual friction point
4. reuse the already-qualified Codex binary by exact SHA
5. provision a completely fresh Memoria-test CODEX_HOME
6. initialize a completely fresh Memoria workflow
7. complete one real Luna/Sol/checkpoint cycle
8. convert repeated deployment friction into P0 installer/doctor requirements
9. implement the minimum install + install-doctor tranche
10. repeat Memoria deployment using the new commands
11. stop broad Agent expansion
12. return primary development effort to Atlas Core external semantic use cases
```

---

## 19. Guiding end state

The desired near-term experience is intentionally unremarkable.

For a new machine:

```bash
atlas-agent install
atlas-agent install-doctor
```

For a new project:

```bash
cd project
# establish project policy
atlas-agent init
atlas-agent doctor
```

For normal work:

```bash
atlas-agent ingest
atlas-agent dispatch
```

The operator should not need to know:

```text
where the Codex fork was built
how sealed memfd runtime authority works
why current_exe needed a stable path
how asset-set hashes are constructed
how release tag objects dereference
how Bubblewrap exec-server startup is qualified
how v0.1.1 was debugged
```

Those remain maintainers' concerns captured by the release procedure and
machine diagnostics.

When this is true, Atlas Agent has achieved its immediate purpose:

```text
reliable infrastructure that fades into the background
while Atlas itself becomes the thing being developed and evaluated
```
