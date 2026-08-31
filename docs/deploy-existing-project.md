# Deploying Atlas Agent into an existing project

Document version: **0.2**

This document is the user-facing deployment and first-start guide for Atlas
Agent on an existing project.

Current scope is intentionally narrow:

```text
operating system: Linux
shell:            bash
repository:       ordinary non-bare Git repository
Atlas backend:    Bubblewrap
```

Atlas Agent's release engineering procedure is documented separately in
`docs/atlas-release-process.md`. A project user should not need to reproduce
that procedure. The deployment goal is much simpler: use one already validated
Atlas Agent release and its matching Codex runtime without depending on the
state of the Atlas development repository.

This document uses Atlas Agent v0.1.1 as the concrete current example. When a
later release changes commands or identities, the release itself is
authoritative.

---

## 1. The deployment model

There are two different installations:

```text
machine installation
    Atlas Agent release
    qualified Atlas Codex executable
    versioned canonical Codex assets
    mutable user authentication reference
    Bubblewrap/runtime prerequisites

project initialization
    atlas-agent-policy.toml
    project-specific workflow journal
    repository witness
    prompts, reports, and execution history
```

Do not mix them.

Atlas Agent and Codex should normally be installed **once per machine/release**.
A project is then initialized separately and receives its own workflow history.

In particular, never copy another repository's `.git/atlas-agent` directory
into a new project.

---

## 2. Command model: installation versus project state

The intended command split is:

```text
atlas-agent install
    install or qualify Atlas Agent and its matching runtime on this machine

atlas-agent install-doctor
    diagnose the machine installation without depending on a project journal

atlas-agent init
    initialize Atlas Agent for the current Git repository

atlas-agent doctor
    diagnose Atlas workflow state for the current Git repository
```

### 2.1 Current v0.1.1 status

`init`, `doctor`, `status`, `executor-info`, `ingest`, `dispatch`, and the other
workflow commands exist in v0.1.1.

The machine-level `install` and `install-doctor` commands are the intended user
interface but are **not yet implemented in v0.1.1**. Until they exist, use the
manual Linux/bash bootstrap in this document.

Do not interpret:

```text
doctor: OK
```

as proof that the machine installation is complete. `doctor` validates the
current project's workflow state. Machine installation diagnostics are a
separate responsibility.

### 2.2 Intended future path

Once the installation commands exist, normal deployment should reduce to
approximately:

```bash
# once per machine/release
atlas-agent install
atlas-agent install-doctor

# once per project
cd /path/to/project
# install/review project policy before init
atlas-agent init
atlas-agent doctor

# ordinary use
atlas-agent ingest
atlas-agent dispatch
```

An authenticated installation smoke should be optional because it consumes
model tokens:

```bash
atlas-agent install-doctor --authenticated
```

The rest of this document defines what those commands eventually need to hide
or verify.

---

## 3. Current supported deployment boundary

For Atlas Agent v0.1.1, the validated deployment target is Linux x86_64 using
the Atlas Bubblewrap backend.

The release manifest identifies the matching runtime. For v0.1.1 the important
identities are:

```text
Atlas Agent tag:          atlas-agent-v0.1.1
Atlas Agent commit:       115cc1514208341ed14d60021ca24dfc7681841f
asset version:            v0.1.1

Atlas Codex tag:          atlas-main-20260830-1
Atlas Codex commit:       a201cff86d370703cfe3938e6c1f6f80348ef953
Codex target:             x86_64-unknown-linux-gnu
Codex binary SHA-256:     5e841fe3f20e1649a0dc9ec144a73f56a6f62bb7e566a479dc46413d36d41524
```

Do not copy these values into future deployment automation as permanent
constants. Read them from the selected release's `atlas-release.toml`.

### 3.1 Current important limitations

For v0.1.1:

* Linux is required by the hardened execution backend.
* The production runtime must be a native Codex executable whose exact SHA-256
  matches the release manifest.
* A normal Git repository topology with a real `.git/` directory is required
  for Bubblewrap execution.
* Git linked worktrees, where `.git` is a file pointing elsewhere, are not
  currently supported by the execution backend.
* A project-local `.codex/config.toml` is rejected rather than silently merged
  with Atlas configuration.
* Atlas does not yet download or install the qualified Codex binary for the
  user.
* Atlas does not yet install the canonical CODEX_HOME through a public CLI
  command.
* Authentication is expected to exist as mutable user state outside the
  canonical Atlas assets.

These are current implementation boundaries, not necessarily long-term design
requirements.

---

## 4. Host prerequisites

Before deployment, verify the basic host:

```bash
uname -s
uname -m
python3 --version
git --version
bwrap --version
```

For the currently validated v0.1.1 target, expect:

```text
Linux
x86_64
Python >= 3.11
Git available
Bubblewrap available
```

v0.1.1 was release-qualified with Bubblewrap 0.12.0. That observation is not a
claim that 0.12.0 is the minimum possible version; the real criterion is that
the Atlas namespace/runtime probes succeed on the target host.

The user also needs normal authenticated access to the model provider. Atlas
must not print or copy credential contents while checking this.

---

## 5. Choose stable machine locations

The following layout is recommended for the manual v0.1.1 bootstrap:

```text
~/.local/share/atlas-agent/
    releases/
        atlas-agent-v0.1.1/
    codex-homes/
        v0.1.1/
```

The exact qualified Codex executable may live elsewhere. Its pathname is not
its identity; Atlas verifies the executable bytes by SHA-256.

Set a few shell variables:

```bash
export ATLAS_BASE="$HOME/.local/share/atlas-agent"
export ATLAS_AGENT_TAG="atlas-agent-v0.1.1"
export ATLAS_AGENT_SRC="$ATLAS_BASE/releases/$ATLAS_AGENT_TAG"
export ATLAS_CODEX_HOME="$ATLAS_BASE/codex-homes/v0.1.1"
```

Do not point these variables at a moving development checkout when a validated
release exists.

---

## 6. Manual machine bootstrap for v0.1.1

This section is the temporary replacement for the future `atlas-agent install`
command.

### 6.1 Fetch the exact Atlas Agent release

Create the release parent and clone Atlas Agent if it is not already present:

```bash
mkdir -p "$ATLAS_BASE/releases"

git clone https://github.com/cyrilmhansen/atlas-py.git "$ATLAS_AGENT_SRC"
git -C "$ATLAS_AGENT_SRC" switch --detach "$ATLAS_AGENT_TAG"
```

Verify the release identity:

```bash
git -C "$ATLAS_AGENT_SRC" status --short
git -C "$ATLAS_AGENT_SRC" cat-file -t "$ATLAS_AGENT_TAG"
git -C "$ATLAS_AGENT_SRC" rev-parse HEAD
git -C "$ATLAS_AGENT_SRC" rev-parse "$ATLAS_AGENT_TAG^{}"
```

For an annotated release tag:

* `cat-file -t` should report `tag`;
* `HEAD` and `tag^{}` must identify the same release commit;
* the checkout should be clean.

For v0.1.1 both commit values are expected to be:

```text
115cc1514208341ed14d60021ca24dfc7681841f
```

### 6.2 Read the release manifest instead of pairing versions manually

Inspect:

```bash
sed -n '1,220p' "$ATLAS_AGENT_SRC/atlas-release.toml"
```

The release manifest defines the Codex source tag/commit, target binary digest,
asset version, canonical configuration, model catalog, prompt set, and profile
identities.

Do not independently choose "the newest" Atlas Agent and "the newest" Codex.
The pair recorded by the release was qualified together.

### 6.3 Provide the exact qualified Codex executable

Set `ATLAS_CODEX_EXECUTABLE` to the native Codex binary supplied or previously
qualified for this release:

```bash
export ATLAS_CODEX_EXECUTABLE="/absolute/path/to/qualified/codex"
```

It must be absolute, a regular executable file, and not group/world writable.

Obtain the expected digest directly from the manifest:

```bash
EXPECTED_CODEX_SHA="$({
python3 - "$ATLAS_AGENT_SRC/atlas-release.toml" <<'PY'
import sys, tomllib
from pathlib import Path

release = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for binary in release["codex"]["binaries"]:
    if binary["target"] == "x86_64-unknown-linux-gnu":
        print(binary["sha256"])
        break
else:
    raise SystemExit("no qualified x86_64 Linux Codex binary in release manifest")
PY
})"

ACTUAL_CODEX_SHA="$(sha256sum "$ATLAS_CODEX_EXECUTABLE" | awk '{print $1}')"

printf 'expected %s\nactual   %s\n' "$EXPECTED_CODEX_SHA" "$ACTUAL_CODEX_SHA"
test "$ACTUAL_CODEX_SHA" = "$EXPECTED_CODEX_SHA"
```

If this fails, stop.

Do **not** change `atlas-release.toml` merely to accept whatever executable is
present on the machine.

### 6.4 If no qualified binary is available

Normal project deployment stops here.

Building Codex from the recorded source commit is not equivalent to obtaining
the already qualified binary: a rebuild can produce different bytes and
therefore a different SHA-256 even from the same source tree.

A newly built binary must be deliberately qualified and pinned through the
release process before it becomes a production Atlas runtime.

This is a release-maintainer operation, not a normal project-start procedure.
The future `atlas-agent install` command should normally obtain a published,
prequalified binary artifact instead.

### 6.5 Provision the canonical v0.1.1 CODEX_HOME

The v0.1.1 source release contains the canonical assets and an internal atomic
provisioning function.

Create only the parent directory first:

```bash
mkdir -p "$(dirname "$ATLAS_CODEX_HOME")"
test ! -e "$ATLAS_CODEX_HOME"
```

Then provision the complete authoritative asset set:

```bash
PYTHONPATH="$ATLAS_AGENT_SRC" python3 - <<'PY'
import os
from pathlib import Path
from tools.atlas_agent.assets import provision_codex_assets

agent = Path(os.environ["ATLAS_AGENT_SRC"])
home = Path(os.environ["ATLAS_CODEX_HOME"])
source = agent / "codex-assets" / "v0.1.1"
print(provision_codex_assets(source, home))
PY
```

The operation validates the canonical source, copies the complete set into a
sibling staging directory, validates the staged bytes, and publishes the fresh
CODEX_HOME atomically.

It intentionally refuses an existing destination rather than partially
updating it.

### 6.6 Authentication remains separate mutable state

The canonical CODEX_HOME does not include credentials.

If the operator's normal Codex authentication is stored at:

```text
~/.codex/auth.json
```

verify that it exists and is readable without printing its contents:

```bash
test -r "$HOME/.codex/auth.json" && echo "Codex auth readable"
```

Then add a reference after canonical asset provisioning:

```bash
ln -s "$HOME/.codex/auth.json" "$ATLAS_CODEX_HOME/auth.json"

readlink "$ATLAS_CODEX_HOME/auth.json"
readlink -f "$ATLAS_CODEX_HOME/auth.json"
test -r "$(readlink -f "$ATLAS_CODEX_HOME/auth.json")"
```

This keeps the release assets versioned and immutable while authentication can
be refreshed independently.

Do not copy the secret into `codex-assets/`, commit it, print it, or include its
contents in release hashes.

### 6.7 Temporary v0.1.1 shell command

Until the public installer creates a stable executable, define a bash helper
for the selected release:

```bash
atlas_agent() {
    PYTHONPATH="$ATLAS_AGENT_SRC${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m tools.atlas_agent "$@"
}
```

The two runtime variables must also remain exported in the shell which launches
Atlas:

```bash
export ATLAS_CODEX_EXECUTABLE
export ATLAS_CODEX_HOME
```

Check the public executor boundary:

```bash
atlas_agent executor-info
```

A healthy Linux installation should report the Atlas Bubblewrap executor as
available and should resolve the intended native Codex executable.

---

## 7. Manual installation diagnostic for v0.1.1

This section is the temporary replacement for `atlas-agent install-doctor`.
It should not depend on any project's `.git/atlas-agent` journal.

### 7.1 Static checks

Run:

```bash
test -d "$ATLAS_AGENT_SRC"
test -f "$ATLAS_AGENT_SRC/atlas-release.toml"
test -x "$ATLAS_CODEX_EXECUTABLE"
test -d "$ATLAS_CODEX_HOME"
command -v git
command -v python3
command -v bwrap
```

Verify the Agent release again:

```bash
test "$(git -C "$ATLAS_AGENT_SRC" rev-parse HEAD)" = \
     "$(git -C "$ATLAS_AGENT_SRC" rev-parse "$ATLAS_AGENT_TAG^{}")"
```

Verify the Codex executable again:

```bash
test "$(sha256sum "$ATLAS_CODEX_EXECUTABLE" | awk '{print $1}')" = \
     "$EXPECTED_CODEX_SHA"
```

Verify the mutable authentication reference without opening the credential:

```bash
test -L "$ATLAS_CODEX_HOME/auth.json"
test -r "$(readlink -f "$ATLAS_CODEX_HOME/auth.json")"
```

Verify that the canonical installed files still match their source release:

```bash
for name in \
    config.toml \
    models-atlas-shell-only.json \
    atlas-luna-local.config.toml \
    atlas-luna-web.config.toml \
    atlas-sol-local.config.toml \
    atlas-sol-web.config.toml \
    atlas-agent-prompts/common.md \
    atlas-agent-prompts/state_audit.md
do
    cmp -s \
        "$ATLAS_AGENT_SRC/codex-assets/v0.1.1/$name" \
        "$ATLAS_CODEX_HOME/$name" || {
        echo "asset mismatch: $name" >&2
        return 1 2>/dev/null || exit 1
    }
done

echo "canonical Atlas Codex assets: OK"
```

Finally:

```bash
atlas_agent executor-info
```

### 7.2 Zero-token host qualification

The future `install-doctor` should also perform a zero-token live probe of the
real production chain:

```text
qualified Codex binary
→ sealed runtime authority
→ stable Atlas runtime path
→ Bubblewrap
→ Codex exec-server
→ codex-linux-sandbox helper dispatch
→ /bin/true
→ exit 0
→ confirmed reap and cleanup
```

v0.1.1 does not yet expose that probe as a public install command. A release or
development environment with the test dependencies installed can run the live
Bubblewrap qualification tests, but ordinary project users should not need
pytest once `install-doctor` exists.

### 7.3 Authenticated diagnostic

An authenticated diagnostic is a separate, optional level because it consumes
model tokens.

It proves that the host-side Codex controller can use the user's authentication
and complete a minimal real model execution. It should not be confused with the
sandbox's `network_access` capability described later.

For an already release-qualified host, this diagnostic does not need to be
repeated for every project.

---

## 8. Reuse an already installed host

If the machine already has the selected Atlas Agent release, exact Codex binary,
versioned CODEX_HOME, authentication reference, and working Bubblewrap backend,
do not reinstall them for every project.

Re-establish the release variables or use the future installed command:

```bash
export ATLAS_AGENT_SRC="$HOME/.local/share/atlas-agent/releases/atlas-agent-v0.1.1"
export ATLAS_CODEX_HOME="$HOME/.local/share/atlas-agent/codex-homes/v0.1.1"
export ATLAS_CODEX_EXECUTABLE="/absolute/path/to/qualified/codex"

atlas_agent() {
    PYTHONPATH="$ATLAS_AGENT_SRC${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m tools.atlas_agent "$@"
}

atlas_agent executor-info
```

Machine installation and project initialization are independent operations.

---

## 9. Inspect the target project before changing it

Move to the existing project:

```bash
cd /path/to/project
```

Confirm that it is the intended repository root:

```bash
git rev-parse --show-toplevel
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
```

Read project instructions and normal development documentation before asking an
agent to modify the repository.

Typical files include:

```text
AGENTS.md
CLAUDE.md
CODEX.md
README*
CONTRIBUTING*
developer/build/test documentation
```

Project instructions guide the task but do not enlarge Atlas security
capabilities.

### 9.1 Dirty repositories

A pre-existing dirty repository is not automatically invalid, but it makes the
initial witness harder to reason about.

For a first deployment, prefer a known stable boundary and understand every
pre-existing modification and untracked file before `init`.

Atlas records the repository state at initialization. Unexplained changes after
that boundary can correctly produce `REPOSITORY_WITNESS_MISMATCH`.

### 9.2 Verify the Git topology

The v0.1.1 Bubblewrap backend requires a real `.git` directory at the repository
root:

```bash
test -d .git && echo "ordinary .git directory: OK"
```

If `.git` is a file, the repository is probably a linked worktree. Workflow
metadata commands may still understand Git's worktree paths, but Atlas
Bubblewrap execution currently rejects that topology with:

```text
ATLAS_SANDBOX_GIT_TOPOLOGY_UNSUPPORTED
```

Use a normal standalone clone for execution rather than weakening this check.

### 9.3 Project-local Codex configuration is currently unsupported

Check:

```bash
test ! -f .codex/config.toml || {
    echo "project .codex/config.toml must be resolved before Atlas execution" >&2
    false
}
```

Atlas intentionally refuses to silently merge arbitrary project Codex
configuration with its qualified runtime configuration.

Do not delete an existing project configuration merely to make Atlas pass.
Understand why it exists and decide deliberately how the project should be
adapted.

---

## 10. Install the project policy before `init`

A v2 Atlas prompt requires `atlas-agent-policy.toml` in the target repository.
`atlas-agent init` currently initializes workflow state; it does **not** copy the
policy file for you.

This ordering matters:

```text
prepare project configuration
→ stabilize/commit intended baseline
→ atlas-agent init
```

Do not initialize first and then casually add the policy, because `init` records
the repository witness.

### 10.1 New Atlas project

If the project has no policy yet, start from the policy shipped with the exact
Agent release:

```bash
test ! -e atlas-agent-policy.toml
cp "$ATLAS_AGENT_SRC/atlas-agent-policy.toml" ./atlas-agent-policy.toml
```

Review it before accepting it:

```bash
sed -n '1,220p' atlas-agent-policy.toml
git diff -- atlas-agent-policy.toml
```

The policy contains runtime identities and action capabilities. Do not replace
its Codex hashes with locally convenient values.

### 10.2 Existing policy

If `atlas-agent-policy.toml` already exists, do not overwrite it automatically.
Determine whether the project was previously initialized with another Atlas
release and treat that as an explicit upgrade/migration case.

### 10.3 Commit or otherwise stabilize the baseline

The recommended normal project setup is to track the policy in Git and commit
it before Atlas initialization using the project's ordinary review process.

For example, after reviewing the change:

```bash
git add atlas-agent-policy.toml
git status --short
# commit according to the project's normal policy
```

Do not accidentally include unrelated dirty files in the deployment commit.

If a project deliberately keeps the policy untracked, Atlas can record that
state as part of the initial witness, but the file must then remain stable. This
is less clear operationally and is not the recommended default.

---

## 11. Initialize Atlas for the project

Choose the stable project boundary first. Then run:

```bash
atlas_agent init
```

Atlas project runtime state is stored through Git's Atlas metadata path,
conceptually:

```text
.git/atlas-agent/
```

Do not create or edit that directory by hand.

Immediately verify the fresh project:

```bash
atlas_agent doctor
atlas_agent status
atlas_agent executor-info
```

A healthy fresh project should show:

```text
journal: OK
state: MATCH
repository witness: MATCH
```

and `doctor` should report OK.

`executor-info` is useful here because it reports the selected Atlas execution
backend, but remember that it is not yet a complete replacement for the future
machine-level `install-doctor`.

---

## 12. Important network distinction

Atlas has two different reasons for network traffic.

### 12.1 Controller/provider connectivity

The host-side Codex controller needs provider connectivity to authenticate and
obtain model responses.

That connectivity is necessary even for a task whose sandbox capability says:

```toml
network_access = false
```

### 12.2 Task execution capability

The prompt field `network_access` is an Atlas capability request for the task's
execution profile. It affects the selected Atlas/Codex profile and the authority
available to model-controlled execution.

Therefore:

```text
network_access = false
```

does **not** mean "the host must be offline". It means that the task does not
receive Atlas network authority merely because the controller itself must reach
the model service.

For v0.1.1:

* `implementation` may explicitly request network access;
* `patch_review` forbids it;
* `state_audit` forbids it.

The project policy is authoritative.

---

## 13. First project prompt

Once installation, policy, initialization, and diagnostics are all clean, create
the first useful task.

Do not put prompt files in the application source tree. Use the Atlas inbox:

```bash
RUNTIME="$(git rev-parse --git-path atlas-agent)"
PROJECT_HEAD="$(git rev-parse HEAD)"
```

For a first implementation generation:

```bash
cat > "$RUNTIME/inbox/g000001-first-task.txt" <<EOF
+++
schema = "atlas-agent-prompt/2"
generation = 1
parent = "genesis"
checkpoint = "first-task"
action = "implementation"
expected_head = "$PROJECT_HEAD"
session_mode = "fresh"
network_access = false
+++
Describe the concrete bounded implementation task here.

Respect the project's existing instructions and tests.
Do not commit, tag, or push unless the task explicitly delegates that authority.
EOF
```

Then ingest it:

```bash
atlas_agent ingest
atlas_agent status
```

Before dispatch, generation 1 should be `ACCEPTED` and the repository witness
should still match.

Run exactly one accepted generation:

```bash
atlas_agent dispatch
```

`dispatch` resolves the model, reasoning level, sandbox, network policy, Codex
profile, and binary identity from the Atlas policy snapshot. A normal user does
not need to pass `--model` or `--sandbox` for ordinary policy-controlled work.

---

## 14. Verify the first execution

After dispatch:

```bash
atlas_agent status
atlas_agent doctor
atlas_agent report 1
git status --short
```

Check all of the following:

* the generation reached the expected terminal state;
* the intended model/profile was selected;
* the sandbox mode matches policy;
* network authority matches the prompt and policy;
* only intended project files changed;
* the repository witness remains coherent;
* the execution report is available when expected;
* the task result itself is semantically correct.

A lifecycle state such as `COMPLETED` and a process exit code of zero establish
execution lifecycle facts. They do not by themselves prove that the requested
software change is correct. Inspect the actual result, diff, and tests.

---

## 15. First review cycle

The normal first real deployment should exercise a bounded but useful project
cycle rather than only Atlas internals:

```text
implementation with Luna
        ↓
project tests
        ↓
read-only patch review with Sol
        ↓
correction if needed
        ↓
review/checkpoint according to project workflow
```

For the second generation, use the same prompt format with:

```toml
generation = 2
parent = 1
action = "patch_review"
session_mode = "fresh"
network_access = false
```

and an `expected_head` matching the repository HEAD required by the workflow.
The review profile is read-only and its network capability is forbidden by the
v0.1.1 policy.

For lifecycle details beyond initial deployment, see `docs/agent-workflow.md`.

---

## 16. When to run a synthetic authenticated smoke

A synthetic authenticated smoke should normally be a **machine installation
check**, not generation 1 of every user project.

Once `install-doctor --authenticated` exists, use that.

With v0.1.1 manual deployment, a new host can be checked in a disposable
standalone clone so the user's real project journal remains meaningful.

For example, create a fresh independent clone rather than a linked worktree:

```bash
SMOKE_PARENT="$(mktemp -d)"
git clone --no-hardlinks "$ATLAS_AGENT_SRC" "$SMOKE_PARENT/atlas-smoke"
cd "$SMOKE_PARENT/atlas-smoke"
git switch --detach "$ATLAS_AGENT_TAG"
```

Then initialize a new Atlas journal and use a minimal implementation prompt that
invokes `true` exactly once and returns a fixed marker.

A valid smoke should verify the **actual recorded command execution**, not only
the model's final text response.

Do not use a linked Git worktree for this smoke because the current Bubblewrap
backend rejects that Git topology.

Once the host has been qualified, ordinary new projects do not need to spend
model tokens repeating the same synthetic smoke.

---

## 17. Repository state after initialization

Atlas is witness-based. This has an important operational consequence:

**perform deliberate baseline repository changes before `init`.**

After initialization, manually changing HEAD, the index, tracked content, or
unexpected untracked state outside the expected Atlas lifecycle can cause a
repository witness mismatch.

This is useful: Atlas should notice when the repository changed outside the
state it recorded.

Do not "fix" a mismatch by deleting the journal or rewriting witness evidence.
Determine what changed and use the workflow's recovery or project migration
procedure as appropriate.

---

## 18. Existing project instructions versus Atlas authority

Atlas operates with several instruction layers:

```text
controller-owned Atlas policy
        ↓ capability ceiling
Atlas action/profile
        ↓ model/runtime selection
project instructions
        ↓ task conventions and repository knowledge
user task prompt
        ↓ requested work
```

Project files such as `AGENTS.md`, READMEs, generated text, web content, or model
output can influence the task but do not enlarge the controller-owned Atlas
capability ceiling.

Do not weaken Atlas policy because project prose requests more authority.

---

## 19. Authentication lifecycle

The recommended v0.1.1 layout keeps authentication outside the versioned Atlas
asset set:

```text
~/.codex/auth.json
        ↑
        └── ~/.local/share/atlas-agent/codex-homes/v0.1.1/auth.json
```

If authentication expires or is refreshed, update the user's normal credential
through the normal authentication mechanism. The Atlas CODEX_HOME symlink can
continue to reference it.

Do not provision a new canonical asset directory merely because the user's
credential changed.

The host-side Codex controller consumes authentication. The model-generated
process inside the Atlas Bubblewrap environment does not need a copy of the
operator's normal CODEX_HOME.

---

## 20. Troubleshooting by symptom

### `POLICY_CONFIG_REQUIRED`

The project does not have the required `atlas-agent-policy.toml`, or Atlas was
initialized before project policy setup was completed.

Use the exact policy for the selected release and establish a deliberate project
baseline before initialization.

### `POLICY_SCHEMA_INVALID`

The project policy or a policy snapshot does not match the release schema.

Do not patch random fields until the error disappears. Compare with the policy
shipped by the selected Atlas Agent release.

### `CODEX_NOT_FOUND`

`ATLAS_CODEX_EXECUTABLE` is absent, wrong, or does not identify an executable
runtime.

### `CODEX_EXECUTABLE_DIGEST_MISMATCH`

The selected executable bytes do not match the SHA-256 pinned by policy.

Common causes:

* PATH resolved an unrelated Codex installation;
* the binary was rebuilt;
* the wrong platform artifact was selected;
* the executable was modified after qualification.

Do not update the pin just to accept the mismatch.

### `CODEX_CONFIG_DIGEST_MISMATCH`, `CODEX_CATALOG_DIGEST_MISMATCH`, or `CODEX_PROFILE_DIGEST_MISMATCH`

The versioned CODEX_HOME does not contain the exact release configuration.
Reprovision a **fresh** versioned home from the canonical release source rather
than incrementally repairing unknown state.

### Authentication failure

Check only metadata first:

```bash
ls -l "$ATLAS_CODEX_HOME/auth.json"
readlink -f "$ATLAS_CODEX_HOME/auth.json"
test -r "$(readlink -f "$ATLAS_CODEX_HOME/auth.json")"
```

Do not print the credential file.

### `ATLAS_SANDBOX_BWRAP_NOT_FOUND`

Bubblewrap is not installed or not discoverable.

### `ATLAS_SANDBOX_NAMESPACE_UNAVAILABLE`

Bubblewrap exists but the host does not permit the namespace operation required
by Atlas. This is a host/runtime issue, not a prompt issue.

### `ATLAS_SANDBOX_GIT_TOPOLOGY_UNSUPPORTED`

The target is not an ordinary repository with a real root `.git/` directory.
A linked worktree is the common cause. Use a standalone clone for the current
backend.

### `CODEX_PROJECT_CONFIG_UNSUPPORTED`

The project contains `.codex/config.toml`. Atlas refuses to merge that mutable
project configuration into its qualified Codex configuration implicitly.

### `REPOSITORY_WITNESS_MISMATCH`

The repository changed relative to Atlas's recorded boundary.

Inspect:

```bash
git status --short
git rev-parse HEAD
atlas_agent status
```

Identify the real change rather than rewriting journal evidence.

### `doctor: OK` but model execution still fails

Project workflow state and machine installation are distinct. `doctor` can be
healthy while the host has an authentication, binary, asset, Bubblewrap, or
provider-connectivity problem.

Run the manual installation diagnostics in section 7. The future
`install-doctor` command exists specifically to close this usability gap.

### Old or copied journal fails validation

Do not copy workflow history between projects.

A journal created by old development code may also be historically incompatible
with a newer durable schema even when the release itself is correct. Preserve
historical evidence; use a fresh project initialization rather than mutating old
journal lines to make validation pass.

---

## 21. Upgrading an existing Atlas project

An Atlas upgrade is not the same as ordinary project work.

Keep the release dimensions explicit:

```text
old Atlas Agent release
+ old matching Codex runtime/assets
+ old project policy and workflow state

              ↓ deliberate upgrade

new Atlas Agent release
+ matching qualified Codex runtime/assets
+ reviewed project policy
+ verified workflow compatibility or migration
```

Do not automatically follow `develop/core-v1`, Codex `main`, or another moving
branch.

A new Agent release may intentionally reuse the same Atlas Codex source and
binary. Conversely, a new Codex binary identity requires qualification even if
the source commit did not change.

Before changing the policy or runtime used by an already initialized project,
reach a stable workflow boundary and follow the migration instructions for the
new release. Do not overwrite the project policy or journal blindly.

---

## 22. What `atlas-agent install` should eventually automate

This is the implementation contract implied by the manual deployment above.
The eventual machine installer should:

1. select an explicit Atlas Agent release, not a moving branch;
2. verify the Agent tag and release manifest;
3. identify the local platform;
4. obtain the exact prequalified Atlas Codex binary for that target;
5. verify its SHA-256 before making it active;
6. provision a fresh versioned canonical CODEX_HOME atomically;
7. verify asset, prompt, catalog, configuration, and profile identities;
8. attach mutable authentication without copying secret bytes into canonical
   assets;
9. verify Bubblewrap availability and basic host prerequisites;
10. install a stable `atlas-agent` command without requiring `PYTHONPATH` shell
    plumbing;
11. be idempotent when the exact release is already correctly installed;
12. refuse ambiguous, partial, or identity-mismatched existing installations.

It should not initialize any particular project journal.

---

## 23. What `atlas-agent install-doctor` should eventually verify

Installation diagnostics should be read-only and layered.

### Level 1 — static installation identity

Verify:

```text
Atlas Agent release/tag/commit
release manifest
native Codex executable
Codex binary SHA-256
versioned CODEX_HOME
canonical asset bytes
prompt/profile identities
authentication reference metadata
Bubblewrap executable
host platform
```

### Level 2 — zero-token runtime qualification

Exercise the real local chain without a model call:

```text
sealed exact Codex runtime
→ stable Atlas runtime materialization
→ Bubblewrap namespace
→ exec-server
→ helper dispatch
→ /bin/true
→ exit 0
→ reap and cleanup
```

### Level 3 — optional authenticated smoke

With explicit user intent, consume a small number of model tokens to prove:

```text
real authentication
→ provider request
→ expected model/profile
→ one bounded tool execution
→ recorded successful result
```

The default installation doctor should not consume tokens merely to repeat a
check that can be performed locally.

---

## 24. Minimal deployment checklist

For the current manual Linux v0.1.1 path:

```text
MACHINE — once
[ ] exact Atlas Agent release checked out
[ ] release manifest read
[ ] exact native Codex binary selected
[ ] Codex SHA-256 matches manifest
[ ] fresh versioned CODEX_HOME provisioned
[ ] canonical assets match
[ ] auth.json reference readable
[ ] Bubblewrap available
[ ] executor-info healthy
[ ] optional/new-host runtime smoke qualified

PROJECT — once
[ ] ordinary standalone Git repository
[ ] existing repository state understood
[ ] no unresolved project .codex/config.toml
[ ] atlas-agent-policy.toml reviewed and stabilized
[ ] intended baseline committed/stable
[ ] atlas-agent init
[ ] atlas-agent doctor: OK
[ ] status witness MATCH

FIRST REAL TASK
[ ] prompt v2 created in Atlas inbox
[ ] ingest accepted the intended generation
[ ] dispatch used expected policy/profile
[ ] result/report inspected
[ ] project diff inspected
[ ] doctor/status still coherent
[ ] review/checkpoint cycle performed as appropriate
```

---

## 25. Guiding principle

A project user should eventually need to understand only this:

```text
install one validated Atlas Agent release on the machine
        +
verify that installation
        +
initialize a clean project-specific workflow boundary
        +
submit bounded tasks through policy-controlled profiles
```

They should **not** need knowledge of the Atlas development checkout, historical
journals, Codex fork development branches, release-build archaeology, or the
manual sequence used by maintainers to qualify a release.

If ordinary project deployment requires that knowledge, installation or
diagnostics are still incomplete and should be improved rather than documented
as permanent user ritual.
