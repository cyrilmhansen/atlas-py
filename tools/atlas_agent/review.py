"""Deterministic task and patch-review tablets.

This is deliberately a Git based representation.  In particular, it does
not make a second (and potentially different) interpretation of a patch by
walking the worktree and comparing files itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from .repository import RepositoryError, _allowed, witness


class ReviewPackageError(ValueError):
    """The review boundary could not be established or represented."""


_CANONICAL_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    # System attributes are another ambient input to Git's diff machinery.
    "GIT_ATTR_NOSYSTEM": "1",
}

# This is the one representation contract for both tracked and no-index
# additions.  In particular, do not rely on diff.noprefix or any other
# ambient gitconfig setting.
_CANONICAL_DIFF_OPTIONS = (
    "--no-ext-diff",
    "--no-textconv",
    "--no-color",
    "--binary",
    "--full-index",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    "-U3",
    "--diff-algorithm=myers",
    "--no-indent-heuristic",
    "--find-renames=50%",
    "--no-relative",
    "-O/dev/null",
)
_CANONICAL_DIFF_CONFIG = (
    "-c", "core.quotePath=true",
    "-c", "diff.noprefix=false",
    "-c", "diff.mnemonicprefix=false",
    "-c", "diff.algorithm=myers",
    "-c", "diff.indentHeuristic=false",
    "-c", "diff.compactionHeuristic=false",
    "-c", "diff.interHunkContext=0",
    "-c", "diff.suppressBlankEmpty=false",
    "-c", "diff.submodule=short",
    "-c", "diff.renameLimit=0",
    "-c", "diff.renames=true",
)


def _canonical_git_env() -> dict[str, str]:
    env = dict(os.environ)
    # Git reads GIT_DIFF_OPTS in addition to command-line options.  In
    # particular, it can silently replace the hunk context requested below.
    # These other variables can inject an alternate diff/config mechanism;
    # unrelated application environment is intentionally retained.
    for key in (
        "GIT_DIFF_OPTS", "GIT_EXTERNAL_DIFF", "GIT_PAGER",
        "GIT_CONFIG", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
    ):
        env.pop(key, None)
    # Do not inherit Git's environment-based config injection either.  The
    # invocation below is the complete representation authority.
    for key in ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"):
        env.pop(key, None)
    for key in tuple(env):
        if key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            env.pop(key, None)
    env.update(_CANONICAL_GIT_ENV)
    return env


def _git(root: Path, *args: str) -> bytes:
    process = subprocess.run(
        ["git", *args], cwd=root, env=_canonical_git_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    if process.returncode:
        raise ReviewPackageError(
            process.stderr.decode("utf-8", "replace").strip()
            or "REVIEW_GIT_FAILED"
        )
    return process.stdout


def _path_bytes(path: bytes) -> str:
    # Git's quoted output is intentionally avoided.  JSON gives us a stable
    # representation of valid UTF-8 names while surrogate names fail closed.
    try:
        return path.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReviewPackageError("REVIEW_PATH_NOT_REPRESENTABLE") from error


def _untracked(root: Path, name: bytes) -> bytes:
    try:
        path = root / os.fsdecode(name)
        info = path.lstat()
    except OSError as error:
        raise ReviewPackageError("REVIEW_UNTRACKED_UNREADABLE") from error
    # A symlink would make Git read an object outside the authorized
    # worktree.  It is not a review candidate, even when its link itself is
    # authorized.
    if stat.S_ISREG(info.st_mode):
        return name
    raise ReviewPackageError("REVIEW_UNTRACKED_FILE_TYPE_UNSUPPORTED")


def _untracked_patch(root: Path, name: bytes) -> bytes:
    # --no-index supplies Git's normal hunk coordinates and binary marker.
    path = os.fsdecode(name)
    process = subprocess.run(
        ["git", *_CANONICAL_DIFF_CONFIG, "--no-pager", "diff",
         *_CANONICAL_DIFF_OPTIONS, "--no-index", "--", "/dev/null", path],
        cwd=root, env=_canonical_git_env(), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode not in (0, 1):
        raise ReviewPackageError("REVIEW_DIFF_NOT_REPRESENTABLE")
    return process.stdout


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8") + b"\n"


def _canonical_witness(root: Path, value: dict) -> dict:
    """Keep authority metadata independent of diff presentation settings."""
    result = dict(value)
    unstaged = _git(
        root, *_CANONICAL_DIFF_CONFIG, "--no-pager", "diff",
        *_CANONICAL_DIFF_OPTIONS,
    )
    result["tracked_worktree_content_sha256"] = hashlib.sha256(
        unstaged).hexdigest()
    return result


@dataclass(frozen=True)
class ReviewTablet:
    tablet_type: str
    data: bytes
    digest: str

    @classmethod
    def make(cls, tablet_type: str, data: bytes) -> "ReviewTablet":
        if tablet_type not in {"TASK", "DIFF"}:
            raise ReviewPackageError("REVIEW_TABLET_TYPE_INVALID")
        # JSON/base64 framing is unambiguous for arbitrary task and patch
        # bytes (including Git binary patches), and has no wall-clock fields.
        framed = _canonical({
            "schema": "atlas-pvc-tablet/1",
            "type": tablet_type,
            "content": base64.b64encode(data).decode("ascii"),
        })
        return cls(tablet_type, framed, hashlib.sha256(framed).hexdigest())

    @property
    def content(self) -> bytes:
        """The exact unframed task or Git patch payload."""
        document = json.loads(self.data.decode("utf-8"))
        return base64.b64decode(document["content"], validate=True)

    @property
    def content_digest(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class ReviewPackage:
    expected_head: str
    witness: dict
    task: ReviewTablet
    diff: ReviewTablet

    @property
    def tablets(self) -> tuple[ReviewTablet, ReviewTablet]:
        return self.task, self.diff

    @property
    def digests(self) -> dict[str, str]:
        return {"TASK": self.task.digest, "DIFF": self.diff.digest}

    @property
    def task_digest(self) -> str:
        return self.task.digest

    @property
    def diff_digest(self) -> str:
        return self.diff.digest

    @property
    def bytes(self) -> bytes:
        return self.task.data + self.diff.data

    def pvc_context(self, purpose: str = "patch review package"):
        """Publish this controller-authored package through the PVC boundary.

        This is deliberately an adapter, not another transport: the package
        is written as a validated PVC bundle and selected with the same
        ``PvcContextSelection`` consumed by the workflow/executor.
        """
        from .one_shot import ProcessResult
        from .pvc import (PvcPrepareRequest, PvcPrepareResult,
                          _snapshot_identity_id)
        from .pvc_context import PvcContextSelection
        import tempfile

        scratch = Path(tempfile.mkdtemp(prefix="atlas-review-pvc-", dir="/tmp"))
        (scratch / "bundle" / "artifacts").mkdir(parents=True)
        # PvcPrepareRequest is intentionally retained as the normal request
        # provenance object; its source is only a valid local witness for the
        # synthetic, controller-authored review bundle.
        source = scratch / "review-package.txt"
        source.write_bytes(b"")
        request = PvcPrepareRequest(scratch, ("review-package.txt",))
        entries = []
        artifacts = []
        for index, tablet in enumerate(self.tablets, 1):
            media = ("text/vnd.atlas.review-task" if tablet.tablet_type == "TASK"
                     else "text/vnd.atlas.review-diff")
            artifact_id = f"review-{tablet.tablet_type.lower()}-{tablet.digest[:16]}"
            relative = f"artifacts/{artifact_id}.tablet"
            (scratch / "bundle" / relative).write_bytes(tablet.content)
            artifacts.append({
                "artifactId": artifact_id, "relativePath": relative,
                "mediaType": media, "byteLength": len(tablet.content),
                "sha256": hashlib.sha256(tablet.content).hexdigest(),
            })
            provenance = {
                "tabletType": tablet.tablet_type,
                "tabletDigest": tablet.digest,
                "expectedHead": self.expected_head,
                "witness": self.witness,
            }
            entries.append({
                "id": f"review-{tablet.tablet_type.lower()}-{tablet.digest[:16]}",
                "pageIndex": index, "profile": "review", "width": 1,
                "height": 1, "spans": [], "artifactId": artifact_id,
                "digest": tablet.digest, "byteLength": len(tablet.content),
                "provenance": _canonical(provenance).decode("utf-8").rstrip("\n"),
            })
        document = {
            "schemaVersion": 1,
            "sources": [{
                "sourceIndex": 0, "displayPath": "review-package.txt",
                "language": "text",
                "contentSha256": hashlib.sha256(b"").hexdigest(),
                "symbolExtraction": {"support": "unsupported"},
            }],
            "tablets": entries, "symbols": [], "artifacts": artifacts,
            "capabilities": {"lineProvenance": "complete",
                             "symbolExtraction": "per-source"},
        }
        document["snapshotId"] = _snapshot_identity_id(document)
        encoded = _canonical(document)
        (scratch / "bundle" / "snapshot.json").write_bytes(encoded)
        stdout = scratch / "stdout"
        stderr = scratch / "stderr"
        stdout.write_bytes(encoded)
        stderr.write_bytes(b"")
        process = ProcessResult(("controller-review-package",), "now", "now",
                                0, stdout, stderr, scratch_path=scratch)
        result = PvcPrepareResult(process, request).validate()
        return PvcContextSelection(result, tuple(entry["id"] for entry in entries),
                                   purpose)


def build_review_package(
    root: Path,
    expected_head: str,
    task: str,
    allowed: list[str] | tuple[str, ...] = (),
    ownership: dict | None = None,
) -> ReviewPackage:
    """Build TASK + DIFF from one witnessed, authorized repository state.

    ``allowed`` and ``ownership`` have the same authority shape as
    :func:`repository.witness`; no path outside that authority is read.
    """
    root = Path(root).resolve()
    if type(task) is not str or "\x00" in task:
        raise ReviewPackageError("REVIEW_TASK_INVALID")
    try:
        before = witness(root, list(allowed), ownership)
    except (RepositoryError, OSError) as error:
        raise ReviewPackageError("REVIEW_REPOSITORY_WITNESS_UNAVAILABLE") from error
    if before["head"] != expected_head:
        raise ReviewPackageError("REVIEW_BASE_HEAD_MISMATCH")

    records = [
        x for x in _git(root, "status", "--porcelain=v2",
                        "--untracked-files=all", "--ignored", "-z").split(b"\0")
        if x
    ]
    untracked = []
    ownership_paths = set((ownership or {}).get("patch_owned_untracked", ()))
    for record in records:
        if record.startswith((b"? ", b"! ")):
            name = record[2:]
            text = _path_bytes(name)
            authorized = _allowed(text, list(allowed)) or name.hex() in ownership_paths
            if not authorized:
                raise ReviewPackageError("REVIEW_UNAUTHORIZED_PATH")
            untracked.append(_untracked(root, name))
        elif record.startswith(b"u "):
            raise ReviewPackageError("REVIEW_UNMERGED_STATE")

    # One Git invocation describes the complete tracked H -> W transform,
    # including staged and unstaged portions (unlike diff --cached).
    # Hash authorized untracked bytes as part of this package's witness.
    # repository.witness intentionally omits ordinary allowed files because
    # they are outside its historical checkpoint witness.
    def untracked_witness(names):
        result = []
        for name in names:
            path = root / os.fsdecode(name)
            try:
                data = path.read_bytes()
            except OSError as error:
                raise ReviewPackageError("REVIEW_UNTRACKED_UNREADABLE") from error
            result.append((name, hashlib.sha256(data).hexdigest(), len(data)))
        return tuple(result)

    untracked_before = untracked_witness(untracked)
    # Authorize the final path set as Git sees it.  Checking only untracked
    # names would permit a tracked edit outside the caller's authority to
    # enter the package.
    # --name-only is insufficient here: with rename detection Git reports
    # only the destination.  Name-status -z exposes both endpoints for
    # renames (and keeps names byte-oriented until authority validation).
    changed_metadata = _git(
        root, *_CANONICAL_DIFF_CONFIG, "--no-pager", "diff",
        *_CANONICAL_DIFF_OPTIONS, "--name-status", "-z", "--format=",
        expected_head, "--",
    ).split(b"\0")
    changed_names = []
    cursor = 0
    while cursor < len(changed_metadata):
        status = changed_metadata[cursor]
        cursor += 1
        if not status:
            continue
        # With -z, rename/copy records are status, old name, new name.
        endpoints = 2 if status[:1] in (b"R", b"C") else 1
        changed_names.extend(changed_metadata[cursor:cursor + endpoints])
        cursor += endpoints
    for name in (item for item in changed_names if item):
        if not _allowed(_path_bytes(name), list(allowed)):
            raise ReviewPackageError("REVIEW_UNAUTHORIZED_PATH")

    tracked = _git(
        root, *_CANONICAL_DIFF_CONFIG, "--no-pager", "diff",
        *_CANONICAL_DIFF_OPTIONS, expected_head, "--",
    )
    additions = b"".join(_untracked_patch(root, name) for name in sorted(untracked))
    diff = tracked + additions

    try:
        after = witness(root, list(allowed), ownership)
    except (RepositoryError, OSError) as error:
        raise ReviewPackageError("REVIEW_REPOSITORY_WITNESS_UNAVAILABLE") from error
    # Re-enumerate names too: creation/deletion/authorization changes must
    # not be silently omitted between the two authority checks.
    after_records = [
        x for x in _git(root, "status", "--porcelain=v2",
                        "--untracked-files=all", "--ignored", "-z").split(b"\0")
        if x and x.startswith((b"? ", b"! "))
    ]
    after_names = []
    for record in after_records:
        name = record[2:]
        if _allowed(_path_bytes(name), list(allowed)) or name.hex() in ownership_paths:
            _untracked(root, name)
            after_names.append(name)
    if after != before or tuple(sorted(after_names)) != tuple(sorted(untracked)) or untracked_witness(after_names) != untracked_before:
        raise ReviewPackageError("REVIEW_REPOSITORY_WITNESS_CHANGED")
    try:
        task_bytes = task.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ReviewPackageError("REVIEW_TASK_INVALID_UTF8") from error
    return ReviewPackage(expected_head, _canonical_witness(root, before),
                         ReviewTablet.make("TASK", task_bytes),
                         ReviewTablet.make("DIFF", diff))


# Short spelling useful to callers integrating this with context preparation.
construct_review_package = build_review_package
build_review_tablets = build_review_package
review_package_pvc_context = ReviewPackage.pvc_context
