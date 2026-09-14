"""The deliberately small PVC prepare consumer of the one-shot boundary."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import codecs
import hashlib
import json
import math
import ntpath
import os
import errno
import stat
import re
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .one_shot import OneShotExecutor, ProcessResult
from .toolchains import CapabilityPlan


class PvcRequestError(ValueError):
    pass


class PvcBundleValidationError(ValueError):
    """A retained PVC result did not cross the bundle trust boundary."""


@dataclass(frozen=True)
class PvcValidatedSnapshot:
    """The parsed snapshot returned by the explicit validation boundary."""

    document: Mapping[str, Any]
    snapshot_bytes: bytes


_MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
_SOURCE_MEDIA_TYPES = frozenset({"image/png"})
_REVIEW_MEDIA_TYPES = frozenset({
    "text/vnd.atlas.review-task", "text/vnd.atlas.review-diff",
})
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SNAPSHOT_ID = re.compile(r"^scs1-[a-f0-9]{64}$")


def _fail(reason: str) -> None:
    raise PvcBundleValidationError(reason)


def _deep_freeze_json(value: Any) -> Any:
    """Copy a parsed JSON value into a recursively immutable representation."""
    if isinstance(value, dict):
        return MappingProxyType({
            key: _deep_freeze_json(item) for key, item in value.items()
        })
    if isinstance(value, list):
        return tuple(_deep_freeze_json(item) for item in value)
    return value


def _relative_parts(relative: str, label: str) -> tuple[str, ...]:
    # Pathname arguments are external bundle data.  Check them before either
    # pathlib or the descriptor-relative syscall gets a chance to interpret
    # them; in particular, os.open raises ValueError for NUL and UnicodeError
    # for data which cannot be encoded for the filesystem.
    if type(relative) is not str or "\x00" in relative:
        _fail(f"PVC_BUNDLE_{label}_PATH_INVALID")
    try:
        relative.encode(sys.getfilesystemencoding(), "strict")
        path = Path(relative)
    except (UnicodeError, ValueError):
        _fail(f"PVC_BUNDLE_{label}_PATH_INVALID")
    if (not relative or path.is_absolute() or ntpath.isabs(relative)
            or ntpath.splitdrive(relative)[0] or ".." in path.parts
            or path == Path(".") or any(part in ("", ".") for part in path.parts)):
        _fail(f"PVC_BUNDLE_{label}_PATH_INVALID")
    return path.parts


def _open_confined(root_fd: int, relative: str, *, label: str) -> int:
    """Open one object below root_fd, never following a component symlink."""
    parts = _relative_parts(relative, label)
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=current)
            os.close(current)
            current = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            _fail(f"PVC_BUNDLE_{label}_NOT_FILE")
        return fd
    except FileNotFoundError:
        _fail(f"PVC_BUNDLE_{label}_MISSING")
    except OSError as error:
        # ELOOP is deliberately reported as a symlink, rather than falling
        # through to a pathname-based read.
        if error.errno == errno.ELOOP:
            _fail(f"PVC_BUNDLE_{label}_SYMLINK")
        _fail(f"PVC_BUNDLE_{label}_UNREADABLE")
    finally:
        try:
            os.close(current)
        except OSError:
            pass


def _read_bounded(fd: int, limit: int, *, label: str) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = os.read(fd, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            _fail(f"PVC_BUNDLE_{label}_BOUNDED")
        chunks.append(chunk)


def _hash_bounded(fd: int, expected: int, digest: str, *, label: str,
                  utf8: bool = False) -> None:
    hasher = hashlib.sha256()
    decoder = None
    if utf8:
        # Validate text at the retained-artifact boundary.  Incremental
        # decoding is important here: a multibyte scalar may straddle two
        # reads, and accepting a prefix would make the transport type
        # advisory rather than authoritative.
        decoder = codecs.getincrementaldecoder("utf-8")()
    total = 0
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        hasher.update(chunk)
        if decoder is not None:
            try:
                decoder.decode(chunk, final=False)
            except UnicodeDecodeError:
                _fail(f"PVC_BUNDLE_{label}_UTF8")
    if decoder is not None:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            _fail(f"PVC_BUNDLE_{label}_UTF8")
    if total != expected:
        _fail(f"PVC_BUNDLE_{label}_BYTE_LENGTH")
    if hasher.hexdigest() != digest:
        _fail(f"PVC_BUNDLE_{label}_SHA256")


def _object(value: Any, reason: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(reason)
    return value


_JS_SAFE_INTEGER = 2 ** 53 - 1


def _identity_int(value: Any, reason: str, minimum=None) -> None:
    """Accept only integers whose JSON number is stable across JS and Python."""
    if (type(value) is not int or abs(value) > _JS_SAFE_INTEGER
            or (minimum is not None and value < minimum)):
        _fail(reason)


def _identity_safe(value: Any) -> Any:
    """Normalize valid UTF-16 pairs and reject malformed Unicode."""
    if isinstance(value, str):
        result = []
        index = 0
        while index < len(value):
            code = ord(value[index])
            if 0xD800 <= code <= 0xDBFF:
                if (index + 1 == len(value)
                        or not 0xDC00 <= ord(value[index + 1]) <= 0xDFFF):
                    _fail("PVC_BUNDLE_IDENTITY_STRING_INVALID")
                result.append(chr(0x10000 + ((code - 0xD800) << 10)
                                  + ord(value[index + 1]) - 0xDC00))
                index += 2
                continue
            if 0xDC00 <= code <= 0xDFFF:
                _fail("PVC_BUNDLE_IDENTITY_STRING_INVALID")
            result.append(value[index])
            index += 1
        return "".join(result)
    elif isinstance(value, dict):
        return {_identity_safe(key): _identity_safe(item)
                for key, item in value.items()}
    elif isinstance(value, list):
        return [_identity_safe(item) for item in value]
    return value


def _finite_metric(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return isinstance(value, int) or math.isfinite(value)


def _parse_snapshot(data: bytes) -> dict[str, Any]:
    if len(data) > _MAX_SNAPSHOT_BYTES:
        _fail("PVC_BUNDLE_STDOUT_BOUNDED")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("PVC_BUNDLE_STDOUT_UTF8")
    try:
        # Reject duplicate names: otherwise the bytes and the interpreted
        # manifest can describe different bundles to different consumers.
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result

        def constant(value):
            raise ValueError(f"non-JSON constant: {value}")

        decoder = json.JSONDecoder(object_pairs_hook=pairs,
                                   parse_constant=constant)
        whitespace = " \t\r\n"
        leading = len(text) - len(text.lstrip(whitespace))
        document, end = decoder.raw_decode(text, leading)
        if any(char not in whitespace for char in text[end:]):
            _fail("PVC_BUNDLE_STDOUT_TRAILING")
    except PvcBundleValidationError:
        raise
    except (ValueError, json.JSONDecodeError):
        _fail("PVC_BUNDLE_STDOUT_JSON")
    return _object(document, "PVC_BUNDLE_SNAPSHOT_SHAPE")



def _snapshot_identity_id(document: dict[str, Any]) -> str:
    """Return the validated snapshot identity using the production projection."""
    capabilities = document["capabilities"]
    identity = {
        "schemaVersion": document["schemaVersion"],
        "sources": [],
        "tablets": [],
        "symbols": [],
    }
    for source in document["sources"]:
        item = {key: source[key] for key in
                ("sourceIndex", "displayPath", "language", "contentSha256")}
        if "codec" in source:
            item["codec"] = source["codec"]
        item["symbolExtraction"] = {
            key: source["symbolExtraction"][key] for key in
            ("support", "status", "extractorVersion")
            if key in source["symbolExtraction"]
        }
        identity["sources"].append(item)
    for tablet in document["tablets"]:
        spans = []
        for span in tablet["spans"]:
            span_item = {key: span[key] for key in
                         ("sourceIndex", "startLine", "endLine")}
            if "bannerOnly" in span:
                span_item["bannerOnly"] = span["bannerOnly"]
            spans.append(span_item)
        tablet_identity = {key: tablet[key] for key in
                           ("id", "pageIndex", "profile", "width", "height")}
        # Typed review tablets add their content identity without changing
        # the historical SOURCE projection.
        for key in ("digest", "byteLength", "provenance"):
            if key in tablet:
                tablet_identity[key] = tablet[key]
        identity["tablets"].append(tablet_identity |
                                   {"spans": spans,
                                    "artifactId": tablet["artifactId"]})
    identity["symbols"] = [
        {key: symbol[key] for key in
         ("sourceIndex", "name", "qualifiedName", "kind", "line", "tabletIds")}
        for symbol in document["symbols"]]
    if "symbolDiagnostics" in document:
        identity["symbolDiagnostics"] = [
            {"sourceIndex": d["sourceIndex"], "message": d["message"]}
            for d in document["symbolDiagnostics"]]
    identity["artifacts"] = [
        {key: artifact[key] for key in ("artifactId", "mediaType", "sha256")}
        for artifact in document["artifacts"]]
    identity["capabilities"] = {
        "lineProvenance": capabilities["lineProvenance"],
        "symbolExtraction": capabilities["symbolExtraction"],
    }
    identity = _identity_safe(identity)
    encoded_identity = json.dumps(identity, ensure_ascii=False,
                                  separators=(",", ":")).encode("utf-8")
    return "scs1-" + hashlib.sha256(encoded_identity).hexdigest()


def validate_prepare_result(result: "PvcPrepareResult") -> "PvcPrepareResult":
    """Validate controller-retained PVC bytes; never invokes PVC."""
    if not isinstance(result, PvcPrepareResult):
        raise TypeError("PVC prepare result is required")
    if not result.process_succeeded:
        _fail("PVC_BUNDLE_PROCESS_NOT_SUCCEEDED")
    expected_stdout = result.scratch_path / "stdout"
    if result.stdout_path != expected_stdout:
        _fail("PVC_BUNDLE_STDOUT_OWNERSHIP")
    bundle_fd = -1
    try:
        scratch_fd = os.open(result.scratch_path,
                             os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stdout_fd = _open_confined(scratch_fd, "stdout", label="STDOUT")
        stdout = _read_bounded(stdout_fd, _MAX_SNAPSHOT_BYTES, label="STDOUT")
        os.close(stdout_fd)
    except (OSError, ValueError):
        _fail("PVC_BUNDLE_STDOUT_MISSING")
    finally:
        try:
            os.close(locals().get("stdout_fd", -1))
        except OSError:
            pass
        try:
            os.close(locals().get("scratch_fd", -1))
        except OSError:
            pass
    document = _parse_snapshot(stdout)

    required = ("schemaVersion", "sources", "tablets", "symbols",
                "artifacts", "capabilities", "snapshotId")
    if any(key not in document for key in required):
        _fail("PVC_BUNDLE_SNAPSHOT_REQUIRED")
    if document["schemaVersion"] != 1:
        _fail("PVC_BUNDLE_SCHEMA_UNSUPPORTED")
    if (type(document["schemaVersion"]) is not int
            or type(document["sources"]) is not list
            or type(document["tablets"]) is not list
            or type(document["symbols"]) is not list
            or type(document["artifacts"]) is not list
            or type(document["capabilities"]) is not dict
            or type(document["snapshotId"]) is not str
            or not _SNAPSHOT_ID.fullmatch(document["snapshotId"])):
        _fail("PVC_BUNDLE_SNAPSHOT_SHAPE")

    try:
        scratch_fd = os.open(result.scratch_path,
                             os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        bundle_fd = os.open("bundle", os.O_RDONLY | os.O_DIRECTORY |
                            os.O_NOFOLLOW, dir_fd=scratch_fd)
        if not stat.S_ISDIR(os.fstat(bundle_fd).st_mode):
            _fail("PVC_BUNDLE_DIRECTORY_INVALID")
        snapshot_fd = _open_confined(bundle_fd, "snapshot.json", label="SNAPSHOT")
        snapshot_bytes = _read_bounded(snapshot_fd, _MAX_SNAPSHOT_BYTES,
                                       label="SNAPSHOT")
        os.close(snapshot_fd)
    except OSError:
        try:
            if bundle_fd >= 0:
                os.close(bundle_fd)
        except OSError:
            pass
        _fail("PVC_BUNDLE_SNAPSHOT_MISSING")
    except BaseException:
        try:
            if bundle_fd >= 0:
                os.close(bundle_fd)
        except OSError:
            pass
        raise
    finally:
        for name in ("snapshot_fd", "scratch_fd"):
            try:
                os.close(locals().get(name, -1))
            except OSError:
                pass
    try:
        return _validate_bundle_contents(
            result, bundle_fd, stdout, snapshot_bytes, document)
    finally:
        try:
            os.close(bundle_fd)
        except OSError:
            pass


def _validate_bundle_contents(result, bundle_fd, stdout, snapshot_bytes, document):
    if snapshot_bytes != stdout:
        _fail("PVC_BUNDLE_STDOUT_SNAPSHOT_MISMATCH")
    # Parse the manifest bytes too, so this also protects against a future
    # caller accidentally changing the accepted stdout parser.
    if _parse_snapshot(snapshot_bytes) != document:
        _fail("PVC_BUNDLE_SNAPSHOT_INVALID")

    capabilities = document["capabilities"]
    if (capabilities.get("lineProvenance") != "complete"
            or capabilities.get("symbolExtraction") != "per-source"):
        _fail("PVC_BUNDLE_CAPABILITIES_INVALID")

    if "project" in document:
        project = _object(document["project"], "PVC_BUNDLE_PROJECT_SHAPE")
        if type(project.get("projectPrefix")) is not str:
            _fail("PVC_BUNDLE_PROJECT_SHAPE")

    def exact_int(value, reason, minimum=None):
        if type(value) is not int or (minimum is not None and value < minimum):
            _fail(reason)

    sources = {}
    if not document["sources"]:
        _fail("PVC_BUNDLE_SOURCE_REQUIRED")
    for item in document["sources"]:
        source = _object(item, "PVC_BUNDLE_SOURCE_SHAPE")
        for key in ("sourceIndex", "displayPath", "language",
                    "contentSha256", "symbolExtraction"):
            if key not in source:
                _fail("PVC_BUNDLE_SOURCE_SHAPE")
        _identity_int(source["sourceIndex"], "PVC_BUNDLE_SOURCE_INDEX_INVALID", 0)
        index = source["sourceIndex"]
        if index in sources:
            _fail("PVC_BUNDLE_SOURCE_INDEX_INVALID")
        if (type(source["displayPath"]) is not str or not source["displayPath"]
                or ntpath.isabs(source["displayPath"])
                or Path(source["displayPath"]).is_absolute()):
            _fail("PVC_BUNDLE_SOURCE_PATH_INVALID")
        if (type(source["language"]) is not str
                or type(source["contentSha256"]) is not str
                or not _SHA256.fullmatch(source["contentSha256"])):
            _fail("PVC_BUNDLE_SOURCE_SHAPE")
        extraction = _object(source["symbolExtraction"],
                             "PVC_BUNDLE_SYMBOL_EXTRACTION_INVALID")
        support = extraction.get("support")
        if type(support) is not str or support not in ("unsupported", "best-effort"):
            _fail("PVC_BUNDLE_SYMBOL_EXTRACTION_INVALID")
        if support == "unsupported" and "status" in extraction:
            _fail("PVC_BUNDLE_SYMBOL_EXTRACTION_INVALID")
        if "status" in extraction and extraction["status"] not in (
                "success", "partial", "failed"):
            _fail("PVC_BUNDLE_SYMBOL_EXTRACTION_INVALID")
        if "extractorVersion" in extraction and type(
                extraction["extractorVersion"]) is not str:
            _fail("PVC_BUNDLE_SYMBOL_EXTRACTION_INVALID")
        if "byteLength" in source:
            exact_int(source["byteLength"], "PVC_BUNDLE_SOURCE_BYTE_LENGTH", 0)
        if "codec" in source and type(source["codec"]) is not str:
            _fail("PVC_BUNDLE_SOURCE_CODEC_INVALID")
        sources[index] = source
    if sorted(sources) != list(range(len(sources))):
        _fail("PVC_BUNDLE_SOURCE_INDEX_INVALID")

    # Review tablets use the same validated artifact boundary as SOURCE
    # tablets, but are text artifacts rather than images.  Keep the normal
    # SOURCE media contract exact; these two additional types are accepted
    # only when the corresponding tablet explicitly declares the review
    # profile.
    review_artifact_ids = {
        tablet.get("artifactId") for tablet in document["tablets"]
        if isinstance(tablet, dict) and tablet.get("profile") == "review"
        and isinstance(tablet.get("artifactId"), str)
    }
    artifacts = {}
    paths = set()
    for item in document["artifacts"]:
        artifact = _object(item, "PVC_BUNDLE_ARTIFACT_SHAPE")
        if any(key not in artifact for key in ("artifactId", "mediaType",
                                                "sha256")):
            _fail("PVC_BUNDLE_ARTIFACT_SHAPE")
        if type(artifact["artifactId"]) is not str:
            _fail("PVC_BUNDLE_ARTIFACT_ID_INVALID")
        artifact_id = artifact["artifactId"]
        if artifact_id in artifacts:
            _fail("PVC_BUNDLE_ARTIFACT_ID_INVALID")
        if type(artifact["mediaType"]) is not str:
            _fail("PVC_BUNDLE_ARTIFACT_MEDIA_TYPE_UNSUPPORTED")
        if artifact["mediaType"] not in _SOURCE_MEDIA_TYPES:
            if (artifact_id not in review_artifact_ids
                    or artifact["mediaType"] not in _REVIEW_MEDIA_TYPES):
                _fail("PVC_BUNDLE_ARTIFACT_MEDIA_TYPE_UNSUPPORTED")
        if type(artifact["sha256"]) is not str or not _SHA256.fullmatch(
                artifact["sha256"]):
            _fail("PVC_BUNDLE_ARTIFACT_INTEGRITY_METADATA_INVALID")
        relative = artifact.get("relativePath")
        if type(relative) is not str or relative in paths:
            _fail("PVC_BUNDLE_ARTIFACT_PATH_INVALID")
        if "byteLength" not in artifact:
            _fail("PVC_BUNDLE_ARTIFACT_INTEGRITY_METADATA_INVALID")
        exact_int(artifact["byteLength"],
                  "PVC_BUNDLE_ARTIFACT_INTEGRITY_METADATA_INVALID", 0)
        artifact_fd = -1
        try:
            artifact_fd = _open_confined(bundle_fd, relative, label="ARTIFACT")
            _hash_bounded(
                artifact_fd, artifact["byteLength"], artifact["sha256"],
                label="ARTIFACT",
                utf8=artifact["mediaType"] in _REVIEW_MEDIA_TYPES,
            )
        except OSError:
            _fail("PVC_BUNDLE_ARTIFACT_UNREADABLE")
        finally:
            try:
                os.close(artifact_fd)
            except OSError:
                pass
        artifacts[artifact_id] = artifact
        paths.add(relative)

    tablet_ids = set()
    page_indexes = set()
    for tablet in document["tablets"]:
        tablet = _object(tablet, "PVC_BUNDLE_TABLET_SHAPE")
        required = ("id", "pageIndex", "profile", "width", "height",
                    "spans", "artifactId")
        if set(required) - tablet.keys():
            _fail("PVC_BUNDLE_TABLET_SHAPE")
        if type(tablet["id"]) is not str:
            _fail("PVC_BUNDLE_TABLET_ID_INVALID")
        tablet_id = tablet["id"]
        if tablet_id in tablet_ids:
            _fail("PVC_BUNDLE_TABLET_ID_INVALID")
        tablet_ids.add(tablet_id)
        _identity_int(tablet["pageIndex"], "PVC_BUNDLE_TABLET_PAGE_INVALID", 1)
        if tablet["pageIndex"] in page_indexes:
            _fail("PVC_BUNDLE_TABLET_PAGE_INVALID")
        page_indexes.add(tablet["pageIndex"])
        if (type(tablet["profile"]) is not str
                or type(tablet["spans"]) is not list):
            _fail("PVC_BUNDLE_TABLET_SHAPE")
        _identity_int(tablet["width"], "PVC_BUNDLE_TABLET_SHAPE", 1)
        _identity_int(tablet["height"], "PVC_BUNDLE_TABLET_SHAPE", 1)
        artifact_id = tablet["artifactId"]
        if type(artifact_id) is not str:
            _fail("PVC_BUNDLE_TABLET_ARTIFACT_INVALID")
        if artifact_id not in artifacts:
            _fail("PVC_BUNDLE_TABLET_ARTIFACT_MISSING")
        if "digest" in tablet and (
                type(tablet["digest"]) is not str
                or not _SHA256.fullmatch(tablet["digest"])):
            _fail("PVC_BUNDLE_TABLET_DIGEST_INVALID")
        if "byteLength" in tablet and (
                type(tablet["byteLength"]) is not int
                or tablet["byteLength"] < 0
                or tablet["byteLength"] != artifacts[artifact_id]["byteLength"]):
            _fail("PVC_BUNDLE_TABLET_LENGTH_INVALID")
        if artifacts[artifact_id]["mediaType"] in _REVIEW_MEDIA_TYPES and (
                tablet["profile"] != "review"
                or "digest" not in tablet or "byteLength" not in tablet
                or type(tablet.get("provenance")) is not str
                or not tablet["provenance"]):
            _fail("PVC_BUNDLE_REVIEW_TABLET_METADATA_INVALID")
        for span in tablet["spans"]:
            span = _object(span, "PVC_BUNDLE_SPAN_SHAPE")
            if "sourceIndex" not in span:
                _fail("PVC_BUNDLE_SPAN_SOURCE_INVALID")
            _identity_int(span["sourceIndex"], "PVC_BUNDLE_SPAN_SOURCE_INVALID", 0)
            if span["sourceIndex"] not in sources:
                _fail("PVC_BUNDLE_SPAN_SOURCE_INVALID")
            for key in ("startLine", "endLine"):
                if key not in span or (span[key] is not None):
                    if key not in span or (span[key] is not None
                            and (type(span[key]) is not int
                                 or abs(span[key]) > _JS_SAFE_INTEGER
                                 or span[key] < 1)):
                        _fail("PVC_BUNDLE_SPAN_LINE_INVALID")
            if (span["startLine"] is not None and span["endLine"] is not None
                    and span["startLine"] > span["endLine"]):
                _fail("PVC_BUNDLE_SPAN_LINE_INVALID")
            if "bannerOnly" in span and type(span["bannerOnly"]) is not bool:
                _fail("PVC_BUNDLE_SPAN_BANNER_INVALID")

    for symbol in document["symbols"]:
        symbol = _object(symbol, "PVC_BUNDLE_SYMBOL_SHAPE")
        if any(key not in symbol for key in
               ("sourceIndex", "name", "qualifiedName", "kind", "line",
                "tabletIds")):
            _fail("PVC_BUNDLE_SYMBOL_SHAPE")
        _identity_int(symbol["sourceIndex"], "PVC_BUNDLE_SYMBOL_SOURCE_INVALID", 0)
        if (symbol["sourceIndex"] not in sources
                or any(type(symbol[key]) is not str for key in
                       ("name", "qualifiedName", "kind"))
                or type(symbol["tabletIds"]) is not list):
            _fail("PVC_BUNDLE_SYMBOL_SHAPE")
        _identity_int(symbol["line"], "PVC_BUNDLE_SYMBOL_LINE_INVALID", 1)
        if any(type(tablet_id) is not str or tablet_id not in tablet_ids
               for tablet_id in symbol["tabletIds"]):
            _fail("PVC_BUNDLE_SYMBOL_TABLET_INVALID")

    if "symbolDiagnostics" in document:
        if type(document["symbolDiagnostics"]) is not list:
            _fail("PVC_BUNDLE_SYMBOL_DIAGNOSTICS_SHAPE")
        for diagnostic in document["symbolDiagnostics"]:
            diagnostic = _object(diagnostic,
                                 "PVC_BUNDLE_SYMBOL_DIAGNOSTICS_SHAPE")
            if (type(diagnostic.get("sourceIndex")) is not int
                    or abs(diagnostic["sourceIndex"]) > _JS_SAFE_INTEGER
                    or diagnostic["sourceIndex"] not in sources
                    or type(diagnostic.get("message")) is not str):
                _fail("PVC_BUNDLE_SYMBOL_DIAGNOSTICS_SHAPE")

    if "metrics" in document:
        metrics = _object(document["metrics"], "PVC_BUNDLE_METRICS_SHAPE")
        if any(key not in metrics for key in ("sourceBytes", "sourceChars",
                                              "encodedChars", "removedChars",
                                              "reductionPercent")):
            _fail("PVC_BUNDLE_METRICS_SHAPE")
        if any(not _finite_metric(metrics[key])
               for key in ("sourceBytes", "sourceChars", "encodedChars",
                            "removedChars", "reductionPercent")):
            _fail("PVC_BUNDLE_METRICS_SHAPE")

    expected_id = _snapshot_identity_id(document)
    if document["snapshotId"] != expected_id:
        _fail("PVC_BUNDLE_SNAPSHOT_ID_MISMATCH")
    # Do not publish the parsed document until every validation above has
    # succeeded.  Freezing also copies every container, so this evidence does
    # not retain aliases to the mutable parser document.
    validated = replace(result)
    object.__setattr__(
        validated, "_validated_snapshot",
        PvcValidatedSnapshot(_deep_freeze_json(document), snapshot_bytes),
    )
    return validated


# Keep the operation-specific name convenient for callers that retain the
# bundle rather than thinking in terms of the prepare result.
validate_pvc_bundle = validate_prepare_result


def _validated_sources(root: Path, sources: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    root = Path(root).resolve()
    result = []
    for value in sources:
        if not isinstance(value, str) or not value:
            raise PvcRequestError("PVC_SOURCE_INVALID")
        path = Path(value)
        if (path.is_absolute() or ".." in path.parts or value.startswith("-")
                or any(char in value for char in "*?[")):
            raise PvcRequestError("PVC_SOURCE_INVALID")
        candidate = root / path
        try:
            # Reject symlinks in every component, including a symlink source.
            current = root
            for part in path.parts:
                current /= part
                if current.is_symlink():
                    raise PvcRequestError("PVC_SOURCE_SYMLINK")
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root) or not candidate.is_file():
                raise PvcRequestError("PVC_SOURCE_INVALID")
        except FileNotFoundError as error:
            raise PvcRequestError("PVC_SOURCE_INVALID") from error
        result.append(path.as_posix())
    return tuple(result)


@dataclass(frozen=True)
class PvcPrepareRequest:
    project_root: Path
    sources: tuple[str, ...]
    profile: str | None = None

    def __post_init__(self):
        if self.profile not in (None, "normal", "conservative"):
            raise PvcRequestError("PVC_PROFILE_INVALID")
        object.__setattr__(self, "project_root", Path(self.project_root).resolve())
        if not self.sources:
            raise PvcRequestError("PVC_SOURCE_REQUIRED")
        object.__setattr__(self, "sources",
                           _validated_sources(self.project_root, self.sources))

    def argv(self) -> tuple[str, ...]:
        args = ["prepare", "--cwd", str(self.project_root),
                "--output", "/var/tmp/bundle",
                "--work-root", "/var/tmp/work",
                "--state-root", "/var/tmp/state"]
        if self.profile is not None:
            args += ["--profile", self.profile]
        return tuple(args + list(self.sources))


def build_prepare_command(command,
                          request: PvcPrepareRequest) -> tuple[str, ...]:
    """Return the complete explicit argv, including the qualified executable."""
    return (str(command.guest_path), *request.argv())


@dataclass(frozen=True)
class PvcPrepareResult:
    """The non-durable result of one qualified PVC prepare operation.

    The scratch directory is intentionally retained on successful execution.
    These paths describe where this invocation wrote (or was expected to
    write) its output; they are not a claim that the output is a valid PVC
    bundle.  The next slice can therefore validate these exact bytes without
    invoking PVC again.
    """

    process: ProcessResult
    request: PvcPrepareRequest
    _validated_snapshot: PvcValidatedSnapshot | None = field(
        default=None, init=False, repr=False, compare=False)

    @property
    def validated_snapshot(self) -> PvcValidatedSnapshot | None:
        """The validator-published snapshot, if validation succeeded."""
        return self._validated_snapshot

    @property
    def scratch_path(self) -> Path:
        """Private operation scratch retained for a subsequent validator."""
        if self.process.scratch_path is None:
            raise RuntimeError("PVC result has no retained scratch")
        return self.process.scratch_path

    @property
    def bundle_path(self) -> Path:
        return self.scratch_path / "bundle"

    @property
    def work_path(self) -> Path:
        return self.scratch_path / "work"

    @property
    def stdout_path(self) -> Path:
        return self.process.stdout_path

    @property
    def stderr_path(self) -> Path:
        return self.process.stderr_path

    @property
    def process_succeeded(self) -> bool:
        return self.process.succeeded

    @property
    def bundle_validated(self) -> bool:
        """Process success is deliberately not bundle validation."""
        return self._validated_snapshot is not None

    @property
    def output_interpreted(self) -> bool:
        # Validation establishes trustworthy bytes, not Atlas meaning.
        return False

    def validate(self) -> "PvcPrepareResult":
        """Return this result with its retained bundle explicitly trusted."""
        if self._validated_snapshot is not None:
            return self
        return validate_prepare_result(self)


def execute_prepare(
    request: PvcPrepareRequest,
    *,
    capability_plan: CapabilityPlan,
    executor: OneShotExecutor,
) -> PvcPrepareResult:
    """Execute PVC with process output retained in its private scratch."""
    if not isinstance(capability_plan, CapabilityPlan):
        raise TypeError("capability_plan is required")
    command = capability_plan.command("pvc")
    return PvcPrepareResult(
        executor.run(command, request.argv(), cwd=request.project_root,
                     capability_plan=capability_plan,
                     stdout_path=None, stderr_path=None),
        request,
    )
