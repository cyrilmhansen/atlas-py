# Deploying Atlas Agent into an existing project

This document describes how to deploy a validated Atlas Agent release into an existing Git repository.

It is intended to be usable by either a human operator or another coding agent without requiring knowledge of Atlas Agent's development history.

The deployment must preserve a simple rule:

> Do not independently select the newest Atlas Agent and newest Codex build. Use a pair that has been validated together.

## 1. Release identities

A validated Atlas Agent release should identify:

```text
Atlas Agent release/tag
Atlas Agent commit resolved from that tag

Codex upstream commit
Codex upstream release tag, when applicable
Atlas Codex tag and exact commit
Atlas Codex binary SHA-256 for each validated target

Codex configuration SHA-256
model catalog SHA-256
profile identities/SHA-256 values
```

When a machine-readable Atlas release manifest is available, it is authoritative.

For example:

```text
atlas-release.toml
```

Conceptually:

```toml
schema = "atlas-release/1"

atlas_agent_tag = "atlas-agent-v0.1.0"

[codex]
upstream_commit = "<upstream-commit>"
# upstream_tag = "rust-v0.152.0"  # only when this is the actual release base

atlas_tag = "atlas-v0.152.0-1"
atlas_commit = "<atlas-codex-commit>"

config_sha256 = "<sha256>"
catalog_sha256 = "<sha256>"

[[codex.binaries]]
target = "x86_64-unknown-linux-gnu"
sha256 = "<sha256>"

[[codex.binaries]]
target = "aarch64-unknown-linux-gnu"
sha256 = "<sha256>"
```

Do not replace any of these values with a newer release unless that combination has been explicitly validated.

`atlas_agent_tag` identifies the Atlas Agent source release. Its Git commit is
resolved from that tag rather than stored in the manifest itself, avoiding a
circular dependency between the manifest contents and the commit containing it.

`codex.upstream_commit` is mandatory. `codex.upstream_tag` is optional and must
only be present when that tag is the actual base of the Atlas Codex patch stack.

## 2. Repository locations

Atlas Agent source:

```text
https://github.com/cyrilmhansen/atlas-py
```

Atlas Codex fork:

```text
https://github.com/cyrilmhansen/codex
```

Use release tags or exact commits.

Do not deploy from an arbitrary moving branch such as `main` or a development branch when a validated release identity exists.

## 3. Determine whether the host is already provisioned

Before installing anything, check whether Atlas Agent and the Atlas Codex runtime already exist on the host.

Typical checks:

```bash
command -v atlas-agent || true
atlas-agent --help 2>/dev/null | head || true

test -x "$HOME/.local/share/atlas-agent/codex-home/../"* 2>/dev/null || true
test -d "$HOME/.local/share/atlas-agent/codex-home" && \
  echo "Atlas CODEX_HOME present"
```

If the host already contains the validated Atlas Agent/Codex pair, prefer verifying it rather than reinstalling it.

Deployment into a new project and provisioning a new host are separate operations.

## 4. Provisioning Atlas Agent on a new host

Fetch the exact validated Atlas Agent release:

```bash
git clone https://github.com/cyrilmhansen/atlas-py.git atlas-agent
cd atlas-agent

git fetch --tags
git checkout <ATLAS_AGENT_TAG>
```

Verify the checkout:

```bash
git status --short
git rev-parse HEAD
git describe --tags --exact-match
```

The commit must match the validated Atlas release manifest.

Install Atlas Agent using the installation mechanism documented by that release.

Do not silently substitute another checkout or development branch if installation fails.

## 5. Provisioning the Atlas Codex runtime

Fetch the exact Codex Atlas release specified by the Atlas Agent release:

```bash
git clone https://github.com/cyrilmhansen/codex.git codex-atlas
cd codex-atlas

git fetch --tags
git checkout <ATLAS_CODEX_TAG>
```

Verify:

```bash
git status --short
git rev-parse HEAD
git describe --tags --exact-match
```

### If a validated binary artifact is provided

Prefer the validated release artifact.

Verify its SHA-256 before installation:

```bash
sha256sum codex
```

The result must exactly match the SHA-256 recorded by the Atlas release manifest.

The deployment agent must select a binary matching the host platform and verify
the SHA-256 associated with that exact target. A SHA-256 recorded for another
architecture or operating system is not valid for the local executable.


## Platform support

| Platform | Atlas Codex | Atlas isolation backend |
| --- | --- | --- |
| Linux x86_64 | supported | Bubblewrap |
| Linux ARM64 | expected; requires validation | Bubblewrap |
| macOS ARM64 | Codex build possible | Atlas isolation backend not yet implemented |
| macOS x86_64 | Codex build possible | Atlas isolation backend not yet implemented |

Atlas Agent's current hardened execution backend is Linux-specific. Codex
itself being portable does not imply that the complete Atlas execution boundary
is portable.

### If Codex must be built from source

A development build may be used while testing the port or installation:

```bash
cd codex-rs
cargo build -p codex-cli
```

Development executable:

```text
target/debug/codex
```

For the production Atlas runtime, build:

```bash
cargo build --release -p codex-cli
```

Production executable:

```text
target/release/codex
```

Record and verify:

```bash
./target/release/codex --version
sha256sum ./target/release/codex
```

Atlas Agent must use the exact SHA-256 of the validated production binary.

A locally rebuilt binary must therefore be explicitly accepted and pinned before it becomes the Atlas runtime.

## 6. Codex configuration and profiles

Atlas uses a dedicated Codex home rather than the operator's normal Codex configuration.

Expected location:

```text
~/.local/share/atlas-agent/codex-home
```

The validated deployment includes or identifies:

```text
config.toml
models-atlas-shell-only.json
Atlas Codex profiles
```

Typical profiles include separate local/web and Luna/Sol configurations.

Their identities must match the Atlas Agent policy pins.

Do not copy settings from the operator's normal `~/.codex` into the Atlas Codex home.

Do not enable additional tools or features merely because they are available in upstream Codex.

The Atlas policy and validated Codex profiles define the intended execution surface.

## 7. Inspect the target project before initialization

Move to the project that will use Atlas Agent:

```bash
cd /path/to/project

git status
git branch --show-current
git remote -v
```

Record:

* current branch;
* existing modified files;
* existing untracked files;
* repository-specific agent instructions;
* existing development/build/test commands;
* whether the project already contains Atlas metadata.

Atlas Agent must be introduced without silently rewriting or discarding existing project state.

A pre-existing dirty working tree is not automatically an error, but it must be understood before Atlas is initialized.

## 8. Check repository instructions

Inspect relevant project instructions before asking Atlas to perform work:

```bash
find .. -name AGENTS.md -o -name CLAUDE.md -o -name CODEX.md 2>/dev/null
```

Also inspect project documentation such as:

```text
README
CONTRIBUTING
developer documentation
test/build documentation
```

The deployment agent should distinguish:

1. project instructions;
2. Atlas Agent control policy;
3. semantic task instructions supplied to Luna or Sol.

Project instructions do not override Atlas security boundaries.

## 9. Initialize Atlas Agent in the target repository

Initialization should create only the Atlas project-level configuration required by the selected release.

Atlas runtime state belongs under the repository's Git metadata rather than being mixed with application source when possible.

Typical Atlas state location:

```text
.git/atlas-agent/
```

Project configuration may include:

```text
atlas-agent.toml
atlas-agent-policy.toml
```

Use the initialization command documented by the selected Atlas Agent release.

Do not copy state or journal history from another project.

A new project receives a new Atlas workflow history.

## 10. Configure repository-specific exceptions deliberately

Some repositories legitimately contain generated, ignored, or untracked material.

If Atlas requires repository-specific declarations such as allowed untracked paths, inspect those paths before adding them.

For example:

```toml
allowed_untracked = [
    "some/generated/path/",
]
```

Do not add broad exceptions merely to make validation pass.

The deployment itself is intended to expose assumptions Atlas may incorrectly make about existing repositories.

Record such friction rather than immediately weakening policy.

## 11. Validate policy resolution before real work

Before assigning a meaningful task, verify that Atlas resolves the intended execution policies.

Expected conceptual policy:

```text
implementation
    model: Luna
    sandbox: workspace-write
    network: explicit according to policy
    tools: implementation profile

patch review
    model: Sol
    sandbox: read-only
    network: forbidden unless explicitly designed otherwise

state audit
    model: Sol
    session: fresh
    sandbox: read-only
    network: forbidden
```

The exact release configuration is authoritative.

Do not infer authority from the prompt presented to the model.

The sandbox, Codex profile, and Atlas policy enforce authority.

## 12. First deployment test

The first test in a new repository should be a real but bounded project task.

Prefer:

```text
small implementation
        ↓
tests
        ↓
Sol patch review
        ↓
possible correction
        ↓
second review or checkpoint
```

Do not start with a synthetic Atlas-only test if a useful real project task is available.

The purpose of the second-project deployment is to expose real integration and usability problems.

## 13. Observe deployment friction

During the first several generations, record friction before changing Atlas itself.

Useful categories include:

```text
installation/provisioning
repository discovery
initialization
policy configuration
existing dirty state
allowed untracked files
project instructions
Codex profile selection
runtime verification
error diagnostics
journal/state handling
agent-facing documentation
commands that require Atlas source knowledge
```

A problem encountered once may be project-specific.

A repeated problem may justify:

```text
Atlas code change
Atlas default change
better diagnostics
documentation change
```

Do not immediately expand Atlas complexity to eliminate every deployment inconvenience.

## 14. Do not import another project's journal

Atlas lifecycle history is project-specific.

Do not copy:

```text
.git/atlas-agent/
```

from another repository.

Do not attempt to make a new deployment continue the generation numbers or execution identities of the Atlas Agent development repository.

The target project begins with its own state.

## 15. Verify the first execution

After the first Atlas-controlled execution, verify:

```bash
git status
atlas-agent status
```

Inspect the generated execution/result information as appropriate.

Confirm that:

* the expected model/profile was selected;
* the intended sandbox was used;
* network authority matches policy;
* only intended files changed;
* execution completed through the expected Atlas lifecycle;
* the repository remains understandable to a normal Git workflow.

## 16. Record project deployment provenance

The target repository should retain a small record of which Atlas runtime it was initialized and validated with.

For example:

```text
Atlas Agent tag:       <ATLAS_AGENT_TAG>
Atlas Agent commit:    <commit>

Codex upstream tag:    <UPSTREAM_CODEX_TAG>
Atlas Codex tag:       <ATLAS_CODEX_TAG>
Codex source commit:   <commit>
Codex target:          <target>
Codex binary SHA-256:  <sha256>

Deployment validated:  <date>
```

This record is informational provenance.

The actual Atlas policy/runtime SHA validation remains authoritative.

## 17. Instructions for another agent

When an agent is asked to deploy Atlas Agent into a project, it should follow these rules:

1. Read this document completely before modifying the target repository.
2. Determine the validated Atlas Agent release.
3. Read the Atlas release manifest.
4. Use the exact Codex Atlas release specified by that manifest.
5. Never pair releases based only on which tags appear newest.
6. Verify commits and SHA-256 identities before execution.
7. Inspect the existing repository before initialization.
8. Preserve existing project state.
9. Initialize a new project-specific Atlas history.
10. Run a bounded real task through the complete implementation/review cycle.
11. Record deployment friction separately from project bugs.
12. Do not weaken policy to bypass unexplained failures.
13. Do not modify Atlas Agent itself unless the deployment provides evidence that an Atlas change is required.

## 18. Updating an existing project later

Updating Atlas Agent is a separate operation from ordinary project development.

A project should move from one validated Atlas release pair to another:

```text
Atlas Agent release A
+ matching Atlas Codex release A

            ↓ explicit upgrade

Atlas Agent release B
+ matching Atlas Codex release B
```

Verify the new runtime and policy pins before performing the first execution under the new version.

Do not automatically follow moving Git branches.

## Guiding principle

Atlas deployment should be reproducible from three pieces of information:

```text
exact Atlas Agent release
        +
exact validated Atlas Codex runtime
        +
target repository
```

No knowledge of the original Atlas development repository or its historical journal should be required.
