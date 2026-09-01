# Atlas / Atlas Agent — Roadmap
Document version: **0.3**

This roadmap reflects the state reached after Atlas Agent v0.1.1 and the first long-running real workflow on Memoria, now extending across roughly forty generations.

It is a prioritization document, not a catalogue of every possible Atlas feature.

> Atlas Agent exists to make Atlas development reliable. Once it is installable, diagnosable, and proven on external projects, further Agent sophistication must not displace Atlas Core work without concrete evidence that the infrastructure is blocking progress.

The current direction is:

```text
fix real correctness/liveness defects revealed by Memoria
→ finish minimal Linux installation and diagnosis
→ remove repeated operator workarounds
→ stabilize qualified prompt/project composition
→ freeze broad Agent expansion
→ return primary effort to Atlas Core
```

---

## 1. Current planning boundary

Primary platform for the next tranche:

```text
OS            Linux
shell         bash first; fish support where activation/export is relevant
architecture  x86_64
sandbox       Bubblewrap
controller    qualified Atlas Codex fork
```

Other platforms remain future targets and must not delay the Linux golden path.

Planning horizons:

```text
NOW    correctness, liveness, sandbox capability, installability
NEXT   qualified project/role contracts and bounded operational ergonomics
THEN   freeze broad Agent expansion and return to Atlas Core
LATER  release automation, portability, broader hardening, optional UX
```

---

## 2. Baseline established by v0.1.1

Atlas Agent v0.1.1 qualified:

- exact Agent release and release manifest;
- exact Atlas Codex source release;
- native Codex executable identified by SHA-256;
- versioned canonical Codex assets;
- versioned compact prompts;
- atomic CODEX_HOME provisioning;
- runtime identity checks and sealed executable authority;
- stable runtime path compatible with Codex `current_exe()`;
- Bubblewrap execution through the real Codex exec-server;
- zero-token helper qualification;
- authenticated Luna smoke;
- explicit release procedure;
- explicit Linux deployment procedure.

The v0.1.1 release answered the question:

```text
can Atlas Agent execute a qualified model through its intended runtime boundary?
```

The Memoria workflow answered a different and more useful question:

```text
what breaks, drifts, becomes repetitive, or requires operator intervention
when Atlas Agent is used continuously on a real project for many generations?
```

That experience now drives the immediate roadmap.

---

## 3. Durable planning principles

### 3.1 Keep identities separate

Independent dimensions include:

```text
Atlas Agent source/tag/commit
Atlas Codex source/tag/commit
Codex executable bytes/SHA
canonical Codex assets
prompt contract set
project prompt overlays
project authority set
project policy
user authentication
project workflow journal
Git publication state
```

Changing one must not silently imply changing another.

### 3.2 Agent release does not imply Codex release

A new Atlas Agent release does not require a new Codex release when Codex source and qualified binary bytes are unchanged.

### 3.3 Binary bytes are runtime authority

A path locates the Codex executable. Its SHA-256 identifies the qualified runtime.

Therefore one exact qualified Codex binary may legitimately be shared by multiple independent Atlas Agent installations on the same machine.

### 3.4 Qualified immutable inputs must not mutate themselves

A file whose digest participates in execution authority must not be modified by the execution it authorizes.

This now applies directly to the Codex configuration drift observed by Memoria.

### 3.5 Machine and project lifecycles are different

Machine-level state includes:

```text
Agent release
qualified Codex executable
canonical CODEX_HOME
user auth reference
Bubblewrap/runtime prerequisites
qualified toolchain/scratch capabilities
```

Project-level state includes:

```text
atlas-agent-policy.toml
project prompt overlays
project authority declarations
.git/atlas-agent journal/spool
repository witness
prompts/reports/checkpoints
```

### 3.6 `doctor` is not an installation diagnostic

`atlas-agent doctor` validates project workflow state.

A separate `install-doctor` must validate machine installation state.

### 3.7 Expected policy boundaries should resolve automatically

A safe and expected policy fallback is not an execution failure.

Examples:

```text
reuse target stale      → fresh
reuse target incompatible → fresh
hot-hop limit reached   → fresh
```

True provenance or security contradictions still fail closed.

### 3.8 Journal-native recovery beats manual surgery

The journal remains authoritative.

If an operator needs to cancel, requeue, or invalidate an accepted generation, that operation must be represented durably in the lifecycle rather than by deleting or editing JSONL records.

### 3.9 Atlas owns runtime/orchestration; role contracts own engineering behavior

Atlas Agent owns:

```text
toolchain/scratch capability
sandboxing
session resolution
timeouts
config isolation
activation/runtime provenance
```

Generic implementation/review contracts own:

```text
truthful validation claims
failure classification
invariant preservation
transaction reasoning
scope discipline
closeout consistency
```

Project overlays own stable project-specific working guidance.

Project authority remains a separate normative context.

### 3.10 Execution lifecycle and task outcome are different state

Atlas may say:

```text
execution status: COMPLETED
```

while a qualified project convention may truthfully say:

```text
task outcome: INCOMPLETE
```

There is no contradiction.

Atlas owns the lifecycle. Projects/roles may define semantic outcome conventions.

### 3.11 Atlas Agent must become boring

After the current hardening/installability tranche, new Agent features require repeated evidence of need.

The goal is reliable infrastructure that fades into the background.

---

# NOW — P0 correctness, liveness, and self-consistency

P0 means:

```text
without this, Atlas can wedge the workflow,
self-invalidate qualified state,
misrepresent a critical runtime capability,
or prevent an implementation agent from validating its own work.
```

## P0.1 — Complete manual checkpoint correctness — PR #1

The first real Memoria checkpoint exposed two lifecycle/provenance defects after the Git checkpoint itself had already succeeded:

- v2 network provenance was missing from the manual checkpoint transition;
- the validator incorrectly required an executor owner for a manual checkpoint.

Manual checkpoints must remain journal-valid without fabricating model execution metadata.

**Exit criterion:** a v2 manual checkpoint can commit, complete, replay, rebuild, and pass doctor with correct network provenance and no fabricated execution owner.

---

## P0.2 — Isolate immutable Codex config from mutable trust state — issue #6

This is promoted from P1 to P0.

A workspace-write Codex run can currently add project trust state to the qualified `config.toml`, causing the next Atlas execution to fail its own `CODEX_CONFIG_DIGEST_MISMATCH` check.

The observed workaround — restoring canonical config after successful generations — must disappear.

Required invariant:

```text
execution-time trust persistence cannot mutate a file
whose exact digest is part of launch authority
```

Possible designs include an execution-local derived config, a separate writable trust-state location, or a disposable runtime copy generated from immutable assets.

**Exit criterion:** repeated workspace-write generations cannot mutate the canonical hash-bound config and require no manual restoration.

---

## P0.3 — Automatic safe reuse fallback — issue #2a

Split issue #2 into an essential P0 part and a later optimization part.

The P0 requirement is:

```text
reuse requested
→ validate target/state/policy/hop/generation compatibility
→ if compatible: reuse
→ otherwise: resolve to fresh before RUN_STARTED
```

Normal reuse is a preference, not a promise that may wedge the workflow.

Durable/presentation state should distinguish:

```text
session requested: reuse
session resolved: fresh
fallback reason: max_hot_reuse_hops
```

Strict same-thread behavior, if needed, should be explicit rather than the default.

P0 includes:

- stale target fallback;
- incompatible policy fallback;
- hot-hop limit fallback;
- generation-gap fallback;
- precise mismatch/fallback diagnostics;
- requested vs resolved session provenance.

P0 does **not** require context-percentage rollover yet.

**Exit criterion:** expected reuse-policy boundaries never leave an `ACCEPTED` generation blocking dispatch.

---

## P0.4 — Cancel/requeue/invalidate unstarted accepted generations — issue #4

Even after #2a, Atlas needs a generic durable escape hatch for an accepted generation that never reached `RUN_STARTED`.

Examples:

```text
operator changes intent
pre-start capability check fails
policy resolution becomes impossible
prompt was accepted but should not execute
```

The lifecycle operation must:

- refuse after any durable `RUN_STARTED`;
- preserve the original prompt hash and history;
- record the reason;
- remain deterministic and crash-recoverable;
- unblock later dispatch;
- be understood by replay/rebuild/doctor.

**Exit criterion:** no manual journal suffix deletion or JSONL surgery is required to abandon/requeue an unstarted accepted generation.

---

## P0.5 — Truthful writable scratch semantics — issue #13

This is promoted to the P0/P1 boundary because Memoria tests were genuinely blocked by a sandbox capability that dispatch presented inaccurately.

Atlas currently advertises:

```text
tmp memory · var/tmp disk
```

while `/var/tmp` is observed read-only inside the sandbox.

Atlas must either make `/var/tmp` writable disk-backed scratch or stop presenting it as such and expose another canonical writable disk location.

Required outcome:

```text
/tmp       explicit writable tmpfs
scratch    explicit writable disk-backed location
TMPDIR     deliberate effective value
presentation == actual mount/write semantics
```

**Exit criterion:** agents/tests can discover and use canonical writable temporary locations without guessing host paths.

---

## P0.6 — Qualified development toolchains and caches — issue #5

An implementation profile that can edit code but cannot compile/test it is structurally degraded.

Memoria demonstrated this with Rust toolchains installed under user HOME and hidden by the sandbox.

Atlas should expose development tooling as explicit qualified capabilities rather than mounting arbitrary HOME state.

The abstraction should cover at least:

```text
Rust
Python
Node
Go
JVM
C/C++
```

The design should support:

- qualified read-only executable/toolchain paths;
- version/provenance reporting;
- preflight of required commands;
- safe writable caches where necessary;
- no credential-bearing user HOME exposure.

Issues #5 and #13 should remain separate for tracking, but implementation may share one sandbox-capability subsystem.

**Exit criterion:** implementation agents can build/test with declared qualified tooling and fail early with a capability diagnostic when required tooling is unavailable.

---

# NOW — P0 installability

The Memoria deployment succeeded using an isolated prefix, but it still relied on existing machine knowledge and an already-qualified Codex executable.

The next release should close that product gap rather than leave installation as maintainer archaeology.

## P0.7 — Distribution of the qualified Codex runtime

The release manifest can identify the required Codex binary, but a virgin machine still needs a supported way to obtain the exact qualified bytes.

Initial target:

```text
x86_64-unknown-linux-gnu
```

Required properties:

- immutable published artifact;
- explicit Codex tag/commit association;
- SHA-256 in `atlas-release.toml`;
- installer-retrievable;
- no trust based only on filename/tag;
- no dependency on a maintainer development checkout.

Do not require fully reproducible builds before solving artifact distribution.

**Exit criterion:** a fresh Linux host can obtain and SHA-verify the exact runtime required by a published Agent release.

---

## P0.8 — `atlas-agent install`

Turn the manual bootstrap from `docs/deploy-existing-project.md` into a supported machine-level operation.

Responsibilities:

- resolve one Agent release;
- validate `atlas-release.toml`;
- select supported host target;
- obtain/locate exact Codex executable;
- verify executable SHA and permissions;
- install a stable `atlas-agent` invocation;
- atomically provision canonical CODEX_HOME;
- verify assets and prompt contracts;
- connect mutable user auth without copying secrets;
- verify host prerequisites;
- leave project repositories untouched.

Recommended layout:

```text
~/.local/share/atlas-agent/
├── releases/atlas-agent-vX.Y.Z/
└── codex-homes/vX.Y.Z/
```

Installation should be idempotent for correct state and refuse unexplained inconsistent destinations rather than partially repairing them.

**Exit criterion:** installing a published release requires no manual PYTHONPATH, asset copying, source-tree archaeology, or hand-written activation script.

---

## P0.9 — `atlas-agent install-doctor`

Installation diagnosis must not depend on any project workflow journal.

### Level A — static identity

Check at minimum:

```text
Agent release/tag/commit
release manifest
Codex target/path/type/permissions/SHA
CODEX_HOME ownership/permissions
config/catalog/profile/prompt identities
auth link/readability
Bubblewrap/platform support
qualified toolchain/scratch capabilities where declared
```

### Level B — zero-token production probe

```text
qualified Codex
→ sealed runtime
→ stable runtime path
→ Bubblewrap
→ exec-server
→ current_exe helper
→ codex-linux-sandbox
→ /bin/true
→ exit 0
→ confirmed reap/cleanup
```

### Level C — optional authenticated smoke

```bash
atlas-agent install-doctor --authenticated
```

Report the three levels separately rather than collapsing them into one boolean.

**Exit criterion:** a user can determine machine readiness without initializing a project or reading release-engineering documentation.

---

## P0.10 — Reproducible launcher/activation and install identity — issue #9

This is promoted from P2 to P0/P1 because reproducible activation is part of installation correctness, not merely convenience.

Closing a terminal must not lose or silently change:

```text
Agent release
CODEX_HOME
Codex executable
qualified override/hotfix state
```

The installer may provide a versioned launcher, an activation mechanism, or a canonical environment exporter.

Candidate surfaces:

```bash
atlas-agent --version
atlas-agent install-info
atlas-agent env --shell bash
atlas-agent env --shell fish
atlas-agent activate <installation>
```

Human and JSON output should expose effective Agent/Codex/assets/runtime identities.

**Exit criterion:** reopening a shell does not require reconstructing Atlas environment variables by hand, and a bug report can state the effective installation identity directly.

---

# NEXT — P1 execution reliability and project quality

P1 means:

```text
without this, long real-project use remains repetitive,
fragile, misleading, or unnecessarily expensive in operator attention,
but the core workflow can still make progress without journal surgery.
```

## P1.1 — Qualified profile timeouts — issue #8

The current universal ~300-second practical default is too short for normal Luna implementation and especially Sol high-reasoning review.

Timeout belongs in qualified execution policy.

Profiles should define sensible defaults with explicit permitted CLI override.

Effective timeout must appear in provenance/presentation.

**Exit criterion:** healthy long implementation/review generations are not interrupted merely because the operator forgot `--timeout-seconds 1800`.

---

## P1.2 — Explicit network semantics and practical defaults — issue #10

Promote this from P2 to P1.

Memoria showed that `network_access = false` was interpreted as the safe normal mode, but this prevented ordinary dependency/tool access. The intended normal implementation mode was network enabled while still restricted by Codex policy.

Atlas should explicitly distinguish:

```text
network requested
network resolved
network enforcement
web search state
```

Example:

```text
network requested: enabled
network resolved: enabled
network enforcement: Codex restricted
web search: live/disabled
```

Implementation defaults should be deliberate and documented; review/audit may remain more restrictive.

**Exit criterion:** operators and agents can distinguish “enabled but restricted” from unrestricted network and from fully disabled network, and reuse compatibility compares the resolved capability correctly.

---

## P1.3 — Generic Luna implementation-agent contract — issue #14

After many generations, stable engineering behavior should not be recopied into each implementation prompt.

The generic contract should remain language/project agnostic and include:

1. validate fixes with the relevant available oracle;
2. report reasoned-but-unverified changes honestly;
3. classify groups of failures before patching;
4. distinguish product/test/deferred/environment failures;
5. preserve accepted invariants even when tests conflict;
6. reason explicitly about durability/transaction boundaries when relevant;
7. preserve unrelated dirty state;
8. understand what validation commands actually cover;
9. stop at the architectural boundary of the requested slice;
10. inspect the accumulated diff on closeout before independent review.

Do not encode Atlas runtime defects as model obligations.

**Exit criterion:** implementation profiles inherit a stable qualified generic contract and generation prompts can remain focused on objective, scope, exclusions, and exit criteria.

---

## P1.4 — Qualified project prompt overlays — issue #15a

Split issue #15 into an essential composition/provenance part and a later structured outcome part.

The P1 composition model is:

```text
1. generic Atlas role contract
2. project common overlay
3. project role overlay
4. separately identified project authority set
5. bounded generation prompt
```

These layers must compose deterministically.

Qualification/provenance should record immutable identities for:

```text
generic role contract
project common overlay
project role overlay
resolved authority set
generation prompt
```

Overlay/authority identity must participate in session compatibility. A changed project contract should normally cause an automatic fresh rollover under #2a rather than remain hidden behind hot reuse.

Project working instructions and project authority must remain separate concepts.

**Exit criterion:** stable project guidance is no longer copied into every generation prompt, while the exact effective prompt composition remains reproducible and auditable.

---

## P1.5 — Compact status/history — issue #3

After roughly forty generations, unbounded `status` output is no longer hypothetical UX debt.

Default status should be bounded and show the current operational state first.

Suggested model:

```text
status            latest + recent bounded history
status --last N   explicit bounded history
status --all      complete current behavior
history           dedicated complete history
```

Earlier generations may be summarized statistically.

**Exit criterion:** status output remains useful independently of generation count while complete history remains explicitly accessible.

---

## P1.6 — Bounded stabilization from repeated Memoria workarounds

Generic repeated workarounds should disappear before another major Agent expansion.

Known examples now include:

```text
manual journal repair
manual config restoration
manual timeout flags
system-wide toolchain installation solely for sandbox visibility
hand-written shell activation
manual reuse rollover decisions
unbounded status history
scratch-path guessing
repeated generic Luna prompt boilerplate
repeated project-role prompt boilerplate
```

Not every Memoria-specific inconvenience deserves an Atlas change.

A problem should normally generalize to Agent infrastructure, project reproducibility, or cross-project engineering behavior.

---

# THEN — P2 observability and advanced policy

P2 means:

```text
the normal workflow is already autonomous and reproducible;
these items improve observation, optimization, or richer semantics.
```

## P2.1 — Stream concise local tool-call progress — issue #7

Move this below correctness/installability/project-contract work.

It is valuable but does not affect execution correctness.

Dispatch should expose bounded locally-derived events such as:

```text
exec cargo check
exec exit 101
exec cargo test
apply_patch ...
```

without requiring model narration or spending output tokens.

Detailed stdout/stderr remain separate logs.

**Exit criterion:** long dispatches expose meaningful activity and command failure promptly without output spam or extra model messages.

---

## P2.2 — Usage/cache/reasoning/cost accounting — issue #11

Memoria demonstrated that raw token totals are misleading when cached input reaches very high percentages.

Expose per-generation and aggregate:

```text
input tokens
cached input
uncached input
output tokens
reasoning tokens when separately observed
wall-clock time
model/profile
fresh/reuse lineage
optional API-equivalent cost
```

Pricing data must be versioned and clearly separated from raw telemetry.

Reasoning/output must not be double-counted.

**Exit criterion:** fresh/reuse and Luna/Sol economics can be evaluated from stored telemetry rather than manual dispatch notes.

---

## P2.3 — Proactive context-headroom rollover — issue #2b

This is the non-blocking optimization split from #2.

Once context usage is observable reliably, policy may proactively resolve a requested reuse to fresh before hard exhaustion.

A threshold around 75% may be a useful experimental starting point, but it must be configurable and evidence-driven.

This feature must not block the simpler P0 stale/incompatible/hop/gap fallback.

**Exit criterion:** hot sessions can roll before hard context exhaustion using observable qualified policy rather than manual operator judgment.

---

## P2.4 — Structured project-defined task outcome — issue #15b / prior roadmap P2

Atlas execution lifecycle and semantic mission outcome must remain distinct.

Atlas should not impose one universal semantic vocabulary.

Project/role overlays may define conventions such as:

```text
implementation: COMPLETE / INCOMPLETE / BLOCKED
review: ACCEPTABLE_FOR_CHECKPOINT / NEEDS_REVISION / UNSOUND
audit: PASS / FINDINGS / INVALID
```

If Atlas stores/displays a task outcome structurally, it must retain the qualified convention identity that defines the value.

Without a declared convention, semantic completion may remain natural-language reporting.

**Exit criterion:** `execution=COMPLETED` and a project-defined non-success task outcome can coexist explicitly without Atlas inventing hidden semantics.

---

# THEN — freeze broad Agent expansion

After P0/P1 and the narrow P2 fundamentals, new Agent work should normally require one of:

```text
repeated external-project friction
security-policy enforcement gap
release/install reliability defect
blocking Atlas Core limitation
material observability defect
```

Convenience alone is not sufficient.

This is the stopping rule that prevents Atlas Agent from becoming the project.

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

Use external technical corpora and reusable computational components to pressure the semantic model around:

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

Core V1 is already substantial enough that real material should drive the next semantic extensions.

**Exit criterion:** several independent external component families can be admitted, qualified, queried, and compared without domain-specific branches.

---

## P3.2 — Semantic candidate search/discovery

Given a declared intention/problem, find candidate realizations from qualified stored components.

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

**Exit criterion:** a real external query produces multiple qualified candidates and structured discovery/filtering evidence.

---

## P3.3 — Selection and composition from real components

Use real cases with alternative realizations, shared resources/preprocessing, context-dependent costs, and explicit applicability constraints.

Prefer the smallest decision machinery justified by observed cases.

Do not implement every solver backend in advance.

**Exit criterion:** Atlas selects or composes a non-trivial real solution reproducibly from persisted semantic evidence.

---

## P3.4 — Black-box Core V1 conformance

Create a small stable façade independent of SQLite/internal classes.

Initial focus:

```text
nominal identity
value validation
order/uniqueness semantics
participant-scoped property resolution
multivalued relations
TRUE/FALSE/UNKNOWN
negative assertion distinction
provenance/dependencies
snapshots/stale semantics
grounding completeness
selection correctness
restart/reproduction
```

**Exit criterion:** Core V1 semantics can be tested through a public surface independent of storage implementation.

---

## P3.5 — Materialization only when semantically motivated

Do not prioritize MIR, RISC-V, WASM, GPU lowering, or VM backends merely because they are attractive engineering projects.

They should demonstrate an already meaningful Atlas semantic decision.

---

# LATER

## P4 — Selective release automation

Automate deterministic and repeatedly expensive work:

```text
manifest/asset/prompt validation
test bundles
binary identity capture
zero-token qualification
release-state audit
tag/remote verification
artifact metadata
```

Keep human gates around release scope, independent/security review disposition, authenticated smoke interpretation, and publication.

---

## P5 — Targeted security enforcement review

Audit concrete paths where external configuration might enlarge authority:

```text
project Codex config/rules
hooks/MCP/tool surfaces
environment inheritance
credentials
network enforcement
filesystem grants
repo metadata write authority
runtime substitution
```

Do not build a general security framework. Fix documented policy/enforcement mismatches.

---

## P6 — Evidence-driven operator ergonomics

After the Memoria-driven work above, consider only evidence-backed additions such as project bootstrap helpers, policy templates, prompt creation helpers, clearer remediation text, and workflow-history navigation.

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

Linked-worktree support needs an explicit Git-metadata sandbox design, not a weakened topology check.

---

## P8 — Other operating systems

macOS, Windows, and alternate isolation backends are deferred until the Linux golden path is stable and Atlas Core work is again primary.

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

### Atlas Agent v0.1.1 — completed baseline

```text
qualified runtime
versioned assets/prompts
stable Bubblewrap helper execution
release manifest/procedure
manual Linux deployment path
```

### Atlas Agent v0.1.2 — target: first long-workflow-usable Linux release

The preferred scope is broader than the original hardening tracker because Memoria revealed that correctness and installability are tightly coupled in actual use.

### Release blockers / correctness

```text
PR #1 checkpoint correctness
#6 immutable config vs mutable trust state
#2a automatic stale/incompatible/hop/gap reuse fallback
#4 cancel/requeue/invalidate unstarted ACCEPTED generation
#13 truthful scratch capability
#5 qualified development toolchains/caches
```

### Execution reliability / project quality

```text
#8 qualified timeout defaults
#10 explicit/practical network semantics
#14 generic implementation-agent contract
#15a qualified project prompt overlays
#3 compact status/history if low-risk
```

### Installability

```text
qualified Codex artifact distribution
atlas-agent install
atlas-agent install-doctor
#9 reproducible launcher/activation
version/install-info
```

### Explicitly deferrable beyond v0.1.2

```text
#7 richer local progress streaming
#11 cost/accounting UI
#2b context-percentage rollover
#15b structured project-defined task outcome
```

If one of these deferred items proves extremely small and low-risk, it may land, but none should delay the release-blocking items above.

`v0.1.2` remains a plausible version number. If installer semantics or prompt/project composition become sufficiently large to justify a stronger product boundary, `v0.2.0` remains reasonable. Version should follow actual scope rather than determine it in advance.

After this tranche, do not plan another large Agent release by default.

---

## 5. Stopping criterion for Atlas Agent expansion

Atlas Agent is sufficiently finished for the current phase when:

```text
long multi-generation workflows require no journal surgery
successful executions do not mutate qualified authority inputs
safe reuse boundaries resolve automatically
unstarted accepted generations can be cancelled/requeued durably
qualified toolchains and writable scratch are explicit
healthy long runs use profile timeout defaults
network semantics/defaults are unambiguous
stable generic/project prompt contracts avoid repeated boilerplate
Linux x86_64 release installs without dev-checkout knowledge
Codex artifact retrieval/SHA verification are automated
CODEX_HOME provisioning is automated
auth is connected without secret copying
install-doctor performs static + zero-token checks
optional authenticated smoke works
activation survives terminal restart reproducibly
project init/doctor remain separate from installation diagnosis
execution lifecycle and semantic task outcome are conceptually distinct
```

This is a stopping rule, not a permanent feature-completeness claim.

---

## 6. Memoria evidence and what it now proves

The isolated-prefix Memoria deployment has moved beyond a first smoke and into sustained use across roughly forty generations.

It has therefore provided evidence for:

```text
fresh Agent checkout under an isolated prefix
fresh canonical CODEX_HOME provisioning
shared exact Codex binary by SHA
fresh auth symlink
fresh project journal/witness
repeated Luna implementation
repeated Sol review
session reuse chains
manual checkpoints
long-running sandbox/toolchain behavior
real project test execution
operator recovery behavior
prompt-contract repetition and drift pressure
```

The experiment still does not prove:

```text
virgin-machine Codex artifact download
first-time authentication setup
Linux ARM64
macOS/Windows
linked worktrees
reproducible Codex builds
multi-user installation
container distribution
```

Those remain separate qualification claims.

---

## 7. Shared versus duplicated state on one machine

Normal steady state should share:

```text
installed Agent release when the same version is used
exact qualified Codex executable
user authentication source
Bubblewrap and host runtime
```

Version separately by release:

```text
canonical CODEX_HOME
release assets/prompts/contracts
release manifest
```

Always isolate by project:

```text
atlas-agent-policy.toml
project overlays/authority declarations
.git/atlas-agent journal
repository witness
prompts/reports/checkpoints
project-specific allowed-untracked configuration
```

A deployment test may deliberately duplicate Agent checkout and CODEX_HOME. That duplication is test instrumentation, not the recommended steady-state layout.

---

## 8. Priority decision rule

Use the following definitions consistently.

### P0

```text
Can wedge the workflow,
self-invalidate qualified state,
misrepresent a capability required for correctness,
prevent implementation validation,
or block reliable installation/recovery.
```

### P1

```text
Does not fundamentally block progress,
but makes long real-project operation fragile,
repetitive, misleading, or non-reproducible.
```

### P2

```text
Improves observability, optimization, or richer policy semantics
after the normal workflow is already autonomous and reproducible.
```

Before promoting new Agent work, ask:

```text
Does it block reliable installation?
Does it block external-project use?
Does it reveal an enforcement/self-consistency gap?
Does it require repeated operator workaround?
Does it prevent truthful validation?
Does it block Atlas Core work?
Has the problem appeared in sustained real use?
```

Avoid these traps:

- hardening indefinitely before use;
- growing Atlas Agent into an orchestrator;
- compensating for runtime defects with larger generation prompts;
- automating every release gate before repeated evidence;
- generalizing Atlas semantics from imagined domains;
- treating more execution backends as proof of semantic value.

---

## 9. Current priority summary

```text
P0  PR #1  manual checkpoint correctness
P0  #6     immutable config / mutable trust isolation
P0  #2a    automatic safe reuse fallback
P0  #4     cancel/requeue/invalidate unstarted ACCEPTED
P0  #13    truthful writable scratch semantics
P0  #5     qualified development toolchains/caches
P0         qualified Codex artifact distribution
P0         atlas-agent install
P0         atlas-agent install-doctor
P0/P1 #9  reproducible activation + install identity

P1  #8     qualified timeout defaults
P1  #10    explicit/practical network semantics
P1  #14    generic Luna implementation contract
P1  #15a   qualified project prompt overlays
P1  #3     bounded status/history

P2  #7     concise local tool-call progress
P2  #11    usage/cache/reasoning/cost accounting
P2  #2b    proactive context-headroom rollover
P2  #15b   structured project-defined task outcome

THEN       freeze broad Agent expansion
THEN P3.1 external corpora/component qualification
THEN P3.2 semantic candidate discovery
THEN P3.3 real selection/composition
THEN P3.4 black-box Core V1 conformance
THEN P3.5 materialization only when semantically motivated

LATER P4  selective release automation
LATER P5  targeted security enforcement review
LATER P6  evidence-driven ergonomics
LATER P7  broader Linux targets/topologies
LATER P8  other OS isolation backends
LATER P9  broader Atlas semantics under demonstrated need
```

---

## 10. Immediate concrete sequence

A reasonable implementation order is:

```text
1. finish/merge PR #1 checkpoint correctness
2. fix #6 config/trust self-invalidation
3. implement #2a safe reuse fallback
4. implement #4 durable cancel/requeue/invalidate
5. resolve #13 scratch semantics
6. implement #5 qualified toolchain/cache capability
7. implement #8 profile timeouts
8. resolve #10 network model/defaults
9. implement #14 generic implementation contract
10. implement #15a qualified project overlays
11. close artifact/install/install-doctor/#9 installability gap
12. take #3 as a low-risk long-history UX improvement
13. run another sustained Memoria tranche on the candidate
14. release once blockers/installability gates are satisfied
15. defer #7/#11/#2b/#15b unless they prove trivial
16. freeze broad Agent expansion
17. return primary development effort to Atlas Core
```

This order may be parallelized where implementation boundaries are independent, but release gates should preserve the logical dependencies.

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
# establish/review project policy, overlays and authority
atlas-agent init
atlas-agent doctor
```

For normal work:

```bash
atlas-agent ingest
atlas-agent dispatch
```

The operator should not need to understand or manually repair:

```text
where Codex was built
sealed memfd authority
stable-path current_exe mechanics
asset-set hash construction
annotated-tag dereference
Bubblewrap exec-server qualification
Codex config trust drift
reuse hop bookkeeping
journal suffix surgery
sandbox toolchain visibility
scratch mount surprises
shell activation reconstruction
repeated generic/project prompt boilerplate
```

Those are infrastructure concerns captured by release engineering, policy, qualified runtime state, and diagnostics.

When this is true, Atlas Agent has achieved its immediate purpose:

```text
reliable infrastructure that fades into the background
while Atlas itself becomes the thing being developed and evaluated
```
