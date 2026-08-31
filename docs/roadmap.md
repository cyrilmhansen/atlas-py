# Atlas / Atlas Agent — Roadmap
Document version: **0.2**

This roadmap reflects the state reached after Atlas Agent v0.1.1 and the release/deployment qualification work performed around it. It is a prioritization document, not a catalogue of every possible Atlas feature.

> Atlas Agent exists to make Atlas development reliable. Once it is installable, diagnosable, and proven on an external project, further Agent sophistication must not displace Atlas Core work without concrete evidence that the infrastructure is blocking progress.

Immediate direction:
```text
finish minimal Linux installation → validate it outside Atlas → fix only generic friction → return primary effort to Atlas Core
```

---
## 1. Current planning boundary
Primary target for the next tranche:
```text
Linux · bash · x86_64 · Bubblewrap · qualified Atlas Codex fork
```
Other platforms remain future targets but must not delay the Linux golden path.

Planning horizons:
```text
NOW   machine installation product
NEXT  Memoria external-project validation
THEN  Atlas Core and external semantic use cases
LATER automation, portability, broader hardening, optional ergonomics
```

---
## 2. Baseline established by v0.1.1
Atlas Agent v0.1.1 qualified:
- exact Agent release + manifest;
- exact Atlas Codex source release;
- native Codex executable identified by SHA-256;
- versioned canonical Codex assets and compact prompts;
- atomic CODEX_HOME provisioning;
- runtime identity checks and sealed executable authority;
- stable runtime path compatible with Codex `current_exe()`;
- Bubblewrap + real Codex exec-server execution;
- zero-token helper qualification;
- authenticated Luna smoke;
- explicit release and deployment procedures.

The immediate problem is therefore no longer "can Atlas Agent run a qualified model?" but:
```text
can a user install and diagnose the qualified system without reconstructing release engineering by hand?
```

---
## 3. Durable planning principles
### 3.1 Keep identities separate
Independent dimensions are Agent source/tag/commit, Codex source/tag/commit, Codex executable bytes/SHA, canonical assets, prompt set, project policy, user authentication, project workflow journal, and Git publication state. Changing one must not silently imply changing another.

### 3.2 Agent release != Codex release
A new Agent release does not require a new Codex release when Codex source and binary bytes are unchanged.

### 3.3 Binary bytes are runtime authority
A path locates the executable; its SHA-256 identifies the qualified runtime. One exact qualified Codex binary may legitimately be shared by multiple independent Agent installations on the same machine.

### 3.4 Assets and auth are different state classes
Canonical assets are immutable release state; authentication is mutable user state. A CODEX_HOME may reference user auth after provisioning without adding the secret to the canonical asset set.

### 3.5 Machine and project lifecycles are different
Machine state: Agent release, qualified Codex binary, canonical CODEX_HOME, auth reference, Bubblewrap/runtime prerequisites.

Project state: `atlas-agent-policy.toml`, `.git/atlas-agent`, repository witness, prompts, reports, checkpoints.

### 3.6 `doctor` is not an installation diagnostic
`atlas-agent doctor` validates project workflow state. A separate installation diagnostic is required.

### 3.7 External projects are product tests
A second project reveals hidden assumptions prepared by Atlas's own development environment.

### 3.8 Atlas Agent must become boring
After installation and external-project validation, new Agent features require repeated evidence of need.

---
# NOW — minimum installable Atlas Agent

## P0.1 — Distribution of the qualified Codex runtime
**Priority: critical**

The largest virgin-machine gap is distribution of the exact native Codex executable recorded by `atlas-release.toml`. A local rebuild is not automatically the qualified binary, even from the same source commit.

Initial target: `x86_64-unknown-linux-gnu`.

Required properties:
- immutable published artifact;
- explicit Codex tag/commit association;
- SHA-256 in the Agent manifest;
- retrievable by the installer;
- no trust from filename/tag alone;
- no dependency on a maintainer checkout.

Do not make reproducible builds a prerequisite for this first step.

**Exit criterion:** a fresh Linux host can obtain and verify the exact binary required by a published Agent release without development working directories.

---
## P0.2 — `atlas-agent install`
**Priority: critical**

Turn the manual bootstrap from `docs/deploy-existing-project.md` into a supported machine-level command.

Responsibilities:
- resolve one Agent release and validate `atlas-release.toml`;
- select the supported host target;
- obtain/locate and SHA-verify the exact Codex executable;
- install a stable `atlas-agent` command;
- atomically provision canonical CODEX_HOME;
- verify asset/prompt identities;
- connect mutable user auth without copying secrets;
- verify host prerequisites;
- leave project repositories untouched.

Recommended layout:
```text
~/.local/share/atlas-agent/
├── releases/atlas-agent-vX.Y.Z/
└── codex-homes/vX.Y.Z/
```
The installer should be idempotent for a correct installation and reject unexplained inconsistent state rather than partially repairing it. It must never print, commit, release-hash, or copy credential contents into canonical assets.

**Exit criterion:** a supported Linux user installs one release without manual `PYTHONPATH`, asset copying, or source-tree archaeology.

---
## P0.3 — `atlas-agent install-doctor`
**Priority: critical**

The diagnostic must not depend on any project `.git/atlas-agent` journal.

### Level A — static identity
Check Agent release/manifest; Codex target/path/type/permissions/SHA; CODEX_HOME ownership/permissions; config/catalog/profile digests; asset/prompt set identities; auth link/readability; Bubblewrap and platform support.

### Level B — zero-token production probe
```text
qualified Codex → sealed runtime → stable path → Bubblewrap → exec-server → current_exe helper → codex-linux-sandbox → /bin/true → exit 0 → reap/cleanup
```
This should become a public diagnostic rather than remain pytest-only.

### Level C — optional authenticated smoke
```bash
atlas-agent install-doctor --authenticated
```
It may consume tokens and should prove host-side Codex authentication plus one minimal model turn. Report independently: installation identity, zero-token runtime, authenticated service.

**Exit criterion:** a user can determine whether the machine is ready without initializing a project or reading the release procedure.

---
## P0.4 — Version and installation identity
**Priority: high, small scope**

Provide a stable human + JSON surface such as:
```bash
atlas-agent --version
atlas-agent install-info
```
It should expose Agent tag/version/commit, asset version, Codex tag/commit/target/path/SHA, CODEX_HOME, asset/prompt SHA, Bubblewrap backend/version.

**Exit criterion:** a bug report can state the effective runtime identity without shell archaeology.

---
# NEXT — validate deployment on Memoria

## P1 — Two legitimate Memoria objectives
Memoria is the first deliberate second-project deployment. Two goals are valid but must not be confused.

### Objective A — use Atlas with Memoria immediately
Reuse the already-qualified v0.1.1 machine installation and create only Memoria project state.

Reuse: existing Agent v0.1.1 installation, existing v0.1.1 CODEX_HOME, exact qualified Codex binary, user auth source, Bubblewrap host installation.

Create independently: Memoria policy, `.git/atlas-agent`, witness, prompts, reports, checkpoints.

This is the fastest route to using Atlas Agent, but it does not validate the deployment guide from a fresh Agent/CODEX_HOME state.

---
## P1.B — Preferred current experiment: isolated Memoria installation prefix
To validate the v0.1.1 deployment procedure itself, create an independent Agent checkout and CODEX_HOME.

Use:
```bash
export ATLAS_BASE="$HOME/.local/share/atlas-agent-memoria-test"
export ATLAS_AGENT_TAG="atlas-agent-v0.1.1"
export ATLAS_AGENT_SRC="$ATLAS_BASE/releases/$ATLAS_AGENT_TAG"
export ATLAS_CODEX_HOME="$ATLAS_BASE/codex-homes/v0.1.1"
export ATLAS_CODEX_EXECUTABLE="$HOME/luna/codex-atlas/codex-rs/target/release/codex"
```
Expected tree:
```text
~/.local/share/atlas-agent-memoria-test/
├── releases/atlas-agent-v0.1.1/
└── codex-homes/v0.1.1/
```

### Must be independent
Do not reuse the existing Agent v0.1.1 checkout, existing Atlas v0.1.1 CODEX_HOME, Atlas workflow journal, Atlas project policy as Memoria state, or Atlas prompts/reports/checkpoints.

Perform fresh:
```text
Agent checkout → tag/commit verification → manifest reading → v0.1.1 asset validation → fresh CODEX_HOME → fresh auth symlink → executor-info → Bubblewrap/helper qualification → Memoria policy → Memoria init/doctor → first execution
```

### May intentionally be shared
Reuse the exact qualified Codex binary. Its identity is the validated SHA-256 of its bytes, not ownership by one installation prefix. Copying another ~1.3 GB identical file adds little deployment evidence.

Reuse the user auth source, normally `~/.codex/auth.json`; each CODEX_HOME gets its own symlink. Bubblewrap and host libraries are shared prerequisites.

### What this experiment proves
Success shows that on this already-qualified machine the guide is sufficient for a fresh Agent checkout, fresh canonical CODEX_HOME, fresh auth wiring, and fresh project initialization.

It does **not** prove virgin-machine Codex artifact download or first-time auth setup; those claims belong to P0.1/P0.2.

---
## P1.1 — Memoria project initialization
Before `atlas-agent init`:
- inspect Memoria Git state and existing modified/untracked files;
- read repository instructions;
- establish/review Memoria `atlas-agent-policy.toml`;
- verify a supported real `.git/` directory;
- verify no conflicting `.codex/config.toml`;
- choose a deliberate stable repository boundary.

Then require:
```text
doctor: OK · state: MATCH · repository witness: MATCH · intended executor resolved
```

**Exit criterion:** Memoria has its own clean workflow history with no imported Atlas journal.

---
## P1.2 — First real Memoria task
Use a bounded real task, not only a synthetic smoke.

Preferred cycle:
```text
implementation/Luna → project tests → patch_review/Sol → correction if needed → review → manual checkpoint
```
Record friction separately as machine installation, install diagnostic, project initialization, repository topology/witness, policy/defaults, prompt ergonomics, runtime/result diagnostics, checkpoint workflow, documentation, or Memoria-specific behavior.

Do not change Atlas Agent for a Memoria-specific inconvenience unless it plausibly generalizes.

**Exit criterion:** one useful Memoria change completes the full implementation/review/checkpoint cycle under a fresh workflow.

---
## P1.3 — Bounded stabilization after Memoria
Fix only generic problems demonstrated by the deployment: error messages, installer/doctor checks, safe defaults, documentation, bootstrap ergonomics, or common repository assumptions. Avoid broad redesign.

**Exit criterion:** repeating the Memoria deployment no longer requires undocumented maintainer knowledge.

---
# THEN — narrow remaining Agent debt

## P2 — Execution health versus task success
**Priority: medium-high, narrow scope**

Keep separate:
```text
process exit 0 · Atlas lifecycle completed · tool calls succeeded · requested task succeeded · review accepted · checkpoint finalized
```
Introduce the smallest structured result contract needed to distinguish `execution_health`, observed tool failure, reported task outcome, and review/checkpoint status.

Do not build a general orchestrator. Do not make model self-reporting the authority for process health.

**Exit criterion:** operator status clearly explains infrastructure completion versus project-task acceptance.

---
## P2.1 — Freeze broad Agent feature expansion
After P0/P1/P2, Agent work should normally require repeated external-project friction, a security-policy enforcement gap, release/install reliability defect, blocking Atlas Core limitation, or material observability defect. Convenience alone is insufficient.

---
# THEN — return priority to Atlas Core

## P3 — Re-center on Atlas
Atlas is not an agent orchestrator. Its conceptual stack remains:
```text
applications/intent → semantic specification → Atlas Semantic Core → qualified component catalogue → selection/synthesis/composition → materialized IR → validation/lowering → backends
```
Agent infrastructure must fade into the development background.

---
## P3.1 — External corpora and component qualification
**Priority: first major Core direction after Agent stabilization**

Use external technical corpora and reusable computational components to pressure the semantic model around identity, contracts, pre/postconditions, effects, algebraic properties, precision/error, determinism, memory/cost, alternative implementations, applicability, provenance/evidence, and versioning.

Core V1 is already substantial enough that real material should drive the next semantic extensions.

**Exit criterion:** several independent external component families can be admitted, qualified, queried, and compared without domain-specific branches.

---
## P3.2 — Semantic candidate search/discovery
**Priority: high**

Given a declared intention/problem, find candidate realizations from qualified stored components. Do not conflate identity, semantic equivalence, similarity, applicability, admissibility, and optimality. Discovery should explain why candidates were found, included, or excluded.

**Exit criterion:** a real external query produces multiple qualified candidates and structured discovery/filtering evidence.

---
## P3.3 — Selection and composition from real components
**Priority: high**

Use real cases with alternative realizations, shared resources/preprocessing, context-dependent costs, and explicit applicability constraints. Prefer the smallest decision machinery justified by observed cases; do not implement every solver backend in advance.

**Exit criterion:** Atlas selects or composes a non-trivial real solution reproducibly from persisted semantic evidence.

---
## P3.4 — Black-box Core V1 conformance
**Priority: high once external consumers appear**

Create a small stable façade independent of SQLite/classes. Initial focus: nominal identity, value validation, order/uniqueness, participant-scoped properties, multivalued relations, TRUE/FALSE/UNKNOWN, negative assertions, provenance/dependencies, snapshots/stale, grounding completeness, selection correctness, restart/reproduction.

**Exit criterion:** Core V1 semantics can be tested through a public surface independent of storage implementation.

---
## P3.5 — Materialization only when semantically motivated
Do not prioritize MIR, RISC-V, WASM, GPU lowering, or VM backends merely because they are attractive engineering projects. They should demonstrate an already meaningful Atlas semantic decision.

---
# LATER

## P4 — Selective release automation
Automate deterministic and repeatedly expensive work: manifest/asset/prompt validation, test bundles, binary identity capture, zero-token qualification, release-state audit, tag/remote verification, artifact metadata. Keep human gates around release scope, independent/security review disposition, authenticated smoke interpretation, and publication.

## P5 — Targeted security enforcement review
Audit concrete paths where external configuration might enlarge authority: project Codex config/rules, hooks/MCP/tool surfaces, environment inheritance, credentials, network, filesystem grants, repo metadata write authority, runtime substitution. Do not build a general security framework; fix documented policy/enforcement mismatches.

## P6 — Evidence-driven operator ergonomics
After Memoria evidence, consider project bootstrap, policy template installation, prompt helpers, clearer status/remediation, installation/project path display, workflow-history navigation. Do not hide authority decisions merely to reduce command count.

## P7 — Broader Linux targets/topologies
Later candidates: Linux ARM64, linked worktrees, other repository layouts, containers, additional Bubblewrap environments. Each requires qualification of the complete Atlas boundary. Linked-worktree support needs an explicit Git-metadata sandbox design, not a weakened topology check.

## P8 — Other operating systems
macOS, Windows, and alternate isolation backends are deferred until the Linux golden path is stable and Atlas Core work is again primary. Codex portability alone does not establish Atlas boundary portability.

## P9 — Broader Atlas semantics under demonstrated need
Candidate directions include quantification/intervals, rich state transitions, temporal planning/lifetimes, reactive truth maintenance, quantitative uncertainty, CP-SAT/SMT/MILP, multiobjective decisions, Semantic Recovery, code materialization/validation, semantic equivalence, distributed stores, and concurrent update policies. These are not a sequential backlog; promote one only when real use cases or experiments justify it.

---
## 4. Suggested near-term release sequence
### v0.1.1 — completed baseline
```text
qualified runtime · versioned assets/prompts · stable Bubblewrap helper execution · release manifest/procedure · manual Linux deployment
```

### Next Agent tranche
Likely scope:
```text
qualified Codex artifact distribution · atlas-agent install · atlas-agent install-doctor · version/install-info · Memoria-derived generic fixes
```
`v0.1.2` is plausible; `v0.2.0` is also reasonable if installation introduces sufficiently large product semantics. Version should follow actual scope.

After this tranche, do not plan another large Agent release by default. Return priority to external corpora, component qualification, discovery, selection/composition, and Core V1 conformance.

---
## 5. Stopping criterion for Atlas Agent expansion
Atlas Agent is sufficiently finished for the current phase when:
```text
Linux x86_64 release installs without dev-checkout knowledge
Codex artifact retrieval/SHA verification automated
CODEX_HOME provisioning automated
auth connected without secret copying
install-doctor static + zero-token checks
authenticated smoke optional and working
project init/doctor separate from installation diagnosis
Memoria real implementation/review/checkpoint cycle complete
no undocumented Atlas-development state required
execution health versus task outcome understandable
```
This is a stopping rule, not a permanent feature-completeness claim.

---
## 6. Successful Memoria procedure-validation experiment
Preferred path: isolated installation prefix.

Success requires:
```text
fresh v0.1.1 Agent checkout under atlas-agent-memoria-test
clean tag/commit validation
fresh v0.1.1 CODEX_HOME
canonical asset provisioning
fresh auth symlink to existing user auth
shared Codex binary matches release SHA
executor-info resolves intended runtime
Bubblewrap/helper execution succeeds
Memoria policy exists before init
new Memoria workflow journal
doctor coherent
first real Luna task
independent Sol review
checkpoint without imported Atlas history
```
Any undocumented step is deployment friction.

The experiment intentionally does not prove virgin-machine Codex download, first-time authentication setup, Linux ARM64, macOS/Windows, linked worktrees, reproducible Codex builds, multi-user installation, or container distribution.

---
## 7. Shared versus duplicated state on one machine
Normal steady state should share the installed Agent release when the version is the same, exact qualified Codex executable, user auth source, Bubblewrap, and host runtime.

Version separately by release: canonical CODEX_HOME, release assets/prompts, manifest.

Always isolate by project: policy, `.git/atlas-agent`, witness, prompts/reports/checkpoints, project-specific allowed-untracked configuration.

A deployment test may deliberately duplicate Agent checkout and CODEX_HOME. That duplication is test instrumentation, not the recommended steady-state layout.

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
If all answers are no, defer it unless exceptionally small and maintenance-reducing.

Avoid five traps: hardening indefinitely before use; growing an orchestrator; automating every release gate too early; generalizing semantics from imagined domains; treating more execution backends as proof of semantic value.

---
## 9. Current priority summary
```text
P0.1 qualified Codex artifact distribution
P0.2 atlas-agent install
P0.3 atlas-agent install-doctor
P0.4 version/install identity reporting
P1   isolated-prefix Memoria deployment
P1.1 Memoria initialization
P1.2 real implementation → review → checkpoint
P1.3 bounded generic stabilization
P2   execution-health versus task-success contract
P2.1 freeze broad Agent expansion
P3.1 external corpora/component qualification
P3.2 semantic candidate discovery
P3.3 real selection/composition
P3.4 black-box Core V1 conformance
P3.5 materialization when semantically motivated
P4   selective release automation
P5   targeted security enforcement review
P6   evidence-driven ergonomics
P7   broader Linux targets/topologies
P8   other OS isolation backends
P9   broader Atlas semantics under demonstrated need
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
New machine:
```bash
atlas-agent install
atlas-agent install-doctor
```
New project:
```bash
cd project
# establish/review project policy
atlas-agent init
atlas-agent doctor
```
Normal work:
```bash
atlas-agent ingest
atlas-agent dispatch
```
The operator should not need to understand where Codex was built, sealed memfd authority, stable-path `current_exe()` mechanics, asset-set hashes, annotated-tag dereference, Bubblewrap exec-server qualification, or v0.1.1 debugging history. Those are maintainer concerns captured by release engineering and machine diagnostics.

When this is true, Atlas Agent has achieved its immediate purpose:
```text
reliable infrastructure that fades into the background while Atlas itself becomes the thing being developed and evaluated
```
