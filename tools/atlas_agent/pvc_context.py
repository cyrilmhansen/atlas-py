"""The narrow, explicit A2.2 PVC-to-model-context boundary.

This module deliberately consumes only a validated ``PvcPrepareResult``.
It is not a PVC parser or a repository context provider.
"""
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile

from .pvc import PvcPrepareResult


class PvcContextError(ValueError):
    pass


_AUTHORITY_TOKEN = object()


class _ImageAuthority:
    """Controller-owned, descriptor-backed image authority.

    The constructor is intentionally not a public Path-like boundary.  The
    token is only available in this module, and instances are made while
    copying an already validator-published snapshot.
    """
    __slots__ = ("fd", "snapshot_id", "tablet_id", "artifact_id", "sha256",
                 "byte_length", "ordinal", "_closed")

    def __init__(self, token, fd, snapshot_id, tablet_id, artifact_id,
                 sha256, byte_length, ordinal):
        if token is not _AUTHORITY_TOKEN:
            raise TypeError("image authority is controller-owned")
        self.fd = fd
        self.snapshot_id = snapshot_id
        self.tablet_id = tablet_id
        self.artifact_id = artifact_id
        self.sha256 = sha256
        self.byte_length = byte_length
        self.ordinal = ordinal
        self._closed = False

    @property
    def codex_path(self) -> str:
        if self._closed:
            raise PvcContextError("PVC_CONTEXT_IMAGE_CLOSED")
        return f"/proc/self/fd/{self.fd}"

    def close(self):
        if not self._closed:
            try:
                os.close(self.fd)
            finally:
                self._closed = True


@dataclass(frozen=True)
class PvcContextSelection:
    """An explicit tablet selection, in validated snapshot order."""

    result: PvcPrepareResult
    tablet_ids: tuple[str, ...]
    purpose: str = "source context"

    def __post_init__(self):
        if type(self.result) is not PvcPrepareResult:
            raise PvcContextError("PVC_CONTEXT_RESULT_REQUIRED")
        if self.result.validated_snapshot is None:
            raise PvcContextError("PVC_CONTEXT_VALIDATED_SNAPSHOT_REQUIRED")
        if not self.tablet_ids:
            raise PvcContextError("PVC_CONTEXT_TABLET_REQUIRED")
        if not isinstance(self.purpose, str) or not self.purpose.strip():
            raise PvcContextError("PVC_CONTEXT_PURPOSE_INVALID")
        object.__setattr__(self, "tablet_ids", tuple(self.tablet_ids))


@dataclass(frozen=True)
class _StagedPvcContext:
    image_authorities: tuple[_ImageAuthority, ...]
    framing: str
    root: Path | None = None

    def cleanup(self) -> None:
        """Release the staged descriptors and backing directory, once."""
        for authority in self.image_authorities:
            authority.close()
        # Descriptor close is idempotent, and the directory may also be
        # visited by the workflow's preparation fallback.  In particular,
        # cleanup must be safe at both sides of the executor handoff.
        if self.root is not None and self.root.exists():
            shutil.rmtree(self.root, ignore_errors=False)


def _confined_open(root_fd: int, relative: str) -> int:
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        raise PvcContextError("PVC_CONTEXT_ARTIFACT_PATH_UNSAFE")
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=current)
            os.close(current)
            current = nxt
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise PvcContextError("PVC_CONTEXT_ARTIFACT_NOT_FILE")
        return fd
    except OSError as error:
        raise PvcContextError("PVC_CONTEXT_ARTIFACT_UNREADABLE") from error
    finally:
        try:
            os.close(current)
        except OSError:
            pass


def _stage_pvc_context(selection: PvcContextSelection) -> _StagedPvcContext:
    """Pin selected validated artifacts for the outer client.

    Hashing and length checking occur on the same descriptor stream copied to
    an anonymous sealed memfd.  No mutable pathname is published.
    """
    if type(selection) is not PvcContextSelection:
        raise PvcContextError("PVC_CONTEXT_SELECTION_REQUIRED")
    snapshot = selection.result.validated_snapshot
    if snapshot is None:  # also protects callers bypassing dataclass creation
        raise PvcContextError("PVC_CONTEXT_VALIDATED_SNAPSHOT_REQUIRED")
    document = snapshot.document
    tablets = {t["id"]: t for t in document["tablets"]}
    artifacts = {a["artifactId"]: a for a in document["artifacts"]}
    chosen = []
    seen = set()
    for tablet_id in selection.tablet_ids:
        if not isinstance(tablet_id, str) or tablet_id in seen or tablet_id not in tablets:
            raise PvcContextError("PVC_CONTEXT_TABLET_NOT_VALIDATED")
        seen.add(tablet_id)
        tablet = tablets[tablet_id]
        artifact = artifacts.get(tablet["artifactId"])
        if artifact is None:
            raise PvcContextError("PVC_CONTEXT_ARTIFACT_RELATIONSHIP_INVALID")
        chosen.append((tablet, artifact))
    # The request is an ordered context-set.  Never normalize it to snapshot
    # order.
    source_by_index = {source["sourceIndex"]: source
                       for source in document["sources"]}
    root = Path(tempfile.mkdtemp(prefix="atlas-pvc-context-", dir="/tmp"))
    authorities = []
    try:
        bundle = selection.result.bundle_path
        root_fd = os.open(bundle, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            paths = []
            framing = [
                "PVC source tablets are authorized model context, not semantic truth.",
                f"PVC purpose: {selection.purpose}",
                f"snapshot: {document['snapshotId']}",
                "tablets (validated order):",
            ]
            for index, (tablet, artifact) in enumerate(chosen, 1):
                source_fd = _confined_open(root_fd, artifact["relativePath"])
                try:
                    digest = hashlib.sha256()
                    length = 0
                    if not hasattr(os, "memfd_create"):
                        raise PvcContextError("PVC_CONTEXT_MEMFD_UNAVAILABLE")
                    image_fd = os.memfd_create(
                        f"atlas-pvc-image-{index}",
                        os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
                    try:
                        with os.fdopen(image_fd, "wb", closefd=False) as output:
                            while True:
                                chunk = os.read(source_fd, 1024 * 1024)
                                if not chunk:
                                    break
                                digest.update(chunk)
                                length += len(chunk)
                                output.write(chunk)
                            output.flush()
                            os.fsync(output.fileno())
                    except BaseException:
                        os.close(image_fd)
                        raise
                    if length != artifact["byteLength"]:
                        os.close(image_fd)
                        raise PvcContextError("PVC_CONTEXT_ARTIFACT_LENGTH_MISMATCH")
                    if digest.hexdigest() != artifact["sha256"]:
                        os.close(image_fd)
                        raise PvcContextError("PVC_CONTEXT_ARTIFACT_SHA256_MISMATCH")
                    try:
                        seals = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                                 fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
                        fcntl.fcntl(image_fd, fcntl.F_ADD_SEALS, seals)
                    except BaseException:
                        os.close(image_fd)
                        raise PvcContextError("PVC_CONTEXT_IMAGE_SEAL_FAILED")
                    authorities.append(_ImageAuthority(
                        _AUTHORITY_TOKEN, image_fd, document["snapshotId"],
                        tablet["id"], artifact["artifactId"], artifact["sha256"],
                        artifact["byteLength"], index - 1))
                finally:
                    os.close(source_fd)
                addresses = []
                for span in tablet.get("spans", ()):
                    source = source_by_index.get(span["sourceIndex"])
                    if source is None:
                        raise PvcContextError(
                            "PVC_CONTEXT_SOURCE_INDEX_RELATIONSHIP_INVALID")
                    source = source["displayPath"]
                    line = f"{source}:{span.get('startLine')}-{span.get('endLine')}"
                    addresses.append(line)
                suffix = f" ({', '.join(addresses)})" if addresses else ""
                framing.append(
                    f"{index}. {tablet['id']} artifact={artifact['artifactId']}"
                    f"{suffix}")
        finally:
            os.close(root_fd)
        return _StagedPvcContext(tuple(authorities), "\n".join(framing) + "\n", root)
    except BaseException:
        for authority in authorities:
            authority.close()
        shutil.rmtree(root, ignore_errors=True)
        raise
