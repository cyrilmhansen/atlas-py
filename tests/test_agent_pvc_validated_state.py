from dataclasses import FrozenInstanceError, replace
import json

import pytest

from tools.atlas_agent.one_shot import ProcessResult
from tools.atlas_agent import pvc as pvc_module
from tools.atlas_agent.pvc import (
    PvcBundleValidationError,
    PvcPrepareResult,
    _snapshot_identity_id,
    validate_prepare_result,
)

from test_agent_pvc_validation import _result


def _canonical_validated_result(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["symbols"] = [{
        "sourceIndex": 0,
        "name": "parse",
        "qualifiedName": "module.parse",
        "kind": "function",
        "line": 1,
        "tabletIds": ["APO-VC-000001"],
    }]
    document["symbolDiagnostics"] = [{
        "sourceIndex": 0,
        "message": "symbol metadata is partial",
    }]
    document["metrics"] = {
        "sourceBytes": 6,
        "sourceChars": 6,
        "encodedChars": 6,
        "removedChars": 0,
        "reductionPercent": 0,
    }
    document["snapshotId"] = _snapshot_identity_id(document)
    encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    result.bundle_path.joinpath("snapshot.json").write_bytes(encoded)
    return result, document


def test_validated_state_is_not_a_supported_constructor_input(tmp_path):
    result = _result(tmp_path)
    with pytest.raises(TypeError):
        PvcPrepareResult(result.process, result.request,
                         validated_snapshot=None)
    with pytest.raises(TypeError):
        PvcPrepareResult(result.process, result.request,
                         _validated_snapshot=None)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.validated_snapshot = object()
    assert not result.bundle_validated


def test_replace_cannot_inject_or_copy_validation_authority(tmp_path):
    result = _result(tmp_path)
    with pytest.raises((TypeError, ValueError)):
        replace(result, _validated_snapshot=object())

    validated = validate_prepare_result(result)
    assert validated.bundle_validated
    copied = replace(validated, process=result.process)
    assert not copied.bundle_validated
    assert copied.validated_snapshot is None


def test_validated_snapshot_is_deeply_immutable_and_alias_isolated(
        tmp_path, monkeypatch):
    result, _ = _canonical_validated_result(tmp_path)

    original_freezer = pvc_module._deep_freeze_json
    freezer_roots = []
    freezer_depth = 0

    def freezing_spy(value):
        nonlocal freezer_depth
        if freezer_depth == 0:
            freezer_roots.append(value)
        freezer_depth += 1
        try:
            return original_freezer(value)
        finally:
            freezer_depth -= 1

    # The original freezer recursively calls this module-level name, so the
    # depth guard identifies the one publication root without replacing the
    # freezer or intercepting validation.
    monkeypatch.setattr(pvc_module, "_deep_freeze_json", freezing_spy)
    validated = validate_prepare_result(result)

    assert len(freezer_roots) == 1
    captured = freezer_roots[0]
    assert type(captured) is dict
    assert type(captured["sources"]) is list
    assert type(captured["sources"][0]["symbolExtraction"]) is dict
    assert validated.validated_snapshot is not None
    assert validated.bundle_validated
    assert not validated.output_interpreted

    document = validated.validated_snapshot.document

    with pytest.raises(TypeError):
        document["project"] = {}
    with pytest.raises(TypeError):
        document["sources"][0]["displayPath"] = "changed.py"
    with pytest.raises(TypeError):
        document["sources"][0]["symbolExtraction"]["status"] = "failed"
    with pytest.raises(TypeError):
        document["tablets"][0]["profile"] = "normal"
    with pytest.raises(TypeError):
        document["tablets"][0]["spans"][0]["startLine"] = 2
    with pytest.raises(TypeError):
        document["symbols"][0]["name"] = "other"
    with pytest.raises(TypeError):
        document["symbols"][0]["tabletIds"][0] = "other"
    with pytest.raises(AttributeError):
        document["symbols"][0]["tabletIds"].append("other")
    with pytest.raises(TypeError):
        document["symbolDiagnostics"][0]["message"] = "changed"
    with pytest.raises(TypeError):
        document["artifacts"][0]["mediaType"] = "image/jpeg"
    with pytest.raises(TypeError):
        document["capabilities"]["lineProvenance"] = "none"
    with pytest.raises(TypeError):
        document["metrics"]["sourceBytes"] = 99
    with pytest.raises(TypeError):
        document["tablets"][0]["spans"] += ({},)
    assert isinstance(document["tablets"], tuple)

    def assert_snapshot_unchanged():
        assert document["sources"][0]["displayPath"] == "source.txt"
        assert document["sources"][0]["symbolExtraction"]["status"] == "success"
        assert document["tablets"][0]["spans"][0]["startLine"] == 1
        assert document["tablets"][0]["spans"][0]["endLine"] == 1
        assert document["symbols"][0]["name"] == "parse"
        assert document["symbols"][0]["tabletIds"] == ("APO-VC-000001",)
        assert document["symbolDiagnostics"][0]["message"] == (
            "symbol metadata is partial")
        assert document["artifacts"][0]["mediaType"] == "image/png"
        assert document["capabilities"]["lineProvenance"] == "complete"
        assert document["metrics"]["sourceBytes"] == 6

    # Mutate the exact parsed document passed to the production freezer after
    # publication.  These checks are distinct from the exposed mutation
    # attempts above and reject shallow proxying or nested container aliases.
    mutations = (
        lambda: captured["sources"][0]["symbolExtraction"].__setitem__(
            "status", "failed"),
        lambda: captured["sources"][0].__setitem__(
            "displayPath", "changed.py"),
        lambda: captured["tablets"][0]["spans"][0].__setitem__(
            "startLine", 2),
        lambda: captured["symbols"][0].__setitem__("name", "other"),
        lambda: captured["symbols"][0]["tabletIds"].__setitem__(0, "other"),
        lambda: captured["symbols"][0]["tabletIds"].append("extra"),
        lambda: captured["symbolDiagnostics"][0].__setitem__(
            "message", "changed"),
        lambda: captured["artifacts"][0].__setitem__(
            "mediaType", "image/jpeg"),
        lambda: captured["capabilities"].__setitem__(
            "lineProvenance", "none"),
        lambda: captured["metrics"].__setitem__("sourceBytes", 99),
    )
    for mutate in mutations:
        mutate()
        assert_snapshot_unchanged()


@pytest.mark.parametrize("process_change", [
    {"exit_code": 3},
    {"timed_out": True},
    {"output_limit_exceeded": "STDOUT"},
])
def test_process_failure_cannot_publish_validated_state(tmp_path, process_change):
    result = _result(tmp_path)
    failed_process = replace(result.process, **process_change)
    result = replace(result, process=failed_process)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)
    assert not result.bundle_validated
    assert result.validated_snapshot is None
    assert not result.output_interpreted


@pytest.mark.parametrize("kind", ["malformed", "artifact"])
def test_validation_failure_cannot_publish_validated_state(tmp_path, kind):
    result = _result(tmp_path)
    if kind == "malformed":
        payload = b"{not json}\n"
    else:
        document = json.loads(result.stdout_path.read_text())
        document["artifacts"][0]["sha256"] = "0" * 64
        payload = (json.dumps(document, separators=(",", ":")).encode() + b"\n")
    result.stdout_path.write_bytes(payload)
    result.bundle_path.joinpath("snapshot.json").write_bytes(payload)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)
    assert not result.bundle_validated
    assert result.validated_snapshot is None
    assert not result.output_interpreted
