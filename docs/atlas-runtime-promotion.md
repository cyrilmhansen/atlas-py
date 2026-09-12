# Atlas — Qualified Codex Runtime Promotion

## Purpose

This runbook describes how to promote a qualified Codex runtime into Atlas.

It is deliberately broader than an environment reconstruction procedure.

Environment reconstruction answers:

> Can we rebuild a runtime from known sources?

Qualified promotion answers:

> What lets us assert that the runtime we qualified is the runtime Atlas will
> actually execute, under the expected policy and with the expected observable
> behaviour?

The promotion chain therefore covers source identity, build identity, binary
identity, installation, policy authority, executable resolution, sandbox
materialization, feature propagation, end-to-end observation, regression
testing, evidence retention, and rollback.

A successful rebuild is an input to promotion. It is not sufficient evidence
of a successful promotion.

---

## Trust chain

The expected chain is:

```text
qualified source revision
        ↓
release build
        ↓
exact binary SHA-256
        ↓
versioned installed runtime
        ↓
ATLAS_CODEX_EXECUTABLE
        ↓
Atlas policy codex_binary_sha256
        ↓
native-runtime resolution
        ↓
sealed runtime FD
        ↓
/opt/atlas-codex inside Bubblewrap
        ↓
actual Codex launch
        ↓
observed model boundary
        ↓
end-to-end witness
```

Every transition must either preserve identity or be independently checked.

`/opt/atlas-codex` is an internal Bubblewrap path. It is not the host
installation path.

---

## 1. Freeze the qualified candidate

Before promotion, record the exact source state:

```bash
git status --short
git rev-parse HEAD
git log --decorate --oneline -5
```

For a customized Codex build, retain at minimum:

- upstream release/tag and commit;
- Atlas-specific commits;
- any runtime extension commits;
- the working-tree cleanliness state.

Do not promote a build whose source identity is ambiguous.

---

## 2. Disk-space preflight

Rust release builds can consume tens of gigabytes, especially when debug and
release artifacts from multiple worktrees coexist.

Check the filesystem that will contain Cargo's target directory:

```bash
df -h /
df -h /tmp
du -sh path/to/codex-rs/target 2>/dev/null
```

Do not assume `/tmp` is backed by the root filesystem. It may be a relatively
small `tmpfs`.

Prefer a build location with explicit capacity, or set a suitable
`CARGO_TARGET_DIR`.

Old `target/debug` trees and build artifacts from completed comparison
worktrees are disposable once their qualification evidence has been recorded.
Source worktrees and commits are not.

---

## 3. Build the release runtime

From the qualified Codex source:

```bash
cd codex-rs
cargo build --release -p codex-cli
```

Record the resulting artifact:

```bash
BIN="$PWD/target/release/codex"

ls -lh "$BIN"
sha256sum "$BIN"
"$BIN" --version
```

If Atlas depends on a custom CLI extension, verify its public contract before
promotion. For example:

```bash
"$BIN" exec --help | grep -A3 -B2 'image-detail'
```

The release binary SHA-256 is the runtime identity used by Atlas policy.

---

## 4. Install without destroying the previous runtime

Use a versioned release directory and keep the executable basename exactly
`codex`:

```text
releases/<release-id>/codex
```

Example:

```bash
RELEASE_ID=atlas-codex-YYYYMMDD-N
CANDIDATE=/absolute/path/to/target/release/codex
NEW_RUNTIME=/absolute/path/to/releases/$RELEASE_ID/codex

mkdir -p "$(dirname "$NEW_RUNTIME")"
install -m 0755 "$CANDIDATE" "$NEW_RUNTIME"
```

The basename matters. Atlas `_native_codex()` accepts a directly supplied
native runtime only when the resolved executable is named `codex`, is
executable, and begins with the ELF magic bytes.

Do not use this form:

```text
releases/atlas-codex-YYYYMMDD-N
```

for the executable itself.

Use:

```text
releases/atlas-codex-YYYYMMDD-N/codex
```

instead.

Verify byte identity:

```bash
sha256sum "$CANDIDATE" "$NEW_RUNTIME"
cmp -s "$CANDIDATE" "$NEW_RUNTIME"
```

Keep the previous qualified runtime intact until promotion has completed.

---

## 5. Update the policy authority

Atlas policy binds executions to the exact runtime bytes through
`codex_binary_sha256`.

Update every applicable Codex profile from the old qualified digest to the new
release digest.

Do this transactionally and assert the expected replacement count rather than
performing an unconstrained textual edit.

After modification:

```bash
git diff --check
git diff -- atlas-agent-policy.toml
```

The policy SHA and installed runtime SHA must agree exactly.

---

## 6. Bind the host runtime

Set the Atlas runtime to the versioned installed executable:

```bash
export ATLAS_CODEX_EXECUTABLE=/absolute/path/to/releases/<release-id>/codex
```

Verify:

```bash
sha256sum "$ATLAS_CODEX_EXECUTABLE"
"$ATLAS_CODEX_EXECUTABLE" --version
```

Also exercise the same native-runtime resolver used by Atlas:

```bash
python3 - <<'PY'
from tools.atlas_agent.bubblewrap import _native_codex
import os

p = os.environ["ATLAS_CODEX_EXECUTABLE"]
resolved = _native_codex(p)

print("requested =", p)
print("native    =", resolved)

assert resolved is not None
assert str(resolved) == p
PY
```

This check is distinct from checking the ELF header manually. It verifies the
actual Atlas admission rule.

---

## 7. Verify policy/runtime agreement before model execution

Before spending a model call, establish all cheap invariants:

```bash
sha256sum "$ATLAS_CODEX_EXECUTABLE"
grep 'codex_binary_sha256' atlas-agent-policy.toml
"$ATLAS_CODEX_EXECUTABLE" --version
git rev-parse HEAD
```

Run targeted security, sandbox, runtime, and feature tests first.

A failure at this stage is preferable to discovering a configuration mismatch
after model execution begins.

---

## Reconstruct and build the custom Codex runtime

The qualified source recipe is versioned in
`codex-runtime-recipes/atlas-codex-0.154.toml`. Reconstruction does not
re-cherry-pick patches. It resolves the exact qualified final commit already
present in the Codex source repository, verifies the upstream tag/commit and
the ordered required-commit ancestry `6b9826e3… -> 513e4a57… -> 123825e5…`, then creates a detached clean worktree:

```bash
env PYTHONPATH="$PWD" python3 -P -m tools.atlas_agent.release     reconstruct-codex     --source-repo /home/john/luna/codex-atlas     --worktree /home/john/luna/codex-atlas/builds/atlas-codex-0.154
```

Build is a separate explicit operation so reconstruction cannot unexpectedly
consume a large amount of CPU or disk:

```bash
env PYTHONPATH="$PWD" python3 -P -m tools.atlas_agent.release     build-codex     --worktree /home/john/luna/codex-atlas/builds/atlas-codex-0.154     --target-dir /home/john/luna/codex-atlas/build-targets/atlas-codex-0.154
```

`build-codex` requires the worktree to begin and end at the qualified clean
HEAD and requires the configured amount of free space (30 GiB by default).
The build recipe pins the effective `cargo --version` and `rustc --version`
identities and fails closed before compilation on a mismatch. This records
the compiler actually used by the qualified build rather than assuming that
`rust-toolchain.toml` is authoritative: a system Cargo/Rust installation can
bypass rustup toolchain-file selection.

Codex release tags intentionally carry the release version in `Cargo.toml`
while workspace entries in `Cargo.lock` can remain at `0.0.0`; Cargo therefore
refreshes those lockfile versions during a release build. Atlas accepts only
that exact semantic transformation (`0.0.0` to the recipe release version),
rejects dependency/checksum/package changes, restores the committed lockfile,
then verifies executable ELF identity, the exact expected Codex version, and
the required `exec --help` public contract (`--image-detail` with `original`
support).

The resulting `.../release/codex` is the input to `prepare-runtime`; build and
promotion remain deliberately separate gates.

## Immutable controller installation

After controller qualification and repository-boundary promotion, install the
controller from the committed Git tree rather than executing the mutable
development worktree:

```bash
env PYTHONPATH="$ATLAS_AGENT_SRC" python3 -P -m tools.atlas_agent.release     install-controller
```

The installation is created under
`~/.local/share/atlas-agent/controllers/<git-head>/`. Its `src/` tree comes
from `git archive HEAD`, excludes untracked working-tree content, rejects
symlinks and unsupported archive entries, and is made read-only. A release
manifest binds the Git HEAD/tree and snapshot digest to the currently
qualified Codex runtime, CODEX_HOME, and optional machine capability manifest.

Activate an installed release with:

```bash
env PYTHONPATH="$ATLAS_AGENT_SRC" python3 -P -m tools.atlas_agent.release     activate-controller --head <40-hex-git-head>
```

Activation atomically updates
`~/.local/share/atlas-agent/current-controller`, writes the active controller
state, and installs the managed launcher `~/.local/bin/aa`. The launcher
restores the controller-specific `ATLAS_AGENT_SRC`, `ATLAS_CODEX_EXECUTABLE`,
`ATLAS_CODEX_HOME`, and capability manifest on every invocation. It refuses
to overwrite an existing unmanaged `~/.local/bin/aa`.

Verify the stable installation from the managed project repository:

```bash
~/.local/bin/aa status --history 0
env PYTHONPATH="$ATLAS_AGENT_SRC" python3 -P -m tools.atlas_agent.release     verify-installation
```

Rollback is activation of a previously installed release. Because each
controller manifest records its qualified Codex runtime, rollback restores the
controller/runtime pair rather than only the controller source.

## Automated release checks

A built and already qualified Codex candidate can be prepared for promotion
with:

```bash
env PYTHONPATH="$PWD" python3 -P -m tools.atlas_agent.release     prepare-runtime     --candidate /absolute/path/to/target/release/codex     --release-id atlas-codex-YYYYMMDD-N
```

`prepare-runtime` requires a clean repository, validates that the candidate is
an executable ELF, installs it as `releases/<release-id>/codex`, verifies its
SHA-256 and Atlas native-runtime resolution, and updates exactly the
`codex_binary_sha256` fields of all Codex policy profiles. The old runtime is
left intact. On a preparation failure, the newly created release directory is
removed.

The command prints the exact `ATLAS_CODEX_EXECUTABLE` value for the subsequent
cutover. Commit and test the policy change before exporting that value and
running `preflight`.

The candidate controller provides read-only qualification checks:

```bash
env PYTHONPATH="$PWD" python3 -P -m tools.atlas_agent.release preflight
```

`preflight` requires a clean repository and verifies the selected Codex
runtime, policy digests, qualified Codex assets, Atlas native-runtime
resolution, filesystem free space, and no-tool smoke calls for Luna High,
Sol Medium, and Astra Medium. The smoke result is accepted only from the
final completed Codex `agent_message`.

After committing a qualified controller change and selecting it through
`ATLAS_AGENT_SRC`, the controller boundary and live cutover can be promoted
without manually copying OLD/NEW commit identifiers:

```bash
env PYTHONPATH="$ATLAS_AGENT_SRC" python3 -P -m tools.atlas_agent.release \
    promote-controller --reason "<qualification reason>"
```

The command reads the previous repository boundary from Atlas journal
authority, requires the current clean HEAD to descend from it, performs the
existing guarded boundary adoption, then requires the post-cutover status,
doctor, and native-runtime checks to pass. Re-running it on an already adopted
HEAD is an idempotent verification.

The post-cutover verification remains independently available:

```bash
env PYTHONPATH="$ATLAS_AGENT_SRC" python3 -P -m tools.atlas_agent.release \
    post-cutover
```

Neither preflight nor post-cutover modifies repository or workflow state.
`promote-controller` modifies only the Atlas repository-boundary journal/state
through the same guarded `Workflow.adopt_boundary` primitive.

---

## 8. Observe the actual launch boundary

A feature being present in Codex does not prove that Atlas propagates it.

The final witness must inspect the actual launch command immediately before
the model call and fail closed when the expected boundary is absent.

For PVC source context using original image detail, the witness must establish
at minimum:

```text
expected profile
expected model
expected reasoning effort
one or more authorized image descriptors
image descriptors included in pass_fds
--image-detail original
--image-detail appearing before the --image arguments
```

This check must inspect the real `launch_command`. A hard-coded diagnostic
message is not evidence.

The guard should execute before delegating to the actual model process.

---

## 9. End-to-end witness

Run one representative real-source witness through the complete Atlas
workflow.

The witness should cover:

```text
source corpus
→ PVC preparation
→ PVC validation
→ deterministic tablet selection
→ secure image staging
→ Atlas preparation
→ runtime identity validation
→ sealed runtime
→ Bubblewrap
→ Codex CLI
→ model
→ semantically useful response
```

Use a real architecture or source-understanding task rather than exact random
text transcription.

Exact random hexadecimal canaries are useful as OCR stress or transport
diagnostics, but they are not appropriate functional acceptance criteria for
semantic PVC qualification.

Model-to-model variation in exact identifier transcription must not be
misattributed to a runtime regression unless the difference clearly exceeds
normal model variance.

---

## 10. Full regression gate

After the end-to-end witness succeeds:

```bash
python -m pytest -q
git diff --check
git status --short
```

Acceptance requires a green full suite and a understood working-tree state.

Do not use a historical exact test count as the acceptance rule. The count may
change as coverage evolves. Record the actual count in the qualification
record.

---

## 11. Evidence to retain

A promotion record should retain enough information to reconstruct the chain
of trust without retaining disposable build trees.

Record:

```text
Atlas source commit
Codex upstream release and commit
Atlas Codex customization commits
release binary SHA-256
installed runtime path
installed runtime SHA-256
previous runtime path and SHA-256
policy commit
feature-boundary observations
targeted-test result
full-suite result
E2E witness result
known deviations or non-goals
```

Large Cargo `target/` directories are not qualification evidence.

---

## 12. Rollback

Rollback requires both sides of the trust binding to move together:

```text
runtime path
+
policy codex_binary_sha256
```

Keep the previously qualified runtime available until the new release has
passed the final gate.

To roll back:

1. restore `ATLAS_CODEX_EXECUTABLE` to the previous versioned runtime;
2. restore the previous `codex_binary_sha256` values;
3. verify `_native_codex()` resolves the previous runtime;
4. verify runtime SHA equals policy SHA;
5. run the relevant targeted tests;
6. record the rollback as a new operational event.

Do not overwrite a failed release with the previous bytes and pretend it is
the same release identity. Runtime identity is the SHA-256 of the exact bytes.

---

## Interpretation

This process is intentionally stricter than environment reconstruction.

It provides evidence not only that a runtime can be built, but that:

- the source was known;
- the produced bytes were known;
- the promoted bytes were the same bytes;
- Atlas admitted those bytes;
- policy authorized those bytes;
- the sandbox executed those bytes;
- the expected feature crossed the Atlas/Codex boundary;
- a real workload exercised the complete path;
- the rest of Atlas remained green.

That is the basis for calling a runtime **qualified and promoted**.
