"""The narrow atlas-python-semantic/1 to PVC adapter."""
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

PYTHON_SEMANTIC_MEDIA_TYPE = "application/vnd.atlas.python-semantic+json"
PYTHON_SEMANTIC_SCHEMA = "atlas-python-semantic/1"


class PythonSemanticResultError(ValueError):
    """Python semantic bytes did not satisfy the canonical result contract."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON number")


def validate_python_semantic_result(data: bytes) -> dict:
    if type(data) is not bytes:
        raise PythonSemanticResultError("PYTHON_SEMANTIC_RESULT_INVALID")
    try:
        text = data.decode("utf-8")
        document, end = json.JSONDecoder(
            object_pairs_hook=_pairs, parse_constant=_constant).raw_decode(text)
        if end != len(text) - 1 or text[-1] != "\n":
            raise ValueError("terminal newline")
        if (type(document) is not dict
                or document.get("schema") != PYTHON_SEMANTIC_SCHEMA
                or set(document) != {"schema", "query", "authority",
                                      "repositoryWitness", "positionEncoding",
                                      "result"}):
            raise ValueError("identity shape")
        if (type(document["query"]) is not dict
                or type(document["authority"]) is not dict
                or type(document["result"]) is not dict
                or type(document["repositoryWitness"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}",
                                document["repositoryWitness"]) is None
                or document["positionEncoding"] != "utf-8"):
            raise ValueError("identity shape")
        query = document["query"]
        authority = document["authority"]
        result = document["result"]
        if (set(query) != {"kind", "path", "line", "character"}
                or query["kind"] not in {"definition", "references", "hover"}
                or type(query["path"]) is not str or not query["path"]
                or type(query["line"]) is not int or query["line"] < 0
                or type(query["character"]) is not int or query["character"] < 0
                or set(authority) != {"executable", "version"}
                or type(authority["executable"]) is not str
                or type(authority["version"]) is not str
                or not authority["version"].strip()
                or set(result) != {"kind", "value"}
                or result["kind"] != query["kind"]):
            raise ValueError("identity shape")
        canonical = json.dumps(document, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()
        if canonical + b"\n" != data:
            raise ValueError("noncanonical")
        return document
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError, TypeError,
            json.JSONDecodeError):
        raise PythonSemanticResultError("PYTHON_SEMANTIC_RESULT_INVALID") from None


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode() + b"\n"


@dataclass(frozen=True)
class PythonSemanticTablet:
    payload: bytes
    digest: str
    tablet_id: str
    artifact_id: str
    provenance: str

    @classmethod
    def from_result(cls, data: bytes) -> "PythonSemanticTablet":
        document = validate_python_semantic_result(data)
        digest = hashlib.sha256(data).hexdigest()
        provenance = _canonical({
            "schema": PYTHON_SEMANTIC_SCHEMA, "payloadSha256": digest,
            "query": document["query"], "authority": document["authority"],
            "repositoryWitness": document["repositoryWitness"],
        }).decode().rstrip("\n")
        return cls(data, digest, f"python-semantic-{digest[:16]}",
                   f"python-semantic-{digest[:16]}", provenance)

    def pvc_context(self, purpose: str = "python semantic context"):
        scratch = Path(tempfile.mkdtemp(prefix="atlas-python-semantic-pvc-",
                                         dir="/tmp"))
        try:
            (scratch / "bundle" / "artifacts").mkdir(parents=True)
            (scratch / "semantic-result.txt").write_bytes(b"")
            request = PvcPrepareRequest(scratch, ("semantic-result.txt",))
            relative = f"artifacts/{self.artifact_id}.tablet"
            (scratch / "bundle" / relative).write_bytes(self.payload)
            document = {
                "schemaVersion": 1,
                "sources": [{"sourceIndex": 0, "displayPath": "semantic-result.txt",
                             "language": "json",
                             "contentSha256": hashlib.sha256(b"").hexdigest(),
                             "symbolExtraction": {"support": "unsupported"}}],
                "tablets": [{"id": self.tablet_id, "pageIndex": 1,
                             "profile": "semantic", "width": 1, "height": 1,
                             "spans": [], "artifactId": self.artifact_id,
                             "digest": self.digest, "byteLength": len(self.payload),
                             "provenance": self.provenance}],
                "symbols": [], "artifacts": [{
                    "artifactId": self.artifact_id, "relativePath": relative,
                    "mediaType": PYTHON_SEMANTIC_MEDIA_TYPE,
                    "byteLength": len(self.payload), "sha256": self.digest}],
                "capabilities": {"lineProvenance": "complete",
                                 "symbolExtraction": "per-source"},
            }
            document["snapshotId"] = _snapshot_identity_id(document)
            encoded = _canonical(document)
            (scratch / "bundle" / "snapshot.json").write_bytes(encoded)
            stdout, stderr = scratch / "stdout", scratch / "stderr"
            stdout.write_bytes(encoded)
            stderr.write_bytes(b"")
            process = ProcessResult(("controller-python-semantic",), "now", "now",
                                    0, stdout, stderr, scratch_path=scratch)
            result = PvcPrepareResult(process, request).validate()
            return PvcContextSelection(result, (self.tablet_id,), purpose)
        except BaseException:
            import shutil
            shutil.rmtree(scratch, ignore_errors=True)
            raise


def build_python_semantic_tablet(data: bytes) -> PythonSemanticTablet:
    """Adapt already-produced Python semantic bytes; does not invoke Pyright."""
    return PythonSemanticTablet.from_result(data)
