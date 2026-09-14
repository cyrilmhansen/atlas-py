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


class _TextAuthority:
    """Controller-owned, descriptor-backed UTF-8 text authority.

    Text is deliberately not represented by a pathname.  ``payload`` is the
    bytes copied from and authenticated against the sealed descriptor; it is
    retained only so the already-staged bytes can be put into the effective
    prompt without reopening the bundle.
    """
    __slots__ = ("fd", "snapshot_id", "tablet_id", "artifact_id", "sha256",
                 "byte_length", "ordinal", "payload", "_closed")

    def __init__(self, token, fd, snapshot_id, tablet_id, artifact_id,
                 sha256, byte_length, ordinal, payload):
        if token is not _AUTHORITY_TOKEN:
            raise TypeError("text authority is controller-owned")
        if type(payload) is not bytes:
            raise TypeError("text authority payload must be bytes")
        # This is a second, local assertion at the model handoff.  The PVC
        # validator performs the same check while authenticating the bundle,
        # but the transport must never accidentally downgrade it later.
        payload.decode("utf-8")
        self.fd = fd
        self.snapshot_id = snapshot_id
        self.tablet_id = tablet_id
        self.artifact_id = artifact_id
        self.sha256 = sha256
        self.byte_length = byte_length
        self.ordinal = ordinal
        self.payload = payload
        self._closed = False

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
class PvcContextComposition:
    """An explicit, ordered composition of already-qualified selections."""

    selections: tuple[PvcContextSelection, ...]
    purpose: str = "composed PVC context"
    # Paths in this list are owned by the adapter which constructed the
    # composition.  In particular, a selection may also point at a retained
    # result directory, which is borrowed input and must not be inferred to be
    # disposable from its ``scratch_path``.
    owned_resources: tuple[Path, ...] = ()

    def __post_init__(self):
        selections = tuple(self.selections)
        if not selections:
            raise PvcContextError("PVC_CONTEXT_COMPOSITION_EMPTY")
        if any(type(selection) is not PvcContextSelection
               for selection in selections):
            raise PvcContextError("PVC_CONTEXT_COMPOSITION_MEMBER_REQUIRED")
        if not isinstance(self.purpose, str) or not self.purpose.strip():
            raise PvcContextError("PVC_CONTEXT_COMPOSITION_PURPOSE_INVALID")
        object.__setattr__(self, "selections", selections)
        object.__setattr__(self, "owned_resources",
                           tuple(Path(path) for path in self.owned_resources))


@dataclass(frozen=True)
class _StagedPvcContext:
    image_authorities: tuple[_ImageAuthority, ...]
    text_authorities: tuple[_TextAuthority, ...]
    framing: str
    root: Path | None = None
    roots: tuple[Path, ...] = ()

    def cleanup(self) -> None:
        """Release the staged descriptors and backing directory, once."""
        for authority in (*self.image_authorities, *self.text_authorities):
            authority.close()
        # Descriptor close is idempotent, and the directory may also be
        # visited by the workflow's preparation fallback.  In particular,
        # cleanup must be safe at both sides of the executor handoff.
        roots = self.roots or ((self.root,) if self.root is not None else ())
        for root in roots:
            if root.exists():
                shutil.rmtree(root, ignore_errors=False)


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


def _stage_pvc_context(selection: PvcContextSelection,
                       _ordinal_offset: int = 0) -> _StagedPvcContext:
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
    authorities_text = []
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
                    payload = bytearray()
                    if not hasattr(os, "memfd_create"):
                        raise PvcContextError("PVC_CONTEXT_MEMFD_UNAVAILABLE")
                    text_authority = None
                    image_fd = os.memfd_create(
                        ("atlas-pvc-image-" if artifact["mediaType"] == "image/png"
                         else "atlas-pvc-text-") + str(index),
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
                                payload.extend(chunk)
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
                    if artifact["mediaType"] == "image/png":
                        authorities.append(_ImageAuthority(
                            _AUTHORITY_TOKEN, image_fd, document["snapshotId"],
                            tablet["id"], artifact["artifactId"],
                            artifact["sha256"], artifact["byteLength"],
                            _ordinal_offset + index - 1))
                    elif artifact["mediaType"] in {
                            "text/vnd.atlas.review-task",
                            "text/vnd.atlas.review-diff",
                            "application/vnd.atlas.rust-semantic+json",
                            "application/vnd.atlas.python-semantic+json"}:
                        try:
                            text = bytes(payload)
                            text.decode("utf-8")
                        except UnicodeDecodeError as error:
                            os.close(image_fd)
                            raise PvcContextError(
                                "PVC_CONTEXT_TEXT_UTF8_INVALID") from error
                        text_authority = _TextAuthority(
                            _AUTHORITY_TOKEN, image_fd, document["snapshotId"],
                            tablet["id"], artifact["artifactId"],
                            artifact["sha256"], artifact["byteLength"],
                            _ordinal_offset + index - 1, text)
                        # The name is historical; the descriptor is an
                        # artifact authority, never a Codex image unless the
                        # media type selected the image branch above.
                        authorities_text.append(text_authority)
                    else:
                        os.close(image_fd)
                        raise PvcContextError(
                            "PVC_CONTEXT_MEDIA_TYPE_UNSUPPORTED")
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
                media = artifact["mediaType"]
                # From this point on, text is taken from the typed authority,
                # not from the source pathname (or an untrusted re-read).
                framed_payload = (
                    text_authority.payload if text_authority is not None
                    else None
                )
                payload_for_metadata = (
                    framed_payload if framed_payload is not None
                    else bytes(payload)
                )
                content_digest = hashlib.sha256(payload_for_metadata).hexdigest()
                framing.append(
                    f"{index}. {tablet['id']} media={media} "
                    f"artifact={artifact['artifactId']} "
                    f"tablet-sha256={tablet.get('digest', '')} "
                    f"payload-sha256={content_digest} "
                    f"payload-bytes={len(payload_for_metadata)}{suffix}")
                provenance = tablet.get("provenance")
                if provenance:
                    framing.append(f"   provenance: {provenance}")
                if media in {"text/vnd.atlas.review-task",
                             "text/vnd.atlas.review-diff",
                             "application/vnd.atlas.rust-semantic+json",
                             "application/vnd.atlas.python-semantic+json"}:
                    # The payload is inserted byte-for-byte between
                    # controller-authored delimiters.  No parsing,
                    # summarization, normalization, or semantic rewrite is
                    # performed.  The added newlines belong to the framing,
                    # not to the staged payload.
                    framing.append("   payload-begin")
                    framing.append(framed_payload.decode("utf-8"))
                    framing.append(
                        f"   payload-end tablet={tablet['id']}")
        finally:
            os.close(root_fd)
        return _StagedPvcContext(
            tuple(authorities), tuple(authorities_text),
            "\n".join(framing) + "\n", root, (root,))
    except BaseException:
        for authority in (*authorities, *authorities_text):
            authority.close()
        shutil.rmtree(root, ignore_errors=True)
        raise


def _stage_pvc_composition(
        composition: PvcContextComposition) -> _StagedPvcContext:
    """Stage members in caller order without merging their PVC authority."""
    if type(composition) is not PvcContextComposition:
        raise PvcContextError("PVC_CONTEXT_COMPOSITION_REQUIRED")
    staged_members = []
    ordinal_offset = 0
    try:
        for number, selection in enumerate(composition.selections, 1):
            staged = _stage_pvc_context(selection, ordinal_offset)
            staged_members.append(staged)
            ordinal_offset += len(selection.tablet_ids)
    except BaseException:
        for staged in staged_members:
            try:
                staged.cleanup()
            except BaseException:
                # Preserve the staging failure; workflow-level cleanup gets
                # another idempotent opportunity.
                pass
        raise

    images = tuple(image for staged in staged_members
                   for image in staged.image_authorities)
    texts = tuple(text for staged in staged_members
                  for text in staged.text_authorities)
    framing = [
        "PVC context composition is explicit controller ordering.",
        f"PVC composition purpose: {composition.purpose}",
    ]
    for number, staged in enumerate(staged_members, 1):
        # The member's historical standalone framing is kept byte-for-byte;
        # these are the only controller-authored composition delimiters.
        framing.append(f"PVC composition selection {number} begin")
        framing.append(staged.framing.rstrip("\n"))
        framing.append(f"PVC composition selection {number} end")
    roots = tuple(staged.root for staged in staged_members
                  if staged.root is not None)
    return _StagedPvcContext(images, texts, "\n".join(framing) + "\n",
                             roots[0] if roots else None, roots)
