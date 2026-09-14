import hashlib
import json

import pytest
from dataclasses import replace

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionSpec, PreparedExecution
from tools.atlas_agent.pvc import (
    PvcBundleValidationError, _snapshot_identity_id, validate_prepare_result,
)
from tools.atlas_agent.pvc_context import (
    PvcContextError, PvcContextSelection, _stage_pvc_context,
)
from tools.atlas_agent.pvc_context import _ImageAuthority
from test_agent_pvc_validation import _result


def validated(tmp_path):
    return validate_prepare_result(_result(tmp_path))


def mixed_validated(tmp_path):
    result = _result(tmp_path)
    text = "exact review text \N{SNOWMAN}\n".encode()
    (result.bundle_path / "artifacts/review.txt").write_bytes(text)
    document = json.loads(result.stdout_path.read_text())
    document["tablets"].append({
        "id": "review-text", "pageIndex": 2, "profile": "review",
        "width": 1, "height": 1, "spans": [], "artifactId": "review-a",
        "digest": hashlib.sha256(b"tablet framing").hexdigest(),
        "byteLength": len(text), "provenance": "controller-review",
    })
    document["artifacts"].append({
        "artifactId": "review-a", "relativePath": "artifacts/review.txt",
        "mediaType": "text/vnd.atlas.review-diff", "byteLength": len(text),
        "sha256": hashlib.sha256(text).hexdigest(),
    })
    document["snapshotId"] = _snapshot_identity_id(document)
    encoded = json.dumps(document, ensure_ascii=False,
                          separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    result.bundle_path.joinpath("snapshot.json").write_bytes(encoded)
    return validate_prepare_result(result), text


def test_selection_is_validated_ordered_and_cleaned(tmp_path):
    result = validated(tmp_path)
    staged = _stage_pvc_context(PvcContextSelection(
        result, ("APO-VC-000001",), "execution path"))
    try:
        assert staged.image_authorities[0].codex_path.startswith("/proc/self/fd/")
        import os
        assert os.pread(staged.image_authorities[0].fd, 64, 0) == b"PNG fixture"
        assert "source.txt:1-1" in staged.framing
        assert "semantic truth" in staged.framing
        with pytest.raises(OSError):
            os.write(staged.image_authorities[0].fd, b"x")
    finally:
        root = staged.root
        staged.cleanup()
        assert not root.exists()


def test_unvalidated_or_tampered_artifact_fails_closed(tmp_path):
    result = _result(tmp_path)
    with pytest.raises(PvcContextError, match="VALIDATED"):
        PvcContextSelection(result, ("APO-VC-000001",))
    result = validate_prepare_result(result)
    (result.bundle_path / "artifacts/one.png").write_bytes(b"tampered")
    with pytest.raises(PvcContextError, match="MISMATCH"):
        _stage_pvc_context(PvcContextSelection(result, ("APO-VC-000001",)))


def test_typed_mixed_context_keeps_text_out_of_image_transport(tmp_path):
    result, text = mixed_validated(tmp_path)
    staged = _stage_pvc_context(PvcContextSelection(
        result, ("APO-VC-000001", "review-text")))
    try:
        assert len(staged.image_authorities) == 1
        assert len(staged.text_authorities) == 1
        assert staged.text_authorities[0].payload == text
        assert text in staged.framing.encode("utf-8")
        executor = CodexExecutor(executable=str(tmp_path / "codex"))
        base = dict(codex_profile=None, session_mode="fresh",
                    web_search="disabled", requested_reasoning_effort="low",
                    action="implementation")
        spec = type("Spec", (), {"repository_root": tmp_path})()
        command = executor._build_command(
            spec, base, staged.image_authorities)
        assert command.count("--image") == 1
        assert staged.text_authorities[0].artifact_id not in command
    finally:
        staged.cleanup()


def test_review_text_artifact_must_be_validated_utf8(tmp_path):
    result = _result(tmp_path)
    document = json.loads(result.stdout_path.read_text())
    document["tablets"][0].update(
        profile="review", digest=hashlib.sha256(b"tablet").hexdigest(),
        byteLength=1,
    )
    document["artifacts"][0].update(
        mediaType="text/vnd.atlas.review-task", byteLength=1,
        sha256=hashlib.sha256(b"\xff").hexdigest(),
    )
    result.bundle_path.joinpath("artifacts/one.png").write_bytes(b"\xff")
    document["snapshotId"] = _snapshot_identity_id(document)
    encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    result.bundle_path.joinpath("snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError, match="UTF8"):
        validate_prepare_result(result)


def test_selection_and_authority_are_nominal_not_duck_typed(tmp_path):
    result = validated(tmp_path)
    with pytest.raises(PvcContextError):
        _stage_pvc_context(type("Selection", (), {
            "result": result, "tablet_ids": ("APO-VC-000001",)
        })())
    with pytest.raises(TypeError):
        _ImageAuthority(object(), 0, "s", "t", "a", "0" * 64, 0, 0)


def test_codex_argv_uses_only_descriptor_authority(tmp_path):
    result = validated(tmp_path)
    staged = _stage_pvc_context(PvcContextSelection(result, ("APO-VC-000001",)))
    try:
        executor = CodexExecutor(executable=str(tmp_path / "codex"))
        base = dict(codex_profile=None, session_mode="fresh",
                    web_search="disabled", requested_reasoning_effort="low",
                    action="implementation")
        spec = type("Spec", (), {"repository_root": tmp_path})()
        command = executor._build_command(
            spec, base, staged.image_authorities)
        detail = command.index("--image-detail")
        image = command.index("--image")
        assert command[detail + 1] == "original"
        assert detail < image
        assert command[image + 1] == staged.image_authorities[0].codex_path
    finally:
        staged.cleanup()


def test_codex_command_has_repeated_images_and_legacy_has_none(tmp_path):
    executable = tmp_path / "codex"
    executable.write_bytes(b"x")
    image1, image2 = tmp_path / "1.png", tmp_path / "2.png"
    image1.write_bytes(b"1")
    image2.write_bytes(b"2")
    executor = CodexExecutor(executable=str(executable))
    base = dict(codex_profile=None, session_mode="fresh", web_search="disabled",
                requested_reasoning_effort="low", action="implementation")
    # A caller-supplied pathname is not an image authority.
    spec = type("Spec", (), {"repository_root": tmp_path,
                             "image_paths": (image1, image2)})()
    command = executor._build_command(spec, base)
    assert "--image" not in command
    assert "--image-detail" not in command
    legacy = executor._build_command(
        type("Spec", (), {"repository_root": tmp_path, "image_paths": ()})(), base)
    assert "--image" not in legacy
    assert "--image-detail" not in legacy


def test_image_authority_is_executor_issued_not_prepared_object_state(tmp_path, monkeypatch):
    """A forged, copied, stale, or cross-executor preparation has no images."""
    result = validated(tmp_path)
    staged = _stage_pvc_context(PvcContextSelection(result, ("APO-VC-000001",)))
    spec = ExecutionSpec(1, "0" * 64, "implementation", tmp_path / "prompt",
                         tmp_path, "execution", tmp_path)
    first = CodexExecutor(executable="/bin/true")
    second = CodexExecutor(executable="/bin/true")
    issued = PreparedExecution(spec, "codex", (), "test", {}, None, None)
    monkeypatch.setattr(first, "_prepare_execution",
                        lambda ignored_spec, ignored_authorities: issued)
    issued = first._prepare_execution_with_pvc(spec, staged)
    prepared = PreparedExecution(spec, "codex", (), "test", {}, None, object())
    assert first._take_prepared_pvc(prepared) is None
    assert second._take_prepared_pvc(issued) is None
    assert first._take_prepared_pvc(replace(issued)) is None
    owned = first._take_prepared_pvc(issued)
    assert owned is staged
    owned.cleanup()
    assert first._take_prepared_pvc(issued) is None
    assert issued.runtime_handle is None
