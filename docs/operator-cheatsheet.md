# Atlas Agent operator cheat sheet

The textual operator card. It assumes the project workflow is already
initialized; see [`agent-workflow.md`](agent-workflow.md) for contracts and
initialization details. `aa` means the installed `atlas-agent` command.

## Fresh terminal → ready

After a reboot, open a new shell and paste this block. It uses no shell
history, starting directory, function, or activated virtual environment:

```sh
cd /home/john/luna/aa-pvc-observation

# Stable, reviewed controller (not the candidate project worktree).
ATLAS_AGENT_SRC=/home/john/luna/atlas-agent-selfhost-p06-g22

# Operator-owned machine capability authority (includes qualified PVC).
export ATLAS_AGENT_CAPABILITIES_FILE=/home/john/.local/share/atlas-agent/pvc-witness-capabilities.toml

aa () {
    env PYTHONPATH="$ATLAS_AGENT_SRC" \
        python3 -P -m tools.atlas_agent "$@"
}

aa status
```

Status history is bounded to the last 10 generations by default. Use
`aa status --history 3 --detail compact` for a quick scan, `--history 0` for
health only, or `aa status --history all --detail full` for the complete
legacy detail. `--history` and `--detail` are independent.

The expected boundary lines are:

```text
journal: OK
state: MATCH
repository witness: MATCH
```

Three authorities are deliberately separate:

| Authority | Selected by | Operator recognition |
|---|---|---|
| **stable Atlas Agent controller** | `ATLAS_AGENT_SRC` in `aa` | `aa` sets `PYTHONPATH` and uses `python3 -P`; it is not this worktree |
| **candidate project/worktree** | the `cd` location and its repository witness | `aa status` reports its generations and repository witness |
| **qualified external toolchain** | exported capability manifest, then the project capability requirement | PVC is resolved from the manifest, not from `PATH` or a repository checkout |

The manifest is operator-owned and authoritative. The current PVC example
identifies `pi-visual-context` as
`git:54777ee0254c6f3f4bc04ea8a5cdb2d58cf43221` and binds
`/home/john/projects/poc/pi-visual-context`; verify the manifest and linked
[`pvc-observation-v0.md`](pvc-observation-v0.md) when that qualification
changes. Capability-free commands do not read it, but exporting it here
makes capability-bearing dispatch ready.

Do not reproduce executor-internal environment variables. CapabilityResolver
and the executor derive the sandbox `PATH`, `HOME`, `CODEX_HOME`, `TMPDIR`,
`TMP`, and `TEMP`. `ATLAS_CODEX_EXECUTABLE` and `ATLAS_CODEX_HOME` are only
optional machine-install overrides.

## Normal generation

### 1. Create and admit

Put the bounded task in `task.txt`; do not rely on a remembered generation:

```sh
aa prompt-create --checkpoint <name> \
    --action <implementation|patch_review|state_audit|checkpoint> < task.txt
aa ingest
```

`prompt-create` prints the generation number. Run one accepted non-checkpoint
generation:

```sh
aa dispatch --timeout-seconds 600
aa report
aa status
```

The normal loop is:

```text
implementation → patch_review → fixes if needed
              → fresh patch_review → PASS
```

Keep the slice bounded. When its contract, review, qualification, and
witnesses are satisfied, stop; do not add opportunistic hardening. Normal
states are `ACCEPTED → RUNNING → COMPLETED`; interruption is `INTERRUPTED`
and unstarted accepted work may be `CANCELLED`.

### 2. Review and host witness

Review the resulting diff and run the required focused checks. If sandbox
evidence is insufficient, perform the linked qualification operation as a
**host witness**. It must leave pre/post repository state identical and
establish:

```text
journal: OK
state: MATCH
repository witness: MATCH
```

A witness proves the bounded operation; it is not permission to broaden it.
Qualification-probe success is not operation success, and process success is
not a validated result.

### 3. Checkpoint

Only after review and the required witness, create and admit a checkpoint:

```sh
aa prompt-create --checkpoint <name> --action checkpoint < checkpoint.txt
aa ingest
aa checkpoint <generation> --message "<commit subject>"
```

Checkpoint dispatch is manual and reports `CHECKPOINT_MANUAL_REQUIRED`; do
not dispatch it and do not run `git commit`. Atlas performs the checkpoint
and does not push.

## Recovery

If a transaction failed after `CHECKPOINT_INTENT`, run:

```sh
aa recover
aa status
```

Do not repair Git manually. An `INTERRUPTED` generation is tainted: create a
fresh generation. A checkpoint left `ACCEPTED` is normally awaiting
`aa checkpoint`, not a dispatch retry.

## Identity problem (current commands only)

`aa status` checks journal/state/provenance and the repository witness.
`aa doctor` performs the current workflow preflight and reports
`doctor: OK`; neither command currently offers a toolchain diff or identity
diagnostic. For an authority/qualification mismatch:

1. Run `aa status` and `aa doctor`.
2. Confirm `ATLAS_AGENT_CAPABILITIES_FILE` names the intended, non-symlink
   manifest. Treat the selected capability manifest as **EXPECTED** authority:
   its qualification string and expected source, executable, probe, and
   identity-file fingerprints.
3. During resolution, compare that authority with **OBSERVED** actual source
   tree/Git revision, observed version, executable fingerprint, probe result,
   and identity files.
   **HISTORICAL EVIDENCE** is a prior successful capability archive/report only
   if one actually exists; a failed qualification may have no archive/report
   because it fails before CapabilityPlan publication. Stop and requalify
   changed tool bytes; do not weaken authority or use ambient `PATH`.

The normal path does not require manual hash archaeology.

## Symptom → action

| Symptom/state | Action |
|---|---|
| `journal: OK`, `state: MISMATCH` | Stop; inspect workflow state and use the supported recovery path. |
| `repository witness: MISMATCH` | Stop; do not create/ingest another generation; diagnose the boundary. |
| `CHECKPOINT_MANUAL_REQUIRED` | Do not dispatch; use `aa checkpoint <g> --message "..."`. |
| failure after `CHECKPOINT_INTENT` | Run `aa recover`; do not repair Git manually. |
| `INTERRUPTED` | Create a fresh generation. |
| review `PASS` | Proceed to required witness and checkpoint; avoid speculative hardening. |
| qualification identity differs | Stop, compare manifest/archive/source facts, then requalify. |

For graphical use, see roadmap item
[`A5.1`](roadmap.md#a51--graphical-operator-golden-path--future): a future
compact card derived from this canonical text will show bootstrap, authorities,
normal lifecycle, review/witness, checkpoint, and recovery branches. It is
intended for rapid scanning and multimodal prompt context, with drift checks;
the graphic is not implemented yet.
