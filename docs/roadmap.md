# Atlas / Atlas Agent — Roadmap

Document version: **0.2**

This roadmap reflects the state reached after Atlas Agent v0.1.1 and the
release/deployment qualification work performed around it.

It is a prioritization document, not a catalogue of every possible Atlas
feature.

The central rule is:

> Atlas Agent exists to make Atlas development reliable. Once it is installable,
> diagnosable, and proven on an external project, further Agent sophistication
> must not displace Atlas Core work without concrete evidence that the
> infrastructure is blocking progress.

The immediate objective is therefore:

```text
finish minimal Linux installation
→ validate it outside the Atlas repository
→ fix only generic deployment friction
→ return primary effort to Atlas Core
```

---

## 1. Current planning boundary

Primary supported target for the next tranche:

```text
OS                  Linux
shell               bash
architecture        x86_64
sandbox             Bubblewrap
controller          qualified Atlas Codex fork
```

Other platforms remain future targets, but they must not delay the current
Linux golden path.

The roadmap uses four horizons:

```text
NOW     finish the machine-installation product
NEXT    validate it on Memoria
THEN    return to Atlas Core and external semantic use cases
LATER   automation, portability, broader hardening, optional ergonomics
```

---

## 2. Baseline established by v0.1.1

Atlas Agent v0.1.1 qualified:

- an exact Atlas Agent release and manifest;
- an exact Atlas Codex source release;
- a native Codex executable identified by SHA-256;
- versioned canonical Codex assets;
- versioned compact prompts;
- atomic CODEX_HOME provisioning;
- runtime identity checks before execution;
- sealed executable authority;
- a stable runtime path compatible with Codex `current_exe()`;
- Bubblewrap execution through the real Codex exec-server;
- zero-token live helper execution;
- an authenticated Luna smoke;
- an explicit release procedure;
- a deployment guide separating machine installation from project state.

The immediate problem is no longer whether Atlas Agent can run a qualified
model.

It is now:

```text
can a user install and diagnose the qualified system
without reconstructing release-engineering knowledge by hand?
```

---

## 3. Durable planning principles

### 3.1 Keep identities separate

Independent dimensions include:

```text
Atlas Agent source/tag/commit
Atlas Codex source/tag/commit
Codex executable bytes/SHA
canonical assets
prompt set
project policy
user authentication
project workflow journal
Git publication state
```

Changing one must not silently imply changing another.

### 3.2 Agent release != Codex release

A new Atlas Agent release does not require a new Codex release when Codex
source and binary bytes are unchanged.

### 3.3 Binary bytes are runtime authority

A path locates the executable.

Its SHA-256 identifies the qualified runtime.

Therefore one exact qualified Codex binary may legitimately be shared by
multiple independent Atlas Agent installations on one machine.

### 3.4 Assets and auth are different state classes

Canonical assets are versioned release state.

Authentication is mutable user state.

A CODEX_HOME may reference user auth after asset provisioning without adding
the secret to the canonical asset set.

### 3.5 Machine and project lifecycles are different

Machine state:

```text
Agent release
qualified Codex binary
canonical CODEX_HOME
auth reference
Bubblewrap/runtime prerequisites
```

Project state:

```text
atlas-agent-policy.toml
.git/atlas-agent
repository witness
prompts/reports/checkpoints
```

### 3.6 `doctor` is not an installation diagnostic

`atlas-agent doctor` validates project workflow state.

A separate installation diagnostic is required.

### 3.7 External projects are product tests

A second project can reveal hidden assumptions prepared by Atlas's own
development environment.

### 3.8 Atlas Agent must become boring

After installation and external-project validation, new Agent features require
repeated evidence of need.

---

# NOW — minimum installable Atlas Agent

## P0.1 — Distribution of the qualified Codex runtime

**Priority: critical**

The largest remaining virgin-machine gap is distribution of the exact native
Codex executable recorded by `atlas-release.toml`.

A local rebuild is not automatically the qualified binary, even from the same
source commit.

Initial supported target:

```text
x86_64-unknown-linux-gnu
```

Required properties:

- immutable published artifact;
- explicit association with Codex tag and commit;
- SHA-256 recorded in the Agent release manifest;
- retrievable by the future installer;
- no trust based only on filename or tag;
- no dependency on a maintainer development checkout.

Do not make reproducible builds a prerequisite for this first step.

### Exit criterion

A fresh Linux host can obtain the exact binary required by a published Atlas
Agent release and verify its SHA without access to Atlas/Codex development
working directories.

---

## P0.2 — `atlas-agent install`

**Priority: critical**

Turn the manual bootstrap from `docs/deploy-existing-project.md` into a
supported machine-level command.

Responsibilities:

- select/resolve one Agent release;
- read and validate `atlas-release.toml`;
- select the supported host target;
- obtain or locate the exact Codex executable;
- verify its SHA-256 and permissions;
- install a stable `atlas-agent` command;
- provision canonical CODEX_HOME atomically;
- verify asset and prompt identities;
- connect mutable user auth without copying secrets;
- verify host prerequisites;
- leave project repositories untouched.

Recommended durable layout:

```text
~/.local/share/atlas-agent/
├── releases/
│   └── atlas-agent-vX.Y.Z/
└── codex-homes/
    └── vX.Y.Z/
```

The installer should be idempotent for an already-correct installation and
refuse unexplained inconsistent state rather than partially repairing it.

It must never print, commit, release-hash, or copy credential contents into
canonical assets.

### Exit criterion

A supported Linux user can install one published Agent release without manual
`PYTHONPATH`, manual asset copying, or source-tree archaeology.

---

## P0.3 — `atlas-agent install-doctor`

**Priority: critical**

The diagnostic must operate without any project `.git/atlas-agent` journal.

### Level A — static identity

Check at least:

```text
Agent release/tag/commit
release manifest
Codex target/path/type/permissions/SHA
CODEX_HOME ownership/permissions
config/catalog/profile digests
asset-set identity
prompt-set identity
auth link/readability
Bubblewrap presence
platform support
```

### Level B — zero-token production probe

Exercise:

```text
qualified Codex bytes
→ sealed runtime authority
→ stable runtime path
→ Bubblewrap
→ Codex exec-server
→ current_exe helper
→ codex-linux-sandbox
→ /bin/true
→ exit 0
→ confirmed reap/cleanup
```

This should become a public product diagnostic, not remain pytest-only.

### Level C — optional authenticated smoke

Proposed form:

```bash
atlas-agent install-doctor --authenticated
```

It may consume tokens and should prove host-side Codex authentication plus one
minimal model turn.

Report the three levels independently:

```text
installation identity OK
zero-token runtime OK
authenticated service OK
```

### Exit criterion

A user can determine whether a machine is ready for Atlas execution without
initializing a project or reading the release procedure.

---

## P0.4 — Version and installation identity

**Priority: high, small scope**

Provide a stable surface such as:

```bash
atlas-agent --version
atlas-agent install-info
```

Human and JSON output should identify at least:

```text
Agent tag/version/commit
asset version
Codex tag/commit/target
Codex path/SHA
CODEX_HOME
asset-set SHA
prompt-set SHA
Bubblewrap backend/version
```

### Exit criterion

A bug report can state the effective runtime identity without shell archaeology.

---

# NEXT — validate deployment on Memoria

## P1 — Why Memoria has two possible deployment objectives

Memoria is the first deliberate second-project deployment.

Two objectives are valid but must not be confused.

### Objective A — use Atlas with Memoria as quickly as possible

Reuse the already-qualified v0.1.1 machine installation and create only Memoria
project state.

Reuse:

```text
existing Agent v0.1.1 installation
existing v0.1.1 CODEX_HOME
existing qualified Codex binary
existing user auth source
existing Bubblewrap host installation
```

Create independently:

```text
Memoria atlas-agent-policy.toml
Memoria .git/atlas-agent
Memoria repository witness
Memoria prompts/reports/checkpoints
```

This is the right path when the goal is simply to start using Atlas Agent.

It does not validate the deployment guide from a fresh Agent/CODEX_HOME state.

---

## P1.B — Preferred current experiment: isolated Memoria installation prefix

To validate the v0.1.1 deployment procedure itself, create an independent Agent
checkout and CODEX_HOME.

Use:

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

### Must be independent

Do not reuse:

```text
existing Agent v0.1.1 checkout
existing Atlas v0.1.1 CODEX_HOME
Atlas development workflow journal
Atlas project policy as Memoria project state
Atlas prompts/reports/checkpoints
```

Perform fresh:

```text
Agent checkout
→ tag/commit verification
→ manifest reading
→ v0.1.1 asset source validation
→ fresh CODEX_HOME provisioning
→ fresh auth symlink
→ executor-info
→ Bubblewrap/helper qualification
→ Memoria policy
→ Memoria init/doctor
→ first Memoria execution
```

### May intentionally be shared

Reuse the exact qualified Codex binary.

Its identity is the validated SHA-256 of its bytes, not ownership by one
installation prefix.

Copying a roughly 1.3 GB identical file provides little additional evidence.

Reuse the user auth source, normally:

```text
~/.codex/auth.json
```

Each CODEX_HOME gets its own symlink to that mutable user-owned source.

Bubblewrap and host libraries are normal shared machine prerequisites.

### What this experiment proves

Success demonstrates that, on this already-qualified machine, the deployment
guide is sufficient for:

```text
fresh Agent checkout
fresh canonical CODEX_HOME
fresh auth wiring
fresh project initialization
```

It does **not** prove virgin-machine Codex artifact download or first-time user
auth setup.

Those remaining claims belong to P0.1/P0.2.

---

## P1.1 — Memoria project initialization

Before `atlas-agent init`:

- inspect Memoria Git state;
- understand existing modified/untracked files;
- read project instructions;
- establish/review Memoria `atlas-agent-policy.toml`;
- verify a supported real `.git/` directory;
- verify no conflicting project `.codex/config.toml`;
- choose a deliberate stable repository boundary.

Then require:

```text
doctor: OK
state: MATCH
repository witness: MATCH
executor-info resolves intended installation
```

### Exit criterion

Memoria has its own clean workflow history with no imported Atlas journal.

---

## P1.2 — First real Memoria task

Use a bounded real task, not only a synthetic smoke.

Preferred cycle:

```text
implementation / Luna
→ project tests
→ patch_review / Sol
→ correction if required
→ review again if required
→ manual checkpoint
```

Record friction separately as:

```text
machine installation
installation diagnostic
project initialization
repository topology/witness
policy/defaults
prompt ergonomics
runtime execution/result diagnostics
checkpoint workflow
documentation
Memoria-specific behavior
```

Do not change Atlas Agent for a Memoria-specific inconvenience unless it
plausibly generalizes.

### Exit criterion

One useful Memoria change completes the full implementation/review/checkpoint
cycle under a fresh project workflow.

---

## P1.3 — Bounded stabilization after Memoria

Fix only generic problems demonstrated by the deployment.

Likely categories:

```text
error messages
installer/doctor checks
safe defaults
documentation corrections
project bootstrap ergonomics
common repository assumptions
```

Avoid broad redesign.

### Exit criterion

Repeating the Memoria deployment no longer requires undocumented maintainer
knowledge.

---

# THEN — narrow remaining Agent debt

## P2 — Execution health versus task success

**Priority: medium-high, narrow scope**

Keep separate:

```text
Codex process exited 0
Atlas lifecycle completed
model tool calls succeeded
requested task succeeded
review accepted result
checkpoint finalized result
```

Introduce the smallest structured result contract needed to distinguish:

```text
execution_health
observed_tool_failure
reported_task_outcome
review/checkpoint status
```

Do not build a general orchestrator.

Do not make model self-reporting the authority for process health.

### Exit criterion

Operator status clearly explains infrastructure completion versus project-task
acceptance.

---

## P2.1 — Freeze broad Agent feature expansion

After P0/P1/P2, Agent work should normally require one of:

```text
repeated external-project friction
security-policy enforcement gap
release/install reliability defect
blocking Atlas Core limitation
material observability defect
```

Convenience alone is not enough.

---

# THEN — return priority to Atlas Core

## P3 — Re-center on Atlas

Atlas is not an agent orchestrator.

Its conceptual stack remains:

```text
applications / intent
→ semantic specification
→ Atlas Semantic Core
→ qualified component catalogue
→ selection / synthesis / composition
→ materialized IR
→ validation / lowering
→ CPU / GPU / VM / other backends
```

Agent infrastructure must fade into the development background.

---

## P3.1 — External corpora and component qualification

**Priority: first major Core direction after Agent stabilization**

Use external technical corpora and reusable computational components to pressure
the semantic model.

Exercise real questions about:

```text
identity
contracts
pre/postconditions
effects
algebraic properties
precision/error
determinism
memory/cost
alternative implementations
applicability
provenance/evidence
versioning
```

Core V1 is already substantial enough that real material should drive the next
semantic extensions.

### Exit criterion

Several independent external component families can be admitted, qualified,
queried, and compared without domain-specific branches.

---

## P3.2 — Semantic candidate search/discovery

**Priority: high**

Given a declared intention/problem, find candidate realizations from qualified
stored components.

Do not conflate:

```text
identity
semantic equivalence
similarity
applicability
admissibility
optimality
```

Discovery should explain why candidates were found, included, or excluded.

### Exit criterion

A real external query produces multiple qualified candidates and structured
discovery/filtering evidence.

---

## P3.3 — Selection and composition from real components

**Priority: high**

Use real cases with alternative realizations, shared resources/preprocessing,
context-dependent costs, and explicit applicability constraints.

Prefer the smallest decision machinery justified by observed cases.

Do not implement every solver backend in advance.

### Exit criterion

Atlas selects or composes a non-trivial real solution reproducibly from
persisted semantic evidence.

---

## P3.4 — Black-box Core V1 conformance

**Priority: high once external consumers appear**

Create a small stable façade independent of SQLite/classes.

Initial conformance focus:

```text
nominal identity
value validation
order/uniqueness semantics
participant-scoped property resolution
multivalued relations
TRUE/FALSE/UNKNOWN
negative assertion distinction
provenance/dependencies
snapshots/stale
grounding completeness
selection correctness
restart/reproduction
```

### Exit criterion

Core V1 semantics can be tested through a public surface independent of storage
implementation.

---

## P3.5 — Materialization only when semantically motivated

Do not prioritize MIR, RISC-V, WASM, GPU lowering, or VM backends merely
because they are attractive engineering projects.

They should demonstrate an already meaningful Atlas semantic decision.

---

# LATER

## P4 — Selective release automation

Automate deterministic, repeatedly expensive parts of the release procedure:

```text
manifest/asset/prompt validation
test bundles
Codex binary identity capture
zero-token qualification
release-state audit
tag/remote verification
artifact metadata
```

Keep human gates around scope, independent review disposition, security review,
authenticated smoke interpretation, and final publication.

---

## P5 — Targeted security enforcement review

Audit concrete paths where external configuration might enlarge authority beyond
the controller-owned ceiling:

```text
project Codex config/rules
hooks/MCP/tool surfaces
environment inheritance
credential exposure
network enforcement
filesystem grants
repo metadata write authority
runtime substitution
```

Do not build a general security framework.

Fix documented policy/enforcement mismatches.

---

## P6 — Evidence-driven operator ergonomics

Possible work after Memoria evidence:

```text
project bootstrap
policy template installation
prompt helpers
clearer status/remediation
installation/project path display
workflow-history navigation
```

Do not hide authority decisions merely to reduce command count.

---

## P7 — Broader Linux targets/topologies

Later candidates:

```text
Linux ARM64
linked Git worktrees
other repository layouts
container-hosted operation
additional Bubblewrap environments
```

Each target requires qualification of the complete Atlas execution boundary.

Linked-worktree support needs an explicit Git-metadata sandbox design, not a
weakened topology check.

---

## P8 — Other operating systems

macOS, Windows, and alternate isolation backends are deferred until the Linux
golden path is stable and Atlas Core work is again primary.

Codex portability alone does not establish Atlas boundary portability.

---

## P9 — Broader Atlas semantics under demonstrated need

Candidate directions remain:

```text
quantification/intervals
rich state transitions
temporal planning/lifetimes
reactive truth maintenance
quantitative uncertainty
CP-SAT / SMT / MILP
multiobjective decisions
information acquisition / Semantic Recovery
code materialization/validation
general semantic equivalence
distributed stores/replication
concurrent update policies
```

These are not a sequential implementation backlog.

Promote one only when real use cases or experiments justify it.

---

## 4. Suggested near-term release sequence

### v0.1.1 — completed baseline

```text
qualified runtime
versioned assets/prompts
stable Bubblewrap helper execution
release manifest/procedure
manual Linux deployment path
```

### Next Agent tranche

Likely scope:

```text
qualified Codex artifact distribution
atlas-agent install
atlas-agent install-doctor
version/install-info
Memoria-derived generic fixes
```

`v0.1.2` is plausible.

`v0.2.0` is also reasonable if installation introduces sufficiently large
product semantics.

Version number should follow actual scope, not determine it in advance.

After this tranche, do not plan another large Agent release by default.

Return priority to:

```text
external corpora
component qualification
search/discovery
selection/composition
Core V1 conformance
```

---

## 5. Stopping criterion for Atlas Agent expansion

Atlas Agent is sufficiently finished for the current phase when:

```text
published Linux x86_64 release installs without dev-checkout knowledge
Codex artifact retrieval/SHA verification are automated
CODEX_HOME provisioning is automated
auth is connected without secret copying
install-doctor validates static state
install-doctor performs zero-token runtime probe
optional authenticated smoke works
project init/doctor remain separate from installation diagnosis
Memoria completes a real implementation/review/checkpoint cycle
no undocumented Atlas-development state is required
execution health versus task outcome is understandable
```

This is a stopping rule, not a permanent feature-completeness claim.

---

## 6. Successful Memoria procedure-validation experiment

Preferred current path: isolated installation prefix.

Success requires:

```text
fresh v0.1.1 Agent checkout under atlas-agent-memoria-test
clean tag/commit validation
fresh v0.1.1 CODEX_HOME under atlas-agent-memoria-test
canonical asset provisioning
fresh auth symlink to existing user auth
shared Codex binary matches release SHA
executor-info resolves intended runtime
Bubblewrap/helper execution succeeds
Memoria policy exists before init
Memoria gets a new workflow journal
Memoria doctor reports coherent state
first real Luna task completes
independent Sol review completes
checkpoint completes without imported Atlas history
```

Any undocumented step needed to make this work is deployment friction.

The experiment intentionally does not prove:

```text
virgin-machine Codex download
first-time authentication setup
Linux ARM64
macOS/Windows
linked worktrees
reproducible Codex builds
multi-user installation
container distribution
```

---

## 7. Shared versus duplicated state on one machine

Normal steady state should share:

```text
installed Agent release when same version is used
exact qualified Codex executable
user authentication source
Bubblewrap and host runtime
```

Version separately by release:

```text
canonical CODEX_HOME
release assets/prompts
release manifest
```

Always isolate by project:

```text
atlas-agent-policy.toml
.git/atlas-agent journal
repository witness
prompts/reports/checkpoints
project-specific allowed-untracked configuration
```

A deployment test may deliberately duplicate Agent checkout and CODEX_HOME.

That duplication is test instrumentation, not the recommended steady-state
layout.

---

## 8. Roadmap decision rule

Before promoting new Agent work, ask:

```text
Does it block reliable installation?
Does it block external-project use?
Does it reveal an enforcement gap?
Does it block Atlas Core work?
Has the problem appeared in more than one context?
```

If all answers are no, defer it unless exceptionally small and clearly
maintenance-reducing.

Avoid these traps:

- hardening indefinitely before using the system;
- growing Atlas Agent into an orchestrator;
- automating all release gates before repeated evidence;
- generalizing Atlas semantics from imagined future domains;
- treating more execution backends as proof of semantic value.

---

## 9. Current priority summary

```text
P0.1  qualified Codex artifact distribution
P0.2  atlas-agent install
P0.3  atlas-agent install-doctor
P0.4  version/install identity reporting

P1    isolated-prefix Memoria deployment
P1.1  Memoria initialization
P1.2  real implementation → review → checkpoint
P1.3  bounded generic stabilization

P2    execution-health versus task-success contract
P2.1  freeze broad Agent expansion

P3.1  external corpora/component qualification
P3.2  semantic candidate discovery
P3.3  real selection/composition
P3.4  black-box Core V1 conformance
P3.5  materialization when semantically motivated

P4    selective release automation
P5    targeted security enforcement review
P6    evidence-driven ergonomics
P7    broader Linux targets/topologies
P8    other OS isolation backends
P9    broader Atlas semantics under demonstrated need
```

---

## 10. Immediate concrete sequence

```text
1. keep v0.1.1 immutable
2. deploy v0.1.1 for Memoria under atlas-agent-memoria-test
3. reuse the exact already-qualified Codex binary by SHA
4. create a completely fresh Agent checkout and CODEX_HOME
5. record every undocumented deployment step
6. initialize a completely fresh Memoria workflow
7. complete one real Luna/Sol/checkpoint cycle
8. turn generic friction into installer/doctor requirements
9. implement the minimum install + install-doctor tranche
10. repeat Memoria deployment using the new commands
11. freeze broad Agent expansion
12. return primary development effort to Atlas Core
```

---

## 11. Guiding end state

For a new machine:

```bash
atlas-agent install
atlas-agent install-doctor
```

For a new project:

```bash
cd project
# establish/review project policy
atlas-agent init
atlas-agent doctor
```

For normal work:

```bash
atlas-agent ingest
atlas-agent dispatch
```

The operator should not need to understand:

```text
where the Codex fork was built
sealed memfd authority
current_exe stable-path mechanics
asset-set hash construction
annotated-tag dereference
Bubblewrap exec-server qualification
v0.1.1 debugging history
```

Those are maintainer concerns captured by release engineering and machine
diagnostics.

When this is true, Atlas Agent has achieved its immediate purpose:

```text
reliable infrastructure that fades into the background
while Atlas itself becomes the thing being developed and evaluated
```
