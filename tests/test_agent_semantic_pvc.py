import json
import hashlib
import os
import subprocess

import pytest

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionResult, PreparedExecution, utc_now
from tools.atlas_agent.semantic import (
    SemanticResultError, build_semantic_tablet,
)
from tools.atlas_agent.pvc_context import _stage_pvc_context
from tools.atlas_agent.pvc_context import PvcContextSelection
from tools.atlas_agent.pvc import PvcBundleValidationError, validate_prepare_result
from tools.atlas_agent.pvc import _snapshot_identity_id
from tools.atlas_agent.workflow import Workflow


def semantic_bytes(**changes):
    document = {
        "schema": "atlas-rust-semantic/1",
        "query": {"kind": "hover", "path": "src/lib.rs",
                  "line": 0, "character": 1},
        "authority": {"executable": "/usr/bin/rust-analyzer",
                      "version": "2026"},
        "repositoryWitness": {"head": "a" * 40},
        "positionEncoding": "utf-8",
        "result": {"kind": "hover", "value": "u32"},
    }
    document.update(changes)
    return json.dumps(document, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode() + b"\n"


def test_semantic_identity_and_exact_text_transport():
    payload = semantic_bytes()
    one, two = build_semantic_tablet(payload), build_semantic_tablet(payload)
    assert (one.digest, one.tablet_id, one.artifact_id, one.provenance) == (
        two.digest, two.tablet_id, two.artifact_id, two.provenance)
    selection = one.pvc_context()
    assert selection.result.validated_snapshot.document["snapshotId"] == (
        two.pvc_context().result.validated_snapshot.document["snapshotId"])
    staged = _stage_pvc_context(selection)
    try:
        assert staged.text_authorities[0].payload == payload
        assert payload in staged.framing.encode()
        assert not staged.image_authorities
    finally:
        staged.cleanup()


def test_semantic_wrong_tablet_digest_rejected_after_snapshot_recomputed():
    selection = build_semantic_tablet(semantic_bytes()).pvc_context()
    result = selection.result
    document = json.loads(result.stdout_path.read_text())
    artifact = document["artifacts"][0]
    assert artifact["sha256"] == hashlib.sha256(
        (result.bundle_path / artifact["relativePath"]).read_bytes()).hexdigest()
    assert artifact["byteLength"] == len(
        (result.bundle_path / artifact["relativePath"]).read_bytes())
    document["tablets"][0]["digest"] = "0" * 64
    document["snapshotId"] = _snapshot_identity_id(document)
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    (result.bundle_path / "snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError,
                       match="PVC_BUNDLE_SEMANTIC_TABLET_METADATA_INVALID"):
        validate_prepare_result(result)


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda d: d["tablets"][0].update(profile="source"),
                 id="semantic-media-with-nonsemantic-profile"),
    pytest.param(lambda d: d["artifacts"][0].update(
        mediaType="image/png"), id="semantic-profile-with-incompatible-media"),
])
def test_semantic_media_and_profile_must_match_retained_bundle(mutate):
    selection = build_semantic_tablet(semantic_bytes()).pvc_context()
    result = selection.result
    document = json.loads(result.stdout_path.read_text())
    mutate(document)
    document["snapshotId"] = _snapshot_identity_id(document)
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    (result.bundle_path / "snapshot.json").write_bytes(encoded)
    with pytest.raises(PvcBundleValidationError):
        validate_prepare_result(result)


def test_mixed_source_image_and_semantic_text_staging_preserves_order():
    payload = semantic_bytes()
    semantic = build_semantic_tablet(payload).pvc_context()
    result = semantic.result
    image = b"\x89PNG mixed fixture"
    image_id = "source-image"
    (result.bundle_path / "artifacts" / "source.png").write_bytes(image)
    document = json.loads(result.stdout_path.read_text())
    document["artifacts"].append({
        "artifactId": image_id, "relativePath": "artifacts/source.png",
        "mediaType": "image/png", "byteLength": len(image),
        "sha256": hashlib.sha256(image).hexdigest(),
    })
    document["tablets"].insert(0, {
        "id": "source-image-tablet", "pageIndex": 1, "profile": "source",
        "width": 1, "height": 1,
        "spans": [{"sourceIndex": 0, "startLine": None, "endLine": None}],
        "artifactId": image_id,
    })
    # The semantic tablet must move to the next page when this fixture is
    # combined; selection order below intentionally differs from page order.
    document["tablets"][1]["pageIndex"] = 2
    document["snapshotId"] = _snapshot_identity_id(document)
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode() + b"\n"
    result.stdout_path.write_bytes(encoded)
    (result.bundle_path / "snapshot.json").write_bytes(encoded)
    result = validate_prepare_result(result)
    selection = PvcContextSelection(
        result, (document["tablets"][1]["id"], document["tablets"][0]["id"]),
        purpose="mixed transport")
    staged = _stage_pvc_context(selection)
    try:
        assert len(staged.image_authorities) == 1
        assert len(staged.text_authorities) == 1
        assert staged.text_authorities[0].payload == payload
        assert staged.image_authorities[0].ordinal == 1
        assert staged.text_authorities[0].ordinal == 0
        assert "--image" not in staged.framing
        assert payload in staged.framing.encode()
        assert image not in staged.framing.encode()
        assert staged.image_authorities[0].codex_path.startswith("/proc/self/fd/")
    finally:
        staged.cleanup()
        assert staged.image_authorities[0]._closed
        assert staged.text_authorities[0]._closed


def test_semantic_cleanup_closes_authority_and_is_idempotent():
    selection = build_semantic_tablet(semantic_bytes()).pvc_context()
    staged = _stage_pvc_context(selection)
    text = staged.text_authorities[0]
    root = staged.root
    staged.cleanup()
    assert text._closed
    assert not root.exists()
    with pytest.raises(OSError):
        os.fstat(text.fd)
    staged.cleanup()
    assert text._closed


@pytest.mark.parametrize("payload", [
    b"{",
    semantic_bytes(schema="wrong"),
    semantic_bytes(positionEncoding="utf-16"),
    semantic_bytes(result=None),
    b'{"authority":{},"authority":{},"positionEncoding":"utf-8",'
    b'"query":{},"repositoryWitness":{},"result":{},'
    b'"schema":"atlas-rust-semantic/1"}\n',
    b'{"authority":{},"positionEncoding":"utf-8","query":{},'
    b'"repositoryWitness":{},"result":{"x":NaN},'
    b'"schema":"atlas-rust-semantic/1"}\n',
])
def test_semantic_result_rejects_invalid_canonical_bytes(payload):
    with pytest.raises(SemanticResultError, match="INVALID"):
        build_semantic_tablet(payload)


def test_semantic_change_changes_snapshot_identity():
    a = build_semantic_tablet(semantic_bytes())
    b = build_semantic_tablet(semantic_bytes(result={"kind": "hover",
                                                      "value": "i64"}))
    assert a.digest != b.digest
    assert (a.tablet_id, a.artifact_id) != (b.tablet_id, b.artifact_id)
    assert (a.pvc_context().result.validated_snapshot.document["snapshotId"]
            != b.pvc_context().result.validated_snapshot.document["snapshotId"])


def test_semantic_non_utf8_is_rejected():
    with pytest.raises(SemanticResultError):
        build_semantic_tablet(b"\xff")


def test_semantic_reaches_workflow_effective_context(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path,
                   check=True)
    (tmp_path / "tracked.txt").write_text("one\n")
    (tmp_path / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\nallowed_untracked = []\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                   cwd=tmp_path).decode().strip()
    workflow = Workflow(tmp_path)
    workflow.init()
    prompt = (f'+++\nschema = "atlas-agent-prompt/1"\ngeneration = 1\n'
              f'parent = "genesis"\ncheckpoint = "semantic"\n'
              f'action = "implementation"\nexpected_head = "{head}"\n'
              'session_mode = "fresh"\n+++\nsemantic\n').encode()
    (workflow.base / "inbox" / "prompt.txt").write_bytes(prompt)
    workflow.ingest()
    payload = semantic_bytes()
    selection = build_semantic_tablet(payload).pvc_context()

    class Capture(CodexExecutor):
        supports_authoritative_pvc_context = True

        def __init__(self):
            super().__init__(executable="/bin/true")
            self.supplied = None
            self.argv = None

        def prepare_execution(self, spec):
            return PreparedExecution(spec, "capture", ("capture",), "capture/1",
                                     self._envelope(), spec.policy_snapshot)

        def run_execution(self, prepared):
            self.supplied, self.argv = prepared.spec.prompt_bytes, prepared.command
            report = prepared.spec.report_dir
            report.mkdir(parents=True, exist_ok=True)
            (report / "stdout.log").write_bytes(b"")
            (report / "stderr.log").write_bytes(b"")
            now = utc_now()
            return ExecutionResult(
                str(prepared.spec.execution_id), "capture", list(prepared.command),
                "capture/1", now, now, 0,
                str((report / "stdout.log").relative_to(tmp_path)),
                str((report / "stderr.log").relative_to(tmp_path)), None, "success",
                str((report / "result.json").relative_to(tmp_path)),
                prepared.permission_envelope,
                execution_input_sha256=hashlib.sha256(self.supplied).hexdigest())

    capture = Capture()
    workflow.execute(1, capture, pvc_context=selection)
    assert payload in capture.supplied
    assert "--image" not in capture.argv
    assert workflow._state()["generations"]["1"]["execution"][
        "effective_prompt_sha256"] == hashlib.sha256(capture.supplied).hexdigest()
