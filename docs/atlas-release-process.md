# Atlas / Atlas Agent release process

Procedure version: **0.2**

This document defines the production release procedure for Atlas Agent and its
qualified Atlas Codex runtime.

It is deliberately gate-based. A release is not merely a Git tag or a green
test suite. It is a chain of separately checked identities and runtime
properties. Each gate should produce evidence that can be inspected later.

The procedure was refined from the first deployable Atlas Agent releases,
especially v0.1.1. That release showed that several things which can look like
one "version" are in fact independent release dimensions: Atlas Agent source,
Atlas Codex source, the compiled Codex executable, canonical Codex assets,
prompts and profiles, authentication state, sandbox behavior, workflow state,
and Git publication.

The goal of this procedure is to make those distinctions explicit enough that
a release can be reproduced, audited, diagnosed, and deployed without relying
on the development machine's accidental state.

---

## 1. Release principles

### 1.1 Release by evidence, not by intention

Every production claim should be backed by a concrete observation. Examples:

* a source identity is a Git commit or immutable tag;
* a runtime binary identity is the SHA-256 of the exact bytes that execute;
* an asset identity is the digest of the canonical versioned asset set;
* a prompt identity is the digest of the canonical prompt set;
* a sandbox claim is established by a live sandbox test;
* an authenticated execution claim is established by a real minimal model run;
* publication is established by checking the remote branch and dereferenced tag.

Do not substitute a nearby proxy for the thing being qualified. In particular,
`codex --version`, a pathname, a source commit, and a binary SHA-256 are not
interchangeable identities.

### 1.2 Stop at failed gates

A failed gate blocks publication until it is understood.

Do not repair release evidence by mutating historical state, deleting old
journals, rebuilding binaries without recording the new identity, or silently
changing release metadata to match whatever happens to exist on the machine.

A failure may turn out to be historical or environmental rather than a product
regression. That distinction must be demonstrated, not assumed.

### 1.3 Keep release dimensions separate

The main dimensions are:

```text
Atlas Agent source
Atlas Agent release manifest
Atlas Codex source
Atlas Codex compiled binary
Codex canonical assets
Atlas prompts and profiles
mutable authentication state
sandbox/runtime qualification
workflow/journal state
Git tag and remote publication
```

A new Atlas Agent release does **not** imply a new Atlas Codex release. If the
Codex source and compiled runtime are unchanged and still qualified, the Agent
release should reuse the exact existing Atlas Codex release identity.

Likewise, changing only prompts or profiles does not by itself require a new
Codex source tag, while rebuilding Codex from unchanged source does create a new
binary identity unless bit-for-bit reproducibility has been demonstrated.

### 1.4 Security, reproducibility, workflow assurance, and methodology differ

Release checks should state what property they establish.

* **Security boundary** checks establish that effective capabilities cannot
  exceed the controller-owned policy ceiling.
* **Reproducibility** checks establish which exact source, binary, asset, prompt,
  and profile identities were used.
* **Workflow assurance** checks establish journal consistency, repository
  witnesses, ownership transitions, and lifecycle behavior.
* **Methodology** checks establish the intended development/review process.

Do not label every reproducibility mismatch a security failure, and do not
weaken a real capability-boundary failure by calling it merely a methodology
issue.

---

## 2. Authorities and identities

### 2.1 Atlas Agent source authority

The release candidate is an exact Atlas Agent commit.

Before tagging, record:

```bash
git rev-parse HEAD
git status --short
```

The working tree must be clean at the final release boundary.

### 2.2 Release manifest authority

`atlas-release.toml` records the identities required to reproduce the runtime
configuration for the release. It should identify at least:

* the intended Atlas Agent tag;
* the canonical asset version;
* asset-set and prompt-set digests;
* Atlas Codex upstream/base commit;
* Atlas Codex immutable tag and exact source commit;
* the qualified Codex configuration and catalog digests;
* profile file identities;
* one or more target-specific Codex binary SHA-256 values.

The manifest is release metadata. It does not replace independent verification
of the referenced repositories and bytes.

### 2.3 Atlas Codex source authority

Atlas Agent uses a dedicated Codex fork with a small explicit Atlas patch stack.
A production Codex source identity consists of:

```text
upstream/base commit
+ Atlas-specific patch stack
+ final Atlas Codex commit
+ immutable Atlas Codex tag
```

The historical first Atlas Codex tag, `atlas-main-20260830-1`, remains immutable.
Future releases should use a clearer distinct naming convention such as:

```text
atlas-codex-YYYYMMDD-N
```

Do not rename or repoint already published tags merely to improve naming.

### 2.4 Codex binary authority

The exact executable bytes are the execution authority.

For each supported target, record:

```bash
sha256sum /path/to/qualified/codex
/path/to/qualified/codex --version
file /path/to/qualified/codex
```

The SHA-256 must match `atlas-release.toml` for the target.

The executable's self-reported version is useful evidence but is not sufficient.
A fork build may report an upstream or placeholder version. The source tag,
source commit, and exact binary SHA-256 are authoritative.

Never identify the production runtime merely with `command -v codex`. A user's
PATH may resolve an unrelated npm or distribution Codex installation.

### 2.5 Canonical asset authority

Versioned canonical assets live under a release-specific directory such as:

```text
codex-assets/v0.1.1/
```

The canonical set contains only the files defined by the release. For the
current architecture that includes the Codex configuration, model catalog,
Atlas profile files, and Atlas-owned prompt files.

Canonical source assets must be validated before provisioning and must not be
silently accepted when missing, corrupted, symlinked, non-regular, or padded
with unexpected authoritative files.

### 2.6 Mutable authentication is not a canonical asset

Authentication is mutable user state and must remain distinct from the release
asset identity.

A qualified CODEX_HOME may therefore contain immutable/versioned Atlas assets
plus a mutable authentication reference, for example:

```text
auth.json -> ~/.codex/auth.json
```

Do not copy secrets into the source asset directory or include authentication
bytes in `asset_set_sha256` or `prompt_set_sha256`.

Authentication may be required for an authenticated smoke test, but it is not
part of the immutable release artifact.

---

## 3. Roles during a release

The normal Atlas development/review split is:

```text
Luna    implementation, exploration, iterative tests
Sol     independent focused review and release audit
Blue    security-specific review when required
operator commits, tags, and publishes
```

Implementation agents should normally leave changes uncommitted for independent
review. When delegating implementation work, state explicitly when the agent
must **not** stage, commit, tag, or push.

The operator remains the authority for final commits and publication.

---

## 4. Release gate sequence

A normal release follows these gates in order.

```text
 1. define release scope
 2. establish repository state
 3. create logical implementation commits or reviewable changes
 4. construct and qualify canonical assets
 5. qualify prompts and profiles
 6. run focused tests
 7. run full pre-review tests
 8. independent Sol review
 9. resolve findings
10. create final release commits
11. identify exact Codex executable
12. provision immutable assets atomically
13. run zero-token runtime qualification
14. inspect fresh runtime/workflow state
15. run authenticated minimal smoke
16. account for lifecycle/result semantics
17. perform final release-state audit
18. create annotated tag and publish deliberately
19. verify remote provenance and deployment state
```

Do not collapse later gates into earlier ones merely because a previous release
happened to pass them together.

---

## 5. Gate 1 — define release scope

Write down what the release is intended to change and, equally importantly,
what it is **not** intended to change.

Typical scope categories include:

* Atlas Agent runtime behavior;
* sandbox/runtime fixes;
* workflow lifecycle semantics;
* canonical assets;
* prompts and profile behavior;
* policy metadata;
* Atlas Codex fork changes;
* documentation only.

If Codex source is not changing, state explicitly that the release reuses the
previous qualified Codex source and binary. This prevents manufacturing a new
Codex tag solely to make version numbers appear aligned.

Release scope should remain narrow after review begins. New architectural or
security redesigns discovered during qualification should normally become a
separate change unless they block the release's stated safety or correctness.

---

## 6. Gate 2 — establish repository state

Before release work, capture the current Atlas Agent state:

```bash
git status --short
git rev-parse HEAD
git log --oneline --decorate -n 10
git tag --list 'atlas-agent-v*'
```

Identify the previous release tag and verify what it dereferences to:

```bash
git rev-parse 'atlas-agent-vX.Y.Z^{}'
```

For annotated tags, plain `git rev-parse atlas-agent-vX.Y.Z` returns the tag
object SHA, not the release commit. Use `^{}` or `git show --no-patch` when
comparing the tag with a commit.

At this point also identify the Codex fork repository and current intended
runtime source if the release depends on it.

---

## 7. Gate 3 — keep changes in logical units

Release changes should be reviewable as independent logical units when
practical. Examples:

```text
runtime/sandbox fix
canonical assets and prompt packaging
release metadata correction
documentation
```

Avoid combining unrelated implementation and release metadata into one opaque
commit unless there is a strong reason.

During the implementation/review cycle, the normal pattern is:

```text
Luna implements without committing
→ focused tests
→ Sol reviews the uncommitted diff read-only
→ Luna fixes only the accepted findings
→ Sol verifies the fixes
→ operator commits
```

This preserves independent review and reduces accidental history churn.

---

## 8. Gate 4 — construct and qualify canonical assets

Canonical Codex assets must be versioned explicitly.

If a previous release's exact assets are needed for comparison or
reproducibility, preserve their exact bytes under their historical version
directory rather than reconstructing approximations.

For the candidate asset version:

1. define the exact required file set;
2. reject symlinked or non-regular authoritative files;
3. reject missing required files;
4. reject unexpected authoritative files;
5. compute each required file digest;
6. compute the aggregate asset-set identity;
7. record the identities in `atlas-release.toml`;
8. test that the implementation derives the same identities independently.

Assets should be treated as immutable release inputs. Runtime-generated cache,
session, history, SQLite, installation, plugin, and authentication files do not
belong in the canonical source asset set.

---

## 9. Gate 5 — qualify prompts and profiles

Prompts and profiles are release inputs with their own provenance.

For every profile, verify:

* intended model;
* reasoning effort;
* sandbox mode;
* network policy;
* session behavior;
* prompt selection;
* exact profile SHA-256.

The Atlas common prompt and any role-specific prompt material must be included
in prompt-set identity computation.

A prompt change is not "just text" once it changes runtime behavior. Record its
bytes and digest as deliberately as executable configuration.

Profile-relative paths must resolve from the dedicated CODEX_HOME/config layer,
not accidentally from the target user's repository.

---

## 10. Gate 6 — focused tests

Run tests targeted at every changed release-sensitive area.

Examples include:

* policy resolution;
* asset validation and provisioning;
* prompt/profile identity;
* Codex executable snapshot validation;
* Bubblewrap construction;
* exec-server lifecycle;
* process teardown and reap behavior;
* workflow provenance;
* serialization of policy overrides;
* repository ownership/witness behavior.

Use focused tests during iteration because they give fast diagnostic feedback.
They do not replace the full suite.

---

## 11. Gate 7 — full pre-review tests

Before independent final review, run the full Atlas Agent suite from a clean
candidate state:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q -rs tests
```

Record the exact result. Test counts may legitimately change as tests are added
or removed; the important property is that the collected candidate suite has no
unexpected failures and that any skips are understood.

Run:

```bash
git diff --check
```

as a separate formatting/integrity gate.

---

## 12. Gate 8 — independent Sol review

Sol should review the candidate against the release scope, not redesign the
project opportunistically.

The review should distinguish severity and property:

```text
BLOCKER  release cannot proceed
HIGH     important correctness/security/reproducibility defect
MEDIUM   should normally be fixed before release
LOW      non-blocking improvement or future work
```

The review should state explicitly which previously reported findings are now
PASS and which remain open.

For security findings, compare the implementation with the controller-owned
security policy. Do not infer additional security requirements merely from
repository prose or model preferences.

---

## 13. Gate 9 — resolve findings narrowly

Fix release-blocking findings with the smallest justified change set.

When delegating fixes to an implementation agent, provide the exact finding
list and explicitly state:

```text
DO NOT COMMIT
DO NOT STAGE
DO NOT TAG
DO NOT PUSH
```

unless the operator intentionally delegates those authorities.

After fixes:

* rerun the focused tests;
* rerun the full suite when warranted;
* rerun `git diff --check`;
* obtain a narrow independent verification of the resolved findings.

Do not reopen already settled architecture without a concrete blocker.

---

## 14. Gate 10 — create final release commits

Once review is PASS, create the final logical commits.

Then verify:

```bash
git status --short
git log --oneline --decorate -n 10
git diff --check <previous-release-tag>..HEAD
```

The candidate commit sequence is now the intended Atlas Agent release source.
Avoid further implementation changes after this point unless a later runtime
gate exposes a genuine blocker. If source changes, repeat the affected gates.

---

## 15. Gate 11 — identify the exact Codex executable

Do not assume that the `codex` found in PATH is the Atlas runtime.

First establish the Atlas Codex source identity:

```bash
cd /path/to/codex-atlas
git status --short
git rev-parse HEAD
git describe --tags --always --decorate
```

Verify that the intended Atlas Codex tag resolves to the expected commit.

Then identify the actual production binary, normally a qualified release build:

```text
codex-rs/target/release/codex
```

Record:

```bash
sha256sum /absolute/path/to/codex
/absolute/path/to/codex --version
file /absolute/path/to/codex
```

The digest must exactly match the target entry in `atlas-release.toml`.

If the binary digest differs, stop. Determine whether the wrong binary was
selected or whether a new build was produced. Do not update the manifest merely
to make the mismatch disappear.

### 15.1 Do not rebuild unnecessarily

If the Agent release intentionally reuses an already qualified Codex source and
binary, do not rebuild Codex simply because a new Agent version is being
released. A rebuild would create a new binary identity and require requalification.

---

## 16. Gate 12 — provision immutable assets atomically

Provision a **fresh** versioned CODEX_HOME from the canonical release source.

The provisioning operation should:

1. validate the entire canonical source before modifying the destination;
2. require a safe non-symlink destination ancestry;
3. refuse an already existing destination rather than partially updating it;
4. stage a complete copy in a sibling temporary directory;
5. set deliberate permissions;
6. revalidate the staged copy;
7. atomically publish the complete directory by rename;
8. clean up only the unpublished staging directory on failure.

Conceptually:

```text
canonical versioned source
        ↓ validate
sibling staging directory
        ↓ copy + revalidate
atomic rename
        ↓
versioned CODEX_HOME
```

After provisioning, independently recompute the asset-set, prompt-set, and
profile identities from the destination.

At this point the immutable assets should match the release manifest exactly.

### 16.1 Add mutable authentication only after asset qualification

If authenticated testing is required, attach the user's mutable authentication
state after the canonical destination has been qualified, for example:

```text
<versioned CODEX_HOME>/auth.json -> ~/.codex/auth.json
```

Do not include that link or target secret in the canonical asset identity.
Do not print, hash, or otherwise expose credential contents during release
qualification.

---

## 17. Gate 13 — zero-token runtime qualification

Before consuming model tokens, qualify the real execution chain on the target
host.

At minimum, verify the path which historically failed:

```text
pinned Atlas Codex binary
→ validated/sealed runtime authority
→ stable runtime pathname
→ Bubblewrap
→ Codex exec-server
→ current_exe()
→ arg0 helper dispatch (codex-linux-sandbox)
→ /bin/true
→ exit 0
→ confirmed process reap
→ runtime cleanup
```

This must exercise the real production mechanism, not a mock that bypasses the
exec-server or helper dispatch.

Also run the broader live Bubblewrap test file when supported on the target
host.

A target host where Bubblewrap is unavailable may legitimately skip host-live
tests during ordinary development, but a production release for that target
must obtain equivalent runtime qualification somewhere representative.

---

## 18. Gate 14 — inspect fresh runtime/workflow state

Runtime qualification should not depend on a stale development journal.

Run `init`, `doctor`, `status`, and `executor-info` against a **fresh repository
state** at the exact candidate commit.

A historical local `.git/atlas-agent` journal may have been created by older
pre-release semantics and can therefore fail validation under the current
implementation. That is not automatically a release regression.

If this occurs:

1. inspect the journal read-only;
2. determine which historical event violates the current contract;
3. compare the relevant validator with the previous released implementation if
   necessary;
4. do not delete or rewrite the historical journal merely to make `doctor`
   green;
5. validate the release candidate against a fresh workflow state.

### 18.1 Prefer a fresh clone for final runtime smoke

A linked Git worktree is useful for isolated workflow/journal inspection, but it
has a different `.git` topology (`.git` is commonly a file referring to another
Git directory).

If the sandbox implementation expects a conventional repository-local `.git`
directory, use a fresh local clone for the final authenticated execution smoke.

The smoke environment should therefore be independent enough to avoid inherited
workflow state while still exercising the production Git topology.

---

## 19. Gate 15 — authenticated minimal smoke

After all zero-token checks pass, perform one small authenticated model execution
through the public Atlas Agent workflow.

The smoke should be deliberately cheap and constrained. A suitable pattern is:

```text
action: implementation
session: fresh
network: false
request: invoke exactly one harmless command such as `true`
then return a unique fixed marker
```

Run it through the normal public path:

```text
prompt in inbox
→ atlas-agent ingest
→ atlas-agent dispatch
```

Do not bypass policy resolution by directly calling private executor methods.
The public workflow must construct and bind the executable policy snapshot.

The smoke should prove together:

* prompt parsing and ingestion;
* policy resolution;
* intended Luna/Sol model selection for the action;
* intended reasoning effort;
* intended sandbox mode;
* network policy;
* canonical profile selection;
* dedicated CODEX_HOME;
* mutable authentication access;
* pinned Atlas Codex executable;
* Bubblewrap and exec-server startup;
* real tool invocation;
* successful terminal lifecycle;
* model response collection;
* repository witness preservation.

After dispatch, check:

```bash
python3 -m tools.atlas_agent status
python3 -m tools.atlas_agent doctor
git status --short
git rev-parse HEAD
python3 -m tools.atlas_agent report <generation>
```

Also inspect the execution JSONL sufficiently to prove that the expected tool
was actually invoked and completed successfully. A model merely printing the
expected marker is not enough.

For a one-command smoke, two JSONL lifecycle records such as
`item.started`/`item.completed` for the same item ID represent one actual tool
invocation, not two invocations.

The candidate repository must remain unchanged unless the smoke explicitly
tests authorized workspace mutations.

---

## 20. Gate 16 — account for lifecycle/result semantics

Atlas workflow completion and subprocess completion are not necessarily the
same semantic claim as task-level success.

When qualifying a release, distinguish at least:

```text
workflow generation reached COMPLETED
executor outcome was success
process/tool exit code was 0
expected tool actually ran
expected model result was produced
repository postconditions remained valid
```

Do not treat a single `COMPLETED` label as proof of all of the above.

If richer structured execution-health semantics are introduced in future
versions, add them here rather than weakening the distinction.

---

## 21. Gate 17 — final release-state audit

Return to the real candidate repository, not the temporary smoke clone.

Run at minimum:

```bash
git status --short
git rev-parse HEAD
git log --oneline --decorate -n 10
git diff --check
git diff --stat <previous-release-tag>..HEAD
git tag --list '<candidate-release-tag>'
sha256sum /absolute/path/to/qualified/codex
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_atlas_codex_assets.py
```

Expected final state:

* working tree clean;
* HEAD equals the reviewed candidate commit;
* no whitespace/diff integrity errors;
* candidate tag does not already exist;
* Codex binary digest still matches the release manifest;
* canonical asset tests pass.

If source changed after the last full suite or independent review, repeat the
appropriate earlier gates before tagging.

---

## 22. Gate 18 — tag and publish deliberately

Atlas Agent release tags are annotated tags.

Create locally only after every previous gate passes:

```bash
git tag -a atlas-agent-vX.Y.Z -m "Atlas Agent vX.Y.Z"
```

Verify the tag object and its dereferenced commit:

```bash
git cat-file -t atlas-agent-vX.Y.Z
git rev-parse HEAD
git rev-parse 'atlas-agent-vX.Y.Z^{}'
git show --no-patch --decorate --format=fuller atlas-agent-vX.Y.Z
```

Expected:

```text
git cat-file -t ...        -> tag
HEAD                        -> candidate commit
tag^{}                      -> same candidate commit
```

The plain tag object SHA is expected to differ from the commit SHA.

### 22.1 Push only the intended refs

After local tag verification and explicit operator approval:

```bash
git push origin <release-branch>
git push origin atlas-agent-vX.Y.Z
```

Do not use `--tags`. Do not force-push release refs.

If local proxy environment variables interfere with Git transport, clear the
relevant proxy variables deliberately and retry only the intended push.

---

## 23. Gate 19 — verify remote provenance

After publication, independently verify both the branch and the annotated tag:

```bash
git ls-remote --heads origin <release-branch>
git ls-remote --tags origin \
  refs/tags/atlas-agent-vX.Y.Z \
  'refs/tags/atlas-agent-vX.Y.Z^{}'
```

Expected shape:

```text
<candidate commit>    refs/heads/<release-branch>
<tag object sha>      refs/tags/atlas-agent-vX.Y.Z
<candidate commit>    refs/tags/atlas-agent-vX.Y.Z^{}
```

Where practical, also query the remote hosting service independently and verify
that:

* the candidate commit exists remotely;
* the tag object type is `tag`;
* the tag object points to the candidate commit;
* the tag message and tagger are as expected.

A tag being unsigned is distinct from it being unannotated. If cryptographic
Git tag signing becomes a release requirement, add that as an explicit policy
and gate; do not infer it retroactively.

---

## 24. Post-release provenance record

A completed release should leave enough evidence to answer these questions
without reconstructing the developer's shell history:

```text
Which Atlas Agent commit was released?
Which annotated Atlas Agent tag identifies it?
Which Atlas Codex source commit and tag were used?
Which upstream/base Codex commit was used?
Which exact Codex binary SHA-256 executed?
Which target architecture did that binary serve?
Which canonical asset version was installed?
What were the asset-set and prompt-set digests?
Which profile digests were active?
Did the zero-token runtime qualification pass?
Did the authenticated smoke pass?
Did repository witness/state checks pass?
Were the remote branch and dereferenced tag verified?
```

`atlas-release.toml`, Git history/tags, test evidence, and release notes should
collectively answer these questions.

---

# Atlas Codex fork management addendum

Atlas Codex has its own release lifecycle. This section applies when Codex source
or build identity changes.

## A.1 Dedicated fork

Maintain Atlas Codex in a dedicated fork and checkout, separate from the Atlas
Agent repository.

The development checkout is not itself runtime authority. Production execution
uses a specifically qualified binary whose bytes match the release manifest.

## A.2 Keep the Atlas patch stack small

Prefer:

```text
upstream Codex base
        +
small explicit Atlas patch stack
        =
qualified Atlas Codex source
```

Do not maintain a permanently merged fork when a small patch stack is
sufficient.

Record for every Atlas Codex source release:

```text
upstream/base commit or release tag
Atlas-specific commits
final Atlas Codex commit
immutable Atlas Codex tag
```

## A.3 Do not rebase on every upstream commit

The Atlas fork does not need to chase every upstream `main` commit.

Refresh deliberately when:

* an upstream release is being adopted;
* an Atlas-required fix lands upstream;
* compatibility needs to be tested;
* the Atlas patch stack needs to be rebased for a specific reason.

A development branch may follow newer upstream code for compatibility testing
without becoming the production release source.

## A.4 Prefer official upstream release bases when practical

When an official upstream release is suitable, create the Atlas release source
from that immutable upstream release and reapply only Atlas-specific patches.

If a release must be based on an upstream main snapshot, record the exact
upstream commit and do not pretend it was based on a release tag.

## A.5 Reapply only Atlas-specific commits

Do not carry forward temporary upstream cherry-picks that are already included
in the new upstream base.

Conflicts must be resolved against the new upstream architecture, especially in
areas affecting:

* tool registration;
* model tool allowlists;
* hosted tools;
* deferred tool discovery;
* Code Mode;
* dispatch/routing;
* configuration precedence;
* sandbox/helper execution.

## A.6 Verify the source delta

For a release based on an upstream tag or commit:

```bash
git diff <upstream-base>..<atlas-codex-release>
git log --oneline <upstream-base>..<atlas-codex-release>
```

The delta should contain only intentional Atlas changes.

## A.7 Test the strict tool allowlist boundary

At minimum verify:

* absent allowlist preserves the intended upstream surface;
* explicit empty allowlist exposes no model tools;
* allowed tools remain available;
* disallowed registered tools are removed;
* hosted tools are filtered;
* deferred/tool-search discovery cannot reveal disallowed tools;
* Code Mode cannot reintroduce disallowed tools;
* dispatch cannot invoke a tool excluded from the finalized registry.

Run broader upstream tests whenever changed upstream code overlaps Atlas-patched
areas.

## A.8 Build development and release binaries separately

Development iteration may use:

```bash
cd codex-rs
cargo build -p codex-cli
```

Production qualification should use the intended release build, normally:

```bash
cargo build --release -p codex-cli
```

Record the exact production binary identity immediately after build.

Do not assume rebuilding identical source yields identical bytes unless
reproducible-build properties have been explicitly established.

## A.9 Source release and binary release are separate dimensions

One Atlas Codex source release may have several target-specific production
binaries:

```toml
[[codex.binaries]]
target = "x86_64-unknown-linux-gnu"
sha256 = "<sha256>"

[[codex.binaries]]
target = "aarch64-unknown-linux-gnu"
sha256 = "<sha256>"

[[codex.binaries]]
target = "aarch64-apple-darwin"
sha256 = "<sha256>"
```

Each actual production binary must be qualified independently.

## A.10 Publish Codex tags immutably

Published Atlas Codex tags are immutable release identities.

Use a distinct naming scheme for future fork releases, preferably:

```text
atlas-codex-YYYYMMDD-N
```

A new Atlas Agent release does **not** require incrementing this tag if Codex
source and qualified binary are unchanged.

Do not create a new Codex tag solely to make an Agent version number line up
visually with a Codex version number.

---

## 25. Installation-path implications

Release qualification and user installation are related but distinct.

The manual v0.1.1 qualification demonstrated a useful future contract for an
installation command and an installation diagnostic:

```text
atlas-agent install
atlas-agent install-doctor
```

Those commands are not assumed to exist merely because this procedure describes
them. When implemented, they should absorb or verify the machine-level steps
that are currently manual:

* locating/installing the qualified Atlas Agent release;
* locating or installing the qualified Atlas Codex binary;
* checking its SHA-256 against the manifest;
* provisioning the versioned CODEX_HOME atomically;
* attaching mutable authentication without copying secrets into canonical
  assets;
* checking Bubblewrap and host prerequisites;
* performing zero-token installation qualification;
* optionally performing an authenticated smoke.

Project-level commands remain conceptually separate:

```text
install / install-doctor     machine installation
init / doctor                one project's workflow state
```

Once installation commands become part of the product, every release should
include a clean-host or near-clean-host qualification through that public path.
The release guide should then prefer the public installer over the lower-level
manual provisioning steps described here, while keeping those lower-level steps
as diagnostic/reference material.

---

## 26. Release checklist

A concise release checklist follows. It does not replace the detailed gates.

```text
[ ] scope frozen
[ ] Atlas Agent working tree understood
[ ] previous release tag identified and dereferenced
[ ] candidate changes logically separated
[ ] canonical assets complete and hashed
[ ] prompts/profiles hashed and qualified
[ ] focused tests pass
[ ] full suite passes
[ ] git diff --check passes
[ ] independent Sol review passes
[ ] review findings resolved and reverified
[ ] final release commits created
[ ] Atlas Codex source tag/commit verified
[ ] exact Codex binary SHA matches manifest
[ ] fresh versioned CODEX_HOME provisioned atomically
[ ] destination asset/prompt/profile identities match
[ ] mutable auth attached separately if needed
[ ] zero-token Bubblewrap/exec-server regression passes
[ ] broader live sandbox tests pass on target host
[ ] fresh init/doctor/status/executor-info pass
[ ] authenticated minimal public-workflow smoke passes
[ ] actual expected tool invocation verified in JSONL
[ ] smoke repository remains in expected state
[ ] final candidate working tree clean
[ ] final asset tests pass
[ ] annotated Atlas Agent tag created locally
[ ] tag^{} equals candidate commit
[ ] only intended branch and tag pushed
[ ] remote branch equals candidate commit
[ ] remote tag object is annotated
[ ] remote tag^{} equals candidate commit
[ ] release provenance recorded
```

---

## 27. Guiding principle

A trustworthy Atlas Agent release is a reproducible chain of authority:

```text
reviewed Atlas Agent source
        +
explicit release manifest
        +
qualified Atlas Codex source
        +
exact qualified Codex binary bytes
        +
versioned canonical assets and prompts
        +
controller-owned policy
        +
verified sandbox/runtime behavior
        +
fresh workflow qualification
        +
authenticated minimal smoke
        +
immutable Git publication
        =
production Atlas Agent release
```

The procedure should evolve toward fewer manual steps, but automation must not
collapse these authorities into one opaque "install succeeded" signal. Good
automation preserves the distinctions and produces the evidence automatically.
