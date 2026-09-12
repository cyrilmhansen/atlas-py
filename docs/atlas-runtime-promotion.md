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
