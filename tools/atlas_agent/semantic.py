"""The small controller adapter from S1b.1 output to a typed PVC tablet."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .one_shot import ProcessResult
from .pvc import PvcPrepareRequest, PvcPrepareResult, _snapshot_identity_id
from .pvc_context import PvcContextSelection


SEMANTIC_MEDIA_TYPE = "application/vnd.atlas.rust-semantic+json"
SEMANTIC_PROFILE = "semantic"
SEMANTIC_SCHEMA = "atlas-rust-semantic/1"


class SemanticResultError(ValueError):
    """S1b.1 bytes did not satisfy the canonical semantic result contract."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON number")


def validate_semantic_result(data: bytes) -> dict:
    """Validate, without interpreting, one canonical S1b.1 result."""
    if type(data) is not bytes:
        raise SemanticResultError("SEMANTIC_RESULT_INVALID")
    try:
        text = data.decode("utf-8")
        decoder = json.JSONDecoder(object_pairs_hook=_pairs,
                                   parse_constant=_constant)
        document, end = decoder.raw_decode(text)
        if end != len(text) - 1 or text[-1] != "\n":
            raise ValueError("canonical terminal newline required")
        if type(document) is not dict:
            raise ValueError("object required")
        if document.get("schema") != SEMANTIC_SCHEMA:
            raise ValueError("schema")
        for key in ("query", "authority", "repositoryWitness",
                    "positionEncoding", "result"):
            if key not in document:
                raise ValueError("required field")
        if (type(document["query"]) is not dict
                or type(document["authority"]) is not dict
                or (type(document["repositoryWitness"]) is not dict
                    and (type(document["repositoryWitness"]) is not str
                         or re.fullmatch(r"[0-9a-f]{64}",
                                         document["repositoryWitness"]) is None))
                or type(document["result"]) is not dict
                or document["positionEncoding"] != "utf-8"):
            raise ValueError("identity shape")
        canonical = json.dumps(document, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()
        if canonical + b"\n" != data:
            raise ValueError("noncanonical")
        return document
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError, TypeError,
            json.JSONDecodeError):
        raise SemanticResultError("SEMANTIC_RESULT_INVALID") from None


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode() + b"\n"


@dataclass(frozen=True)
class SemanticTablet:
    payload: bytes
    digest: str
    tablet_id: str
    artifact_id: str
    provenance: str

    @classmethod
    def from_result(cls, data: bytes) -> "SemanticTablet":
        document = validate_semantic_result(data)
        digest = hashlib.sha256(data).hexdigest()
        # These fields are copied as provenance, never transformed into the
        # semantic payload.
        provenance = _canonical({
            "schema": SEMANTIC_SCHEMA,
            "payloadSha256": digest,
            "query": document["query"],
            "authority": document["authority"],
            "repositoryWitness": document["repositoryWitness"],
        }).decode().rstrip("\n")
        return cls(data, digest, f"semantic-{digest[:16]}",
                   f"semantic-{digest[:16]}", provenance)

    def pvc_context(self, purpose: str = "rust semantic context"):
        """Publish this tablet through the existing PVC text transport."""
        scratch = Path(tempfile.mkdtemp(prefix="atlas-semantic-pvc-", dir="/tmp"))
        try:
            (scratch / "bundle" / "artifacts").mkdir(parents=True)
            source = scratch / "semantic-result.txt"
            source.write_bytes(b"")
            request = PvcPrepareRequest(scratch, ("semantic-result.txt",))
            relative = f"artifacts/{self.artifact_id}.tablet"
            (scratch / "bundle" / relative).write_bytes(self.payload)
            document = {
                "schemaVersion": 1,
                "sources": [{
                    "sourceIndex": 0, "displayPath": "semantic-result.txt",
                    "language": "json",
                    "contentSha256": hashlib.sha256(b"").hexdigest(),
                    "symbolExtraction": {"support": "unsupported"},
                }],
                "tablets": [{
                    "id": self.tablet_id, "pageIndex": 1,
                    "profile": SEMANTIC_PROFILE, "width": 1, "height": 1,
                    "spans": [], "artifactId": self.artifact_id,
                    "digest": self.digest, "byteLength": len(self.payload),
                    "provenance": self.provenance,
                }],
                "symbols": [],
                "artifacts": [{
                    "artifactId": self.artifact_id, "relativePath": relative,
                    "mediaType": SEMANTIC_MEDIA_TYPE,
                    "byteLength": len(self.payload), "sha256": self.digest,
                }],
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
            process = ProcessResult(("controller-rust-semantic",), "now", "now",
                                    0, stdout, stderr, scratch_path=scratch)
            result = PvcPrepareResult(process, request).validate()
            return PvcContextSelection(result, (self.tablet_id,), purpose)
        except BaseException:
            import shutil
            shutil.rmtree(scratch, ignore_errors=True)
            raise


def build_semantic_tablet(data: bytes) -> SemanticTablet:
    """Explicit S1b.1-to-PVC adapter; rust-analyzer is not called here."""
    return SemanticTablet.from_result(data)
