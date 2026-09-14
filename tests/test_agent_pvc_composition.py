"""Qualification evidence for explicit, ordered PVC context composition."""
import hashlib
import json
import os
import subprocess

import pytest

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionResult, PreparedExecution, utc_now
from tools.atlas_agent.pvc_context import (
    PvcContextComposition, PvcContextError, PvcContextSelection,
    _stage_pvc_composition, _stage_pvc_context,
)
from tools.atlas_agent.pvc import _snapshot_identity_id, validate_prepare_result
from tools.atlas_agent.review import build_review_package
from tools.atlas_agent.semantic import build_semantic_tablet
from tools.atlas_agent.workflow import Workflow
from test_agent_pvc_validation import _result
from test_agent_semantic_pvc import semantic_bytes


def _review(tmp_path):
    tmp_path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path,
                   check=True)
    (tmp_path / "tracked.txt").write_text("before\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                                   text=True).strip()
    (tmp_path / "tracked.txt").write_text("after\n")
    return build_review_package(tmp_path, head, "TASK",
                                ["tracked.txt"]).pvc_context("r")


def _members(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    review = _review(tmp_path / "repo")
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = PvcContextSelection(
        validate_prepare_result(_result(source_root)),
        ("APO-VC-000001",), "s")
    semantic_payload = semantic_bytes(result={"kind": "hover", "value": "x"})
    semantic = build_semantic_tablet(semantic_payload).pvc_context("s")
    return review, source, semantic, semantic_payload


def test_full_explicit_composition_crosses_workflow_and_preserves_authority(
        tmp_path):
    review, source, semantic, semantic_payload = _members(tmp_path)
    composition = PvcContextComposition((review, source, semantic), "q")
    review_payloads = [
        (review.result.bundle_path / artifact["relativePath"]).read_bytes()
        for artifact in review.result.validated_snapshot.document["artifacts"]
    ]
    staged = _stage_pvc_composition(composition)
    try:
        assert [a.payload for a in staged.text_authorities] == [
            *review_payloads,
            semantic_payload,
        ]
        assert len(staged.image_authorities) == 1
        assert staged.image_authorities[0].ordinal == 2
        assert os.pread(staged.image_authorities[0].fd, 100, 0) == b"PNG fixture"
        assert "PVC composition selection 1 begin" in staged.framing
        assert staged.framing.index("selection 1 begin") < staged.framing.index(
            "selection 2 begin") < staged.framing.index("selection 3 begin")
        assert staged.framing.index("payload-begin") < staged.framing.index(
            "payload-end")
    finally:
        staged.cleanup()

    root = tmp_path / "workflow"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for key, value in (("user.email", "test@example.invalid"),
                       ("user.name", "test")):
        subprocess.run(["git", "config", key, value], cwd=root, check=True)
    (root / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\nallowed_untracked = []\n')
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                   text=True).strip()
    workflow = Workflow(root)
    workflow.init()
    prompt = (f'+++\nschema = "atlas-agent-prompt/1"\ngeneration = 1\n'
              f'parent = "genesis"\ncheckpoint = "composition"\n'
              f'action = "implementation"\nexpected_head = "{head}"\n'
              'session_mode = "fresh"\n+++\naccepted\n').encode()
    (workflow.base / "inbox" / "prompt.txt").write_bytes(prompt)
    workflow.ingest()

    class Capture(CodexExecutor):
        supports_authoritative_pvc_context = True
        def __init__(self):
            super().__init__(executable="/bin/true")
            self.input = None
            self.command = None
        def prepare_execution(self, spec):
            return PreparedExecution(spec, "capture", ("capture",), "capture/1",
                                     self._envelope(), spec.policy_snapshot)
        def run_execution(self, prepared):
            self.input, self.command = prepared.spec.prompt_bytes, prepared.command
            prepared.spec.report_dir.mkdir(parents=True, exist_ok=True)
            (prepared.spec.report_dir / "stdout.log").write_bytes(b"")
            (prepared.spec.report_dir / "stderr.log").write_bytes(b"")
            now = utc_now()
            return ExecutionResult(str(prepared.spec.execution_id), "capture",
                list(prepared.command), "capture/1", now, now, 0,
                "reports/x/stdout.log", "reports/x/stderr.log", None, "success",
                "reports/x/result.json", prepared.permission_envelope,
                execution_input_sha256=hashlib.sha256(self.input).hexdigest())
    capture = Capture()
    workflow.execute(1, capture, pvc_context=composition)
    assert capture.input is not None
    assert all(payload in capture.input for payload in review_payloads)
    assert semantic_payload in capture.input
    assert hashlib.sha256(capture.input).hexdigest() == workflow._state()[
        "generations"]["1"]["execution"]["effective_prompt_sha256"]
    assert capture.command.count("--image") == 1
    assert all(artifact["artifactId"] not in capture.command
               for artifact in review.result.validated_snapshot.document[
                   "artifacts"])


def test_composition_is_deterministic_and_order_sensitive(tmp_path):
    a, b, c, _ = _members(tmp_path)
    first = _stage_pvc_composition(PvcContextComposition((a, b, c)))
    second = _stage_pvc_composition(PvcContextComposition((a, b, c)))
    reverse = _stage_pvc_composition(PvcContextComposition((c, b, a)))
    try:
        assert first.framing == second.framing
        assert [x.payload for x in first.text_authorities] == [
            x.payload for x in second.text_authorities]
        assert first.framing.encode() + b"".join(
            x.payload for x in first.text_authorities) == second.framing.encode() + b"".join(
                x.payload for x in second.text_authorities)
    finally:
        first.cleanup(); second.cleanup(); reverse.cleanup()


def test_order_sensitivity_changes_framing_and_payload_order_not_bytes(tmp_path):
    a, b, c, _ = _members(tmp_path)
    forward = _stage_pvc_composition(PvcContextComposition((a, b, c)))
    swapped = _stage_pvc_composition(PvcContextComposition((c, b, a)))
    try:
        assert forward.framing != swapped.framing
        assert sorted(x.payload for x in forward.text_authorities) == sorted(
            x.payload for x in swapped.text_authorities)
        assert b"".join(x.payload for x in forward.text_authorities) != b"".join(
            x.payload for x in swapped.text_authorities)
        assert hashlib.sha256(forward.framing.encode() + b"".join(
            x.payload for x in forward.text_authorities)).hexdigest() != \
            hashlib.sha256(swapped.framing.encode() + b"".join(
                x.payload for x in swapped.text_authorities)).hexdigest()
    finally:
        forward.cleanup(); swapped.cleanup()


def test_single_selection_framing_and_ordinals_remain_historical(tmp_path):
    review, source, semantic, _ = _members(tmp_path)
    for selection in (review, source, semantic):
        direct = _stage_pvc_context(selection)
        composed = _stage_pvc_composition(PvcContextComposition((selection,)))
        try:
            begin = composed.framing.index("PVC source tablets")
            end = composed.framing.index("PVC composition selection 1 end")
            assert composed.framing[begin:end].rstrip() + "\n" == direct.framing
            assert [x.ordinal for x in direct.image_authorities] == [
                x.ordinal for x in composed.image_authorities]
            assert [x.ordinal for x in direct.text_authorities] == [
                x.ordinal for x in composed.text_authorities]
        finally:
            direct.cleanup(); composed.cleanup()


def test_no_context_keeps_prompt_and_parent_semantics(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\nallowed_untracked = []\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    w = Workflow(tmp_path); w.init()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                                   text=True).strip()
    p = (f'+++\nschema = "atlas-agent-prompt/1"\ngeneration = 1\n'
         f'parent = "genesis"\ncheckpoint = "none"\naction = "implementation"\n'
         f'expected_head = "{head}"\nsession_mode = "fresh"\n+++\nhello\n').encode()
    (w.base / "inbox" / "prompt.txt").write_bytes(p); w.ingest()
    from tools.atlas_agent.executor import FakeExecutor
    w.execute(1, FakeExecutor())
    execution = w._state()["generations"]["1"]["execution"]
    assert execution["prompt_input"] == "accepted_prompt_plus_atlas_context"
    assert b"PVC context composition" not in (
        w.base / execution["effective_prompt_path"]).read_bytes()


def test_invalid_compositions_fail_closed(tmp_path):
    with pytest.raises(PvcContextError, match="EMPTY"):
        PvcContextComposition(())
    with pytest.raises(PvcContextError, match="MEMBER"):
        PvcContextComposition((object(),))
    (tmp_path / "raw").mkdir()
    raw = _result(tmp_path / "raw")
    with pytest.raises(PvcContextError, match="VALIDATED"):
        PvcContextComposition((PvcContextSelection(raw, ("APO-VC-000001",)),))


def test_composition_staging_is_failure_atomic(tmp_path, monkeypatch):
    _, source, semantic, _ = _members(tmp_path)
    import tools.atlas_agent.pvc_context as module
    original = module._stage_pvc_context
    staged_first = []
    def fail_later(selection, offset=0):
        if staged_first:
            raise PvcContextError("intentional later failure")
        value = original(selection, offset); staged_first.append(value); return value
    monkeypatch.setattr(module, "_stage_pvc_context", fail_later)
    with pytest.raises(PvcContextError, match="intentional"):
        module._stage_pvc_composition(PvcContextComposition((source, semantic)))
    assert staged_first and all(a._closed for a in (
        *staged_first[0].image_authorities, *staged_first[0].text_authorities))
    assert not staged_first[0].root.exists()


def test_composed_cleanup_is_idempotent(tmp_path):
    composition = PvcContextComposition(_members(tmp_path)[:3])
    staged = _stage_pvc_composition(composition)
    roots = staged.roots
    fds = [a.fd for a in (*staged.image_authorities, *staged.text_authorities)]
    staged.cleanup(); staged.cleanup()
    assert all(not root.exists() for root in roots)
    assert all(not os.path.exists(f"/proc/self/fd/{fd}") for fd in fds)


def test_distinct_snapshots_keep_duplicate_local_ids_unambiguous(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    one = PvcContextSelection(
        validate_prepare_result(_result(tmp_path / "one")),
        ("APO-VC-000001",))
    two = PvcContextSelection(
        validate_prepare_result(_result(tmp_path / "two")),
        ("APO-VC-000001",))
    document = json.loads(two.result.stdout_path.read_text())
    document["sources"] = [dict(document["sources"][0], displayPath="other.txt")]
    document["snapshotId"] = _snapshot_identity_id(document)
    encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
    two.result.stdout_path.write_bytes(encoded)
    (two.result.bundle_path / "snapshot.json").write_bytes(encoded)
    two = PvcContextSelection(validate_prepare_result(two.result),
                              ("APO-VC-000001",))
    assert one.result.validated_snapshot.document["snapshotId"] != \
        two.result.validated_snapshot.document["snapshotId"]
    # Same local identifier is explicitly scoped by the retained snapshot.
    staged = _stage_pvc_composition(PvcContextComposition((one, two)))
    try:
        assert len(staged.image_authorities) == 2
        assert {a.snapshot_id for a in staged.image_authorities} == {
            one.result.validated_snapshot.document["snapshotId"],
            two.result.validated_snapshot.document["snapshotId"]}
    finally:
        staged.cleanup()


def test_flattened_ordinals_are_global_but_single_selection_starts_at_zero(
        tmp_path):
    review, source, semantic, _ = _members(tmp_path)
    staged = _stage_pvc_composition(PvcContextComposition((review, source,
                                                             semantic)))
    try:
        authorities = sorted((*staged.image_authorities,
                              *staged.text_authorities), key=lambda x: x.ordinal)
        assert [a.ordinal for a in authorities] == [0, 1, 2, 3]
        standalone = _stage_pvc_context(source)
        try:
            assert standalone.image_authorities[0].ordinal == 0
        finally:
            standalone.cleanup()
    finally:
        staged.cleanup()
