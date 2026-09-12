# Atlas Codex Runtime Qualification — 2026-09-12

## Result

**PASS**

Codex 0.154.0 with the Atlas runtime customizations and PVC original-image
detail support was promoted and exercised successfully through the complete
Atlas execution path.

---

## Atlas identity

Repository checkpoint after promotion policy update:

```text
7b95667ab685c2ed38a7fbd1b01fd7787b27d73b
```

Relevant Atlas commits:

```text
b724c39  Integrate validated PVC source context into Atlas execution
5af7774  Use original image detail for PVC source context
7b95667  Qualify Codex 0.154 runtime digest
```

---

## Codex source identity

Upstream release:

```text
rust-v0.154.0
```

Upstream commit:

```text
6b9826e3aa83b1a5947db50f4332cb9c65f1b340
```

Atlas strict model-tool allowlist commit:

```text
513e4a57eb
```

Image-detail CLI extension commit:

```text
123825e5d3
```

The older proactive-delegation wording patch was not reapplied because its
effective change was already present upstream in 0.154.

---

## Release binary

Installed runtime:

```text
/home/john/luna/codex-atlas/releases/atlas-codex-20260912-1/codex
```

Version:

```text
codex-cli 0.154.0
```

SHA-256:

```text
7d88c283f15e453f75dc7038a1d880ab44e5cc4727cd007dabf7fcda8e75329c
```

The installed runtime was verified byte-for-byte against the release build
using both SHA-256 and `cmp`.

Atlas policy was updated to the same SHA-256 for all three Codex-backed
profiles.

---

## Previous qualified runtime

Previous runtime:

```text
/home/john/luna/codex-atlas/codex-rs/target/release/codex
```

Previous SHA-256:

```text
5e841fe3f20e1649a0dc9ec144a73f56a6f62bb7e566a479dc46413d36d41524
```

It remained available during promotion for rollback.

---

## Runtime-resolution finding

An initial versioned installation used:

```text
/home/john/luna/codex-atlas/releases/atlas-codex-20260912-1
```

as the executable path.

Atlas rejected it before model execution with:

```text
ATLAS_SANDBOX_CODEX_NATIVE_NOT_FOUND
```

Investigation showed that `_native_codex()` accepts a directly supplied native
runtime only when the executable basename is exactly:

```text
codex
```

and the file is executable ELF.

The release layout was therefore corrected to:

```text
/home/john/luna/codex-atlas/releases/atlas-codex-20260912-1/codex
```

The same `_native_codex()` resolver then accepted the runtime.

No model quota was consumed by the failed attempt because the failure occurred
during policy/runtime preparation.

This basename requirement is now part of the reusable promotion runbook.

---

## Build-space finding

The first release build failed with:

```text
No space left on device (os error 28)
```

The root filesystem had ample free space, but `/tmp` was a 47 GiB `tmpfs`
which was full.

At the time:

```text
/tmp/atlas-codex-original-detail/codex-rs/target   ~21 GiB
/tmp/codex-atlas-0.154/codex-rs/target             ~26 GiB
```

Removing completed comparison build artifacts and the candidate debug target
freed approximately 40 GiB. Cargo then resumed the partial release build
successfully.

Disk-capacity preflight, especially for `/tmp`, is now part of the promotion
runbook.

---

## Image-detail integration

The qualified Codex client exposes:

```text
--image-detail <IMAGE_DETAIL>
possible values: auto, low, high, original
```

Atlas was changed so that authorized PVC image context emits:

```text
--image-detail original
```

before repeated:

```text
--image /proc/self/fd/N
```

When no authorized PVC image context exists, Atlas emits neither `--image`
nor `--image-detail`.

The behavior is covered by unit tests.

---

## Targeted regression

Targeted runtime/PVC/sandbox validation after integration:

```text
316 passed, 5 skipped in 11.74s
```

An earlier focused PVC/security group after the command change also passed:

```text
115 passed in 10.15s
```

---

## Final real-source E2E witness

Source:

```text
tools/atlas_agent/codex_executor.py
```

PVC normal profile produced three deterministic source tablets.

Observed model boundary:

```text
profile=atlas-luna-local
model=gpt-5.6-luna
reasoning=medium
images=3 ['/proc/self/fd/6', '/proc/self/fd/7', '/proc/self/fd/8']
pass_fds=[11, 6, 7, 8]
image_detail=original
```

Model execution:

```text
exit=0
model elapsed=29.4s
workflow elapsed=38.6s
```

The response gave a coherent semantic description of runtime preparation,
launch, resource lifecycle, and execution invariants.

Notably, the final response correctly identified `subprocess.Popen`, improving
on some earlier model-variable source-name guesses observed during exploratory
A/B testing.

Witness result:

```text
A2.2 REAL SOURCE E2E WITNESS COMPLETE
```

---

## PVC interpretation

Exact random hexadecimal canaries were found to be an adversarial OCR test.
Both older and newer Codex/model combinations could garble them despite
successful multimodal transport.

They are therefore classified as transport/OCR stress diagnostics, not as
functional acceptance criteria for PVC.

Functional acceptance uses real source material and semantic architecture
questions.

Exact identifier or function-name transcription remains best-effort and
model-variable unless independently constrained.

Runtime A/B differences should only be attributed to the runtime when they
clearly exceed expected model variance.

---

## Full Atlas regression

Final full suite:

```text
1121 passed in 60.96s
```

Additional final checks:

```text
git diff --check    PASS
tracked working tree clean
```

Untracked exploratory/qualification artifacts intentionally remained outside
the release checkpoint:

```text
.pi/
pvc_a22_real_witness.py
pvc_a22_witness.py
```

---

## Qualification conclusion

The qualified chain is:

```text
Codex upstream 0.154.0
+ Atlas Codex customizations
+ --image-detail original support
        ↓
release binary SHA-256
7d88c283f15e453f75dc7038a1d880ab44e5cc4727cd007dabf7fcda8e75329c
        ↓
versioned native runtime .../atlas-codex-20260912-1/codex
        ↓
ATLAS_CODEX_EXECUTABLE
        ↓
matching Atlas policy digest
        ↓
native runtime admission
        ↓
sealed runtime / Bubblewrap execution
        ↓
PVC FD transport with image_detail=original
        ↓
real Luna Medium semantic E2E
        ↓
1121-test full regression
```

**Final verdict: qualified for Atlas execution.**
