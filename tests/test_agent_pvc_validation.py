import hashlib
import json
import math
import shutil
from pathlib import Path

import pytest

from tools.atlas_agent.one_shot import ProcessResult
from tools.atlas_agent.pvc import (
    PvcBundleValidationError,
    PvcPrepareRequest,
    PvcPrepareResult,
    _snapshot_identity_id,
    validate_prepare_result,
)


def _result(tmp_path, document=None, *, stdout=None, exit_code=0):
    source = tmp_path / "source.txt"
    source.write_text("source")
    scratch = tmp_path / "scratch"
    bundle = scratch / "bundle"
    artifacts = bundle / "artifacts"
    artifacts.mkdir(parents=True)
    image = b"PNG fixture"
    (artifacts / "one.png").write_bytes(image)
    if document is None:
        document = {
            "schemaVersion": 1, "project": {"projectPrefix": "APO"},
            "sources": [{"sourceIndex": 0, "displayPath": "source.txt",
                         "language": "Python",
                         "contentSha256": hashlib.sha256(b"source").hexdigest(),
                         "symbolExtraction": {"support": "best-effort",
                                              "status": "success"}}],
            "tablets": [{"id": "APO-VC-000001", "pageIndex": 1,
                         "profile": "conservative", "width": 1056,
                         "height": 980, "spans": [{
                             "sourceIndex": 0, "startLine": 1, "endLine": 1
                         }], "artifactId": "a1"}],
            "symbols": [],
            "artifacts": [{
                "artifactId": "a1", "relativePath": "artifacts/one.png",
                "mediaType": "image/png", "byteLength": len(image),
                "sha256": hashlib.sha256(image).hexdigest(),
            }],
            "capabilities": {"lineProvenance": "complete",
                             "symbolExtraction": "per-source"},
        }
        identity = {k: document[k] for k in
                    ("schemaVersion", "sources", "tablets", "symbols")}
        identity["artifacts"] = [{k: a[k] for k in
                                  ("artifactId", "mediaType", "sha256")}
                                 for a in document["artifacts"]]
        identity["capabilities"] = document["capabilities"]
        encoded_identity = json.dumps(identity, ensure_ascii=False,
                                      separators=(",", ":")).encode()
        document["snapshotId"] = "scs1-" + hashlib.sha256(
            encoded_identity).hexdigest()
    encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
    (bundle / "snapshot.json").write_bytes(encoded)
    stdout_path = scratch / "stdout"
    stdout_path.write_bytes(encoded if stdout is None else stdout)
    stderr = scratch / "stderr"
    stderr.write_bytes(b"")
    process = ProcessResult(("pvc",), "now", "now", exit_code, stdout_path,
                            stderr, scratch_path=scratch)
    return PvcPrepareResult(process, PvcPrepareRequest(tmp_path, ("source.txt",)))


def _rewrite(result, document):
    encoded = json.dumps(document, ensure_ascii=False,
                          separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    (result.bundle_path / "snapshot.json").write_bytes(encoded)


def _identity_id(document):
    projection = {
        "schemaVersion": document["schemaVersion"],
        "sources": [],
        "tablets": [],
        "symbols": document["symbols"],
    }
    for source in document["sources"]:
        item = {k: source[k] for k in
                ("sourceIndex", "displayPath", "language", "contentSha256")}
        if "codec" in source:
            item["codec"] = source["codec"]
        item["symbolExtraction"] = source["symbolExtraction"]
        projection["sources"].append(item)
    projection["tablets"] = document["tablets"]
    projection["artifacts"] = [{k: a[k] for k in
                                ("artifactId", "mediaType", "sha256")}
                               for a in document["artifacts"]]
    projection["capabilities"] = document["capabilities"]
    return "scs1-" + hashlib.sha256(json.dumps(
        projection, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def test_real_shaped_bundle_validates_without_interpreting(tmp_path):
    result = validate_prepare_result(_result(tmp_path))
    assert result.bundle_validated
    assert not result.output_interpreted
    assert result.validated_snapshot.document["snapshotId"].startswith("scs1-")


@pytest.mark.parametrize("stdout", [
    b"{not json}\n",
    b'{"schemaVersion":1} trailing\n',
    b'{"schemaVersion":1} {"schemaVersion":1}\n',
    b"\xff",
])
def test_stdout_must_be_one_bounded_utf8_json_document(tmp_path, stdout):
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(_result(tmp_path, stdout=stdout))


def test_stdout_snapshot_mismatch_and_missing_snapshot(tmp_path):
    result = _result(tmp_path, stdout=b"{}")
    with pytest.raises(PvcBundleValidationError, match="MISMATCH|SHAPE|REQUIRED"):
        validate_prepare_result(result)
    shutil.rmtree(result.scratch_path)
    result = _result(tmp_path)
    (result.bundle_path / "snapshot.json").unlink()
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)


@pytest.mark.parametrize("change", [
    {"relativePath": "/tmp/image.png"},
    {"relativePath": "../image.png"},
    {"byteLength": 99},
    {"sha256": "0" * 64},
    {"mediaType": "text/plain"},
])
def test_artifact_integrity_and_path_contract(tmp_path, change):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["artifacts"][0].update(change)
    encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    (result.bundle_path / "snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)


def test_symlink_missing_artifact_and_tablet_binding_are_rejected(tmp_path):
    result = _result(tmp_path)
    artifact = result.bundle_path / "artifacts" / "one.png"
    artifact.unlink()
    artifact.symlink_to(result.request.project_root / "source.txt")
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)

    shutil.rmtree(result.scratch_path)
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["tablets"][0]["artifactId"] = "missing"
    encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    (result.bundle_path / "snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)


def test_process_failure_cannot_validate_and_failure_does_not_interpret(tmp_path):
    result = _result(tmp_path, exit_code=3)
    with pytest.raises(PvcBundleValidationError, match="PROCESS"):
        validate_prepare_result(result)
    assert not result.bundle_validated
    assert not result.output_interpreted


@pytest.mark.parametrize("mutate", [
    lambda d: d["sources"][0].update(displayPath="renamed.py"),
    lambda d: d["tablets"][0].update(profile="normal"),
])
def test_identity_members_require_a_new_snapshot_id(tmp_path, mutate):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    mutate(document)
    document["snapshotId"] = _identity_id(document)
    _rewrite(result, document)
    assert validate_prepare_result(result).bundle_validated


def test_identity_member_with_stale_snapshot_id_is_rejected(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["tablets"][0]["profile"] = "normal"
    _rewrite(result, document)
    with pytest.raises(PvcBundleValidationError, match="SNAPSHOT_ID_MISMATCH"):
        validate_prepare_result(result)


@pytest.mark.parametrize("mutate", [
    lambda d: d["sources"][0].update(byteLength=999),
    lambda d: d.update(metrics={"sourceBytes": 1, "sourceChars": 2,
                                "encodedChars": 3, "removedChars": 4,
                                "reductionPercent": 5}),
    lambda d: d["project"].update(projectPrefix="OTHER"),
])
def test_excluded_fields_do_not_change_snapshot_id(tmp_path, mutate):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    baseline = json.loads(result.stdout_path.read_text())
    mutate(document)
    assert _snapshot_identity_id(document) == _snapshot_identity_id(baseline)
    _rewrite(result, document)
    assert validate_prepare_result(result).bundle_validated


def test_excluded_artifact_fields_have_real_independent_identity_exclusions(
        tmp_path):
    result = _result(tmp_path)
    baseline = json.loads(result.stdout_path.read_text())
    for mutate in (
            lambda d: d["artifacts"][0].update(byteLength=999),
            lambda d: d["artifacts"][0].update(relativePath="artifacts/two.png"),
    ):
        changed = json.loads(json.dumps(baseline))
        mutate(changed)
        # These IDs come from the production projection, not this test's
        # historical fixture helper.
        assert _snapshot_identity_id(changed) == _snapshot_identity_id(baseline)

    # The changed path is also a valid bundle path, so this independently
    # proves the exclusion without conflating it with artifact verification.
    (result.bundle_path / "artifacts" / "two.png").write_bytes(b"PNG fixture")
    changed = json.loads(json.dumps(baseline))
    changed["artifacts"][0]["relativePath"] = "artifacts/two.png"
    _rewrite(result, changed)
    assert validate_prepare_result(result).bundle_validated


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schemaVersion=2),
    lambda d: d.update(project=[]),
    lambda d: d.update(sources=[{}]),
    lambda d: d.update(tablets=[{"tabletId": "t1"}]),
    lambda d: d.update(artifacts=[{}]),
    lambda d: d["artifacts"][0].update(byteLength=True),
    lambda d: d["tablets"][0]["spans"][0].update(startLine=0),
    lambda d: d["artifacts"][0].update(sha256="g" * 64),
    lambda d: d.update(snapshotId=""),
    lambda d: d["sources"].append(dict(d["sources"][0])),
    lambda d: d["tablets"].append(dict(d["tablets"][0])),
    lambda d: d["artifacts"].append(dict(d["artifacts"][0])),
    lambda d: d["tablets"][0].update(artifactId="missing"),
    lambda d: d["tablets"][0].update(pageIndex=True),
])
def test_canonical_snapshot_structure_and_closure_fail_closed(tmp_path, mutation):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    mutation(document)
    encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    (result.bundle_path / "snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)
    assert not result.bundle_validated
    assert not result.output_interpreted


@pytest.mark.parametrize("path,value", [
    (("tablets", 0, "width"), 1056.0),
    (("tablets", 0, "width"), -0.0),
    (("tablets", 0, "width"), 1e-7),
    (("tablets", 0, "width"), True),
    (("tablets", 0, "width"), 2 ** 53),
    (("tablets", 0, "width"), math.nan),
    (("tablets", 0, "height"), math.inf),
])
def test_identity_numeric_domain_is_exact_safe_integer(tmp_path, path, value):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    target = document
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    _rewrite(result, document)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)


def test_identity_safe_integer_boundary_is_accepted(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["tablets"][0]["width"] = 2 ** 53 - 1
    document["snapshotId"] = _identity_id(document)
    _rewrite(result, document)
    assert validate_prepare_result(result).bundle_validated


@pytest.mark.parametrize("value", [True, 1056.0, 2 ** 53])
def test_identity_numeric_boundary_rejections_are_explicit(tmp_path, value):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["tablets"][0]["width"] = value
    _rewrite(result, document)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)


@pytest.mark.parametrize("value", [1.5, True, math.nan, math.inf, -math.inf])
def test_metrics_accept_finite_float_and_reject_nonfinite_or_bool(
        tmp_path, value):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["metrics"] = {"sourceBytes": value, "sourceChars": 2,
                           "encodedChars": 3, "removedChars": 4,
                           "reductionPercent": 5}
    # NaN and infinities are deliberately written as JSON spellings here;
    # the parser's parse_constant hook must reject them.
    _rewrite(result, document)
    if value == 1.5:
        assert validate_prepare_result(result).bundle_validated
    else:
        with pytest.raises(PvcBundleValidationError):
            validate_prepare_result(result)


def test_metrics_changes_do_not_change_snapshot_id(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["metrics"] = {"sourceBytes": 1.5, "sourceChars": 2,
                           "encodedChars": 3, "removedChars": 4,
                           "reductionPercent": 5}
    assert _identity_id(document) == _identity_id(
        json.loads(result.stdout_path.read_text()))
    _rewrite(result, document)
    assert validate_prepare_result(result).bundle_validated


@pytest.mark.parametrize("location", [
    ("sources", 0, "contentSha256"),
    ("artifacts", 0, "mediaType"),
    ("artifacts", 0, "sha256"),
    ("tablets", 0, "spans", 0, "sourceIndex"),
])
@pytest.mark.parametrize("bad", [[], {}, None])
def test_malformed_nested_values_fail_with_bundle_error(tmp_path, location, bad):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    target = document
    for part in location[:-1]:
        target = target[part]
    target[location[-1]] = bad
    _rewrite(result, document)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)


@pytest.mark.parametrize("value", ["\ud800", "\udc00"],
                         ids=["lone-high-surrogate", "lone-low-surrogate"])
def test_lone_surrogate_identity_string_is_controlled_rejection(tmp_path,
                                                                 value):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["sources"][0]["displayPath"] = value
    encoded = json.dumps(document, ensure_ascii=True,
                         separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    result.bundle_path.joinpath("snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError, match="IDENTITY_STRING"):
        validate_prepare_result(result)


# Expected IDs are literal SHA-256 vectors independently produced from
# JavaScript JSON.stringify compact output (not generated by this test or
# Python's json.dumps).
@pytest.mark.parametrize("value,expected", [
    ("ASCII", "scs1-1fec00eb2f1bf55fc9d4a751834c1c430c0612ba5dc375bf896606c7152ac387"),
    ("café", "scs1-57546dff820af939ffc7835b6ed43c2213f22e27e4fb5e4696697b987696efe9"),
    ("😀", "scs1-30fbfb87a48e67e5f327d981d8a666faa86ddba22ea134f138d7ccad9978cf77"),
    ('quote"', "scs1-392585155d68c4c02ff088621ed7f180208b38ca84e9aec5fb668437b68776ef"),
    ("slash\\", "scs1-0ea83ab9699dc902ba2b81b5183965e579e750fce8b2ad1b30c27343d8b7accd"),
    ("line\ncontrol", "scs1-11cdfef636badd814cb15c97798d0eb1178d037fea43f07bbab00bb44c2b8346"),
])
def test_identity_unicode_golden_vectors(tmp_path, value, expected):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["sources"][0]["displayPath"] = value
    document["snapshotId"] = expected
    _rewrite(result, document)
    assert validate_prepare_result(result).bundle_validated


def test_identity_valid_surrogate_pair_normalizes_to_unicode_scalar(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["sources"][0]["displayPath"] = "\ud83d\ude00"
    document["snapshotId"] = (
        "scs1-30fbfb87a48e67e5f327d981d8a666faa86ddba22ea134f138d7ccad9978cf77"
    )
    encoded = json.dumps(document, ensure_ascii=True,
                          separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    result.bundle_path.joinpath("snapshot.json").write_bytes(encoded)
    assert validate_prepare_result(result).bundle_validated


@pytest.mark.parametrize("bad_path", ["artifacts/ nul\x00.png",
                                      "artifacts/\ud800.png",
                                      "artifacts/\udc00.png"])
def test_malformed_artifact_paths_are_controlled_errors(tmp_path, bad_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["artifacts"][0]["relativePath"] = bad_path
    encoded = json.dumps(document, ensure_ascii=True,
                          separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    result.bundle_path.joinpath("snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError, match="ARTIFACT_PATH_INVALID"):
        validate_prepare_result(result)


def test_unknown_artifact_id_field_does_not_redirect_canonical_binding(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["artifacts"][0]["id"] = "not-the-canonical-id"
    _rewrite(result, document)
    assert validate_prepare_result(result).bundle_validated


def test_artifact_id_alias_cannot_rescue_or_redirect_binding(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["artifacts"][0]["artifactId"] = "A"
    document["artifacts"][0]["id"] = "B"
    document["tablets"][0]["artifactId"] = "B"
    document["snapshotId"] = _snapshot_identity_id(document)
    _rewrite(result, document)
    with pytest.raises(PvcBundleValidationError,
                       match="PVC_BUNDLE_TABLET_ARTIFACT_MISSING"):
        validate_prepare_result(result)


def test_canonical_artifact_binding_ignores_additive_id_alias(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["artifacts"][0]["artifactId"] = "A"
    document["artifacts"][0]["id"] = "B"
    document["tablets"][0]["artifactId"] = "A"
    document["snapshotId"] = _snapshot_identity_id(document)
    _rewrite(result, document)
    assert validate_prepare_result(result).bundle_validated
