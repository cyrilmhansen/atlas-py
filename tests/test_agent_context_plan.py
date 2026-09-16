"""Qualification tests for the operator context-plan adapter (S1b.3b)."""
import hashlib
import json
import stat
import sys

import pytest

from tools.atlas_agent import cli
from tools.atlas_agent.context_plan import (
    build_context_composition, cleanup_context_composition, parse_context_plan,
)
from tools.atlas_agent.pvc_context import PvcContextComposition
from tools.atlas_agent.pvc_context import _stage_pvc_composition
from tools.atlas_agent.review import ReviewPackage
from test_agent_pvc_validation import _result
from test_semantic_query import FAKE
from test_python_semantic_query import FAKE as PYTHON_FAKE
from test_agent_workflow_w221 import accepted, make_repo


def write_plan(path, members, **extra):
    value = {"schema": "atlas-agent-context-plan/1", "members": members}
    value.update(extra)
    path.write_text(json.dumps(value))
    return path


def semantic_member(executable, kind="hover", path="a.rs", line=0, character=0):
    return {"kind": "SEMANTIC", "query": {"kind": kind, "path": path,
            "line": line, "character": character}, "executable": str(executable),
            "version": "fake"}


def python_member(executable, path="a.py"):
    return {"kind": "SEMANTIC", "backend": "python",
            "query": {"kind": "hover", "path": path, "line": 0,
                      "character": 8}, "executable": str(executable),
            "version": "fake 1"}


def _server(path, source):
    path.write_text("#!" + sys.executable + "\n" + source)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _bound_target(workflow):
    return workflow.preview_dispatch_target()


def test_context_plan_valid_schema_and_ordered_member_shapes(tmp_path):
    exe = tmp_path / "ra"
    members = [{"kind": "REVIEW"},
               {"kind": "SOURCE", "result_path": "retained",
                "tablet_ids": ["t"], "purpose": "source"},
               semantic_member(exe)]
    path = write_plan(tmp_path / "plan.json", members)
    assert parse_context_plan(path)["members"] == members


@pytest.mark.parametrize("raw, code", [
    (b"\xff", "CONTEXT_PLAN_INVALID"),
    (b"{", "CONTEXT_PLAN_INVALID"),
    (b'{"schema":"atlas-agent-context-plan/1","schema":"atlas-agent-context-plan/1","members":[{"kind":"REVIEW"}]}',
     "CONTEXT_PLAN_INVALID"),
    (b'{"schema":"atlas-agent-context-plan/1","members":[{"kind":"REVIEW"}],"x":NaN}',
     "CONTEXT_PLAN_INVALID"),
    (b'{"schema":"other","members":[{"kind":"REVIEW"}]}',
     "CONTEXT_PLAN_SCHEMA_INVALID"),
    (b'{"schema":"atlas-agent-context-plan/1"}', "CONTEXT_PLAN_SCHEMA_INVALID"),
    (b'{"schema":"atlas-agent-context-plan/1","members":[]}',
     "CONTEXT_PLAN_SCHEMA_INVALID"),
    (b'{"schema":"atlas-agent-context-plan/1","members":[{"kind":"NOPE"}]}',
     "CONTEXT_PLAN_MEMBER_KIND_INVALID"),
    (b'{"schema":"atlas-agent-context-plan/1","members":[{"kind":"REVIEW","x":1}]}',
     "CONTEXT_PLAN_UNKNOWN_FIELD"),
    (b'{"schema":"atlas-agent-context-plan/1","members":[{"kind":"SEMANTIC","query":{},"executable":"/x"}]}',
     "CONTEXT_PLAN_SEMANTIC_INVALID"),
    (b'{"schema":"atlas-agent-context-plan/1","members":[{"kind":"SEMANTIC","query":{"kind":"hover","path":"a.rs","line":0,"character":[]},"executable":"/x"}]}',
     "CONTEXT_PLAN_SEMANTIC_INVALID"),
])
def test_context_plan_rejects_malformed_documents(tmp_path, raw, code):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match=code):
        parse_context_plan(path)


def test_context_plan_rejects_authority_and_query_boundaries(tmp_path):
    exe = tmp_path / "ra"
    cases = [
        semantic_member(exe, "completion"),
        semantic_member(exe, path="/absolute.rs"),
        semantic_member(exe, path="../a.rs"),
        semantic_member(exe, line=-1),
        semantic_member(exe, character=-1),
        semantic_member(tmp_path / "missing-ra"),
    ]
    # Parsing enforces the query-kind and position contract.  Path safety and
    # executable availability belong to the reused semantic boundary.
    for member in cases[:1]:
        path = write_plan(tmp_path / "p.json", [member])
        with pytest.raises(ValueError):
            parse_context_plan(path)
    assert parse_context_plan(write_plan(tmp_path / "valid.json", [cases[1]]))
    for member in cases[3:5]:
        with pytest.raises(ValueError):
            parse_context_plan(write_plan(tmp_path / "position.json", [member]))


def test_semantic_path_and_authority_fail_at_reused_boundary(tmp_path):
    repo, workflow = make_repo(tmp_path)
    authority = tmp_path / "fake-ra"
    authority.write_text(FAKE)
    authority.chmod(authority.stat().st_mode | stat.S_IXUSR)
    accepted(workflow)
    for member in (
            semantic_member(authority, path="/a"),
            semantic_member(authority, path="../a"),
            semantic_member(tmp_path / "unavailable-ra")):
        plan = write_plan(tmp_path / "plan.json", [member])
        with pytest.raises(ValueError, match="CONTEXT_PLAN_SEMANTIC_INVALID"):
            build_context_composition(workflow, parse_context_plan(plan))


def test_semantic_adapter_uses_authority_and_query_and_builds_pvc(tmp_path):
    repo, workflow = make_repo(tmp_path)
    authority = tmp_path / "fake-ra"
    authority.write_text(FAKE)
    authority.chmod(authority.stat().st_mode | stat.S_IXUSR)
    accepted(workflow)
    plan = write_plan(tmp_path / "plan.json",
                      [semantic_member(authority, "references", path="a")])
    composition = build_context_composition(workflow, parse_context_plan(plan))
    try:
        payload = (composition.selections[0].result.bundle_path /
                   composition.selections[0].result.validated_snapshot.document[
                       "artifacts"][0]["relativePath"]).read_bytes()
        document = json.loads(payload)
        assert document["query"]["kind"] == "references"
        assert document["query"]["path"] == "a"
        assert document["authority"]["executable"] == str(authority)
    finally:
        from tools.atlas_agent.context_plan import cleanup_context_composition
        cleanup_context_composition(composition)


def test_review_source_and_plan_order_cross_adapter_boundary(tmp_path):
    repo, workflow = make_repo(tmp_path)
    authority = tmp_path / "fake-ra"
    authority.write_text(FAKE)
    authority.chmod(authority.stat().st_mode | stat.S_IXUSR)
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    retained = _result(repo / "corpus_miner")
    plan = write_plan(tmp_path / "plan.json", [
        {"kind": "REVIEW"},
        {"kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
         "tablet_ids": ["APO-VC-000001"], "purpose": "explicit source"},
        semantic_member(authority, path="a"),
    ])
    composition = build_context_composition(workflow, parse_context_plan(plan))
    assert isinstance(composition, PvcContextComposition)
    assert [x.purpose for x in composition.selections] == [
        "patch review package", "explicit source", "rust semantic context"]
    assert composition.selections[1].tablet_ids == ("APO-VC-000001",)
    staged = _stage_pvc_composition(composition)
    try:
        review_bytes = [
            (composition.selections[0].result.bundle_path /
             a["relativePath"]).read_bytes()
            for a in composition.selections[0].result.validated_snapshot.document[
                "artifacts"]
        ]
        assert b"W2.2.1\n" in review_bytes
        assert any(payload.startswith(b"diff --git ") for payload in review_bytes)
        assert [x.ordinal for x in staged.image_authorities] == [2]
        assert [x.ordinal for x in staged.text_authorities] == [0, 1, 3]
    finally:
        staged.cleanup()


def test_source_is_borrowed_and_owned_members_are_cleaned(tmp_path):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    retained = _result(repo / "corpus_miner")
    retained_bytes = (retained.scratch_path / "stdout").read_bytes()
    plan = write_plan(tmp_path / "plan.json", [
        {"kind": "REVIEW"},
        {"kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
         "tablet_ids": ["APO-VC-000001"], "purpose": "retained"},
    ])
    composition = build_context_composition(workflow, parse_context_plan(plan))
    owned = composition.owned_resources[0]
    cleanup_context_composition(composition)
    assert retained.scratch_path.is_dir()
    assert (retained.scratch_path / "stdout").read_bytes() == retained_bytes
    assert not owned.exists()


def test_source_survives_later_member_failure_and_prior_owned_data_does_not(
        tmp_path, monkeypatch):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    retained = _result(repo / "corpus_miner")
    retained_bytes = (retained.scratch_path / "stdout").read_bytes()
    created_review_roots = []
    real_pvc_context = ReviewPackage.pvc_context

    def record_real_review_resource(package, purpose="patch review package"):
        selection = real_pvc_context(package, purpose)
        created_review_roots.append(selection.result.scratch_path)
        assert created_review_roots[-1].exists()
        return selection

    monkeypatch.setattr(ReviewPackage, "pvc_context",
                        record_real_review_resource)
    plan = write_plan(tmp_path / "plan.json", [
        {"kind": "REVIEW"},
        {"kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
         "tablet_ids": ["APO-VC-000001"], "purpose": "retained"},
        {"kind": "SOURCE", "result_path": str(tmp_path / "missing"),
         "tablet_ids": ["APO-VC-000001"], "purpose": "fails"},
    ])
    with pytest.raises(ValueError):
        build_context_composition(workflow, parse_context_plan(plan))
    assert retained.scratch_path.is_dir()
    assert (retained.scratch_path / "stdout").read_bytes() == retained_bytes
    assert len(created_review_roots) == 1
    assert not created_review_roots[0].exists()


def test_review_uses_authoritative_accepted_spool_digest(tmp_path):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    accepted_path = next((workflow.base / "accepted").glob("g*.txt"))
    original = accepted_path.read_bytes()
    # Keep the prompt parseable while invalidating the durable spool digest.
    accepted_path.write_bytes(original.replace(b"W2.2.1", b"changed!"))
    with pytest.raises(Exception, match="SPOOL_CORRUPT"):
        build_context_composition(
            workflow, parse_context_plan(write_plan(
                tmp_path / "plan.json", [{"kind": "REVIEW"}])))


def test_source_rejects_unvalidated_and_unknown_tablets(tmp_path):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    retained = _result(repo)
    for tablet in ("unknown",):
        plan = write_plan(tmp_path / "plan.json", [{
            "kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
            "tablet_ids": [tablet], "purpose": "x"}])
        with pytest.raises((ValueError, RuntimeError)):
            build_context_composition(workflow, parse_context_plan(plan))
    bad = repo / "not-a-result"
    bad.mkdir()
    plan = write_plan(tmp_path / "bad.json", [{
        "kind": "SOURCE", "result_path": "not-a-result",
        "tablet_ids": ["APO-VC-000001"], "purpose": "x"}])
    with pytest.raises(Exception, match="PVC_BUNDLE_STDOUT_MISSING"):
        build_context_composition(workflow, parse_context_plan(plan))


def test_public_cli_loads_plan_and_passes_composition(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    plan = write_plan(tmp_path / "plan.json", [{"kind": "REVIEW"}])
    calls = []
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    monkeypatch.setattr(workflow, "dispatch",
                        lambda executor, observer=None, pvc_context_provider=None:
                        calls.append(pvc_context_provider(_bound_target(workflow))))
    assert cli.main(["dispatch", "--context-plan", str(plan)]) == 0
    assert isinstance(calls[0], PvcContextComposition)


def test_cli_dispatch_finally_cleanup_preserves_retained_source(tmp_path,
                                                                 monkeypatch):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    retained = _result(repo / "corpus_miner")
    before = (retained.scratch_path / "stdout").read_bytes()
    plan = write_plan(tmp_path / "plan.json", [{
        "kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
        "tablet_ids": ["APO-VC-000001"], "purpose": "retained"}])
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    monkeypatch.setattr(workflow, "dispatch",
                        lambda *args, **kwargs: None)
    assert cli.main(["dispatch", "--context-plan", str(plan)]) == 0
    assert retained.scratch_path.is_dir()
    assert (retained.scratch_path / "stdout").read_bytes() == before


def test_malformed_cli_plan_precedes_run_started_and_no_plan_is_unchanged(
        tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    invoked = []
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    monkeypatch.setattr(workflow, "dispatch", lambda *a, **k: invoked.append(k))
    assert cli.main(["dispatch", "--context-plan", str(bad)]) == 1
    assert not invoked
    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"
    assert not any(x["event"] == "RUN_STARTED" for x in workflow.journal.read())
    assert cli.main(["dispatch"]) == 0
    assert "pvc_context" not in invoked[-1]


def test_context_plan_cannot_smuggle_execution_authority(tmp_path):
    for key in ("model", "reasoning", "sandbox", "network", "session_mode",
                "compute_profile", "fast"):
        path = write_plan(tmp_path / (key + ".json"), [{"kind": "REVIEW"}],
                          **{key: "forbidden"})
        with pytest.raises(ValueError):
            parse_context_plan(path)


def test_v2_rust_bridge_queries_fixture_and_records_owned_resource(tmp_path):
    repo, workflow = make_repo(tmp_path)
    authority = _server(tmp_path / "fake-ra", FAKE)
    accepted(workflow)
    (repo / "a.rs").write_text("fn main() {}\n")
    plan = write_plan(tmp_path / "v2.json", [{
        **semantic_member(authority, path="a.rs"), "backend": "rust",
    }], schema="atlas-agent-context-plan/2")
    composition = build_context_composition(workflow, parse_context_plan(plan))
    try:
        selection = composition.selections[0]
        artifact = selection.result.validated_snapshot.document["artifacts"][0]
        semantic = (selection.result.bundle_path /
                    artifact["relativePath"]).read_bytes()
        assert json.loads(semantic)["schema"] == "atlas-rust-semantic/1"
        assert artifact["mediaType"] == (
            "application/vnd.atlas.rust-semantic+json")
        assert selection.purpose == "rust semantic context"
        assert selection.result.scratch_path in composition.owned_resources
    finally:
        cleanup_context_composition(composition)


def test_v2_model_execution_transports_review_and_python_once(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionResult, PreparedExecution, utc_now

    repo, workflow = make_repo(tmp_path)
    server = _server(tmp_path / "pyright", PYTHON_FAKE.replace("a.py", "corpus_miner/a"))
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    (repo / "corpus_miner" / "a").write_bytes(
        "é😀 target = 2\r\nprint(target)\r\n".encode())
    plan = write_plan(tmp_path / "v2.json", [
        {"kind": "REVIEW"}, python_member(server, path="corpus_miner/a"),
    ], schema="atlas-agent-context-plan/2")
    composition = build_context_composition(workflow, parse_context_plan(plan))
    review = composition.selections[0]
    review_payloads = [(review.result.bundle_path / item["relativePath"]).read_bytes()
                       for item in review.result.validated_snapshot.document[
                           "artifacts"]]
    artifact = composition.selections[1].result.validated_snapshot.document[
        "artifacts"][0]
    python_bytes = (composition.selections[1].result.bundle_path /
                    artifact["relativePath"]).read_bytes()

    class Capture(CodexExecutor):
        supports_authoritative_pvc_context = True

        def __init__(self):
            super().__init__(executable="/bin/true")
            self.inputs = []
            self.commands = []

        def prepare_execution(self, spec):
            return PreparedExecution(spec, "capture", ("capture",), "capture/1",
                                     self._envelope(), spec.policy_snapshot)

        def run_execution(self, prepared):
            self.inputs.append(prepared.spec.prompt_bytes)
            self.commands.append(prepared.command)
            prepared.spec.report_dir.mkdir(parents=True, exist_ok=True)
            (prepared.spec.report_dir / "stdout.log").write_bytes(b"")
            (prepared.spec.report_dir / "stderr.log").write_bytes(b"")
            now = utc_now()
            return ExecutionResult(
                str(prepared.spec.execution_id), "capture",
                list(prepared.command), "capture/1", now, now, 0,
                "reports/x/stdout.log", "reports/x/stderr.log", "capture-session",
                "success", "reports/x/result.json",
                prepared.permission_envelope,
                execution_input_sha256=hashlib.sha256(
                    prepared.spec.prompt_bytes).hexdigest())

    capture = Capture()
    try:
        workflow.execute(1, capture, pvc_context=composition)
        assert len(capture.inputs) == 1
        actual = capture.inputs[0]
        assert all(payload in actual for payload in review_payloads)
        assert python_bytes in actual
        assert b"atlas-python-semantic/1" in actual
        assert "--image" not in capture.commands[0]
        assert workflow._state()["generations"]["1"]["execution"][
            "effective_prompt_sha256"] == hashlib.sha256(actual).hexdigest()
    finally:
        cleanup_context_composition(composition)


def test_v2_mixed_plan_preserves_order_and_global_ordinals(tmp_path):
    repo, workflow = make_repo(tmp_path)
    rust = _server(tmp_path / "rust", FAKE)
    python = _server(tmp_path / "python",
                     PYTHON_FAKE.replace("a.py", "corpus_miner/a"))
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    (repo / "corpus_miner" / "a").write_bytes(
        "é😀 target = 2\r\nprint(target)\r\n".encode())
    retained = _result(repo / "corpus_miner")
    plan = write_plan(tmp_path / "mixed.json", [
        {"kind": "REVIEW"}, python_member(python, path="corpus_miner/a"),
        {"kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
         "tablet_ids": ["APO-VC-000001"], "purpose": "retained"},
        {**semantic_member(rust, path="corpus_miner/a"), "backend": "rust"},
    ], schema="atlas-agent-context-plan/2")
    composition = build_context_composition(workflow, parse_context_plan(plan))
    staged = _stage_pvc_composition(composition)
    try:
        assert [x.purpose for x in composition.selections] == [
            "patch review package", "python semantic context", "retained",
            "rust semantic context"]
        all_authorities = sorted((*staged.text_authorities,
                                  *staged.image_authorities),
                                 key=lambda x: x.ordinal)
        assert [x.ordinal for x in all_authorities] == list(range(5))
        assert [x.ordinal for x in staged.text_authorities] == [0, 1, 2, 4]
        assert [x.ordinal for x in staged.image_authorities] == [3]
    finally:
        staged.cleanup()
        cleanup_context_composition(composition)


def test_context_composition_cleanup_removes_generated_semantics_only(tmp_path):
    repo, workflow = make_repo(tmp_path)
    rust = _server(tmp_path / "rust", FAKE)
    python = _server(tmp_path / "python",
                     PYTHON_FAKE.replace("a.py", "corpus_miner/a"))
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    (repo / "corpus_miner" / "a").write_bytes(
        "é😀 target = 2\r\nprint(target)\r\n".encode())
    retained = _result(repo / "corpus_miner")
    retained_stdout = (retained.scratch_path / "stdout").read_bytes()
    retained_artifact = retained.bundle_path / "artifacts" / "one.png"
    retained_artifact_bytes = retained_artifact.read_bytes()
    composition = build_context_composition(workflow, parse_context_plan(
        write_plan(tmp_path / "lifecycle.json", [
            {"kind": "REVIEW"}, python_member(python, path="corpus_miner/a"),
            {"kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
             "tablet_ids": ["APO-VC-000001"], "purpose": "retained"},
            {**semantic_member(rust, path="corpus_miner/a"), "backend": "rust"},
        ], schema="atlas-agent-context-plan/2")))
    review_root = composition.selections[0].result.scratch_path
    python_root = composition.selections[1].result.scratch_path
    retained_root = composition.selections[2].result.scratch_path
    rust_root = composition.selections[3].result.scratch_path
    owned_roots = (review_root, python_root, rust_root)
    assert all(root.is_dir() for root in owned_roots)
    assert retained_root.is_dir()
    assert retained_artifact.is_file()
    cleanup_context_composition(composition)
    assert all(not root.exists() for root in owned_roots)
    assert retained_root.is_dir()
    assert (retained_root / "stdout").read_bytes() == retained_stdout
    assert retained_artifact.is_file()
    assert retained_artifact.read_bytes() == retained_artifact_bytes


def test_context_composition_failure_cleans_python_but_borrows_source(
        tmp_path, monkeypatch):
    from tools.atlas_agent.python_semantic import PythonSemanticTablet

    repo, workflow = make_repo(tmp_path)
    python = _server(tmp_path / "python", PYTHON_FAKE.replace("a.py", "corpus_miner/a"))
    accepted(workflow)
    (repo / "corpus_miner").mkdir()
    (repo / "corpus_miner" / "a").write_bytes(
        "é😀 target = 2\r\nprint(target)\r\n".encode())
    retained = _result(repo / "corpus_miner")
    retained_stdout = (retained.scratch_path / "stdout").read_bytes()
    retained_artifact = retained.bundle_path / "artifacts" / "one.png"
    retained_artifact_bytes = retained_artifact.read_bytes()
    captured_python_roots = []
    captured_python_existence = []
    real_python_pvc_context = PythonSemanticTablet.pvc_context

    def record_python_root(tablet, purpose="python semantic context"):
        selection = real_python_pvc_context(tablet, purpose)
        root = selection.result.scratch_path
        captured_python_roots.append(root)
        captured_python_existence.append(root.is_dir())
        return selection

    monkeypatch.setattr(PythonSemanticTablet, "pvc_context",
                        record_python_root)
    plan = write_plan(tmp_path / "failure.json", [
        python_member(python, path="corpus_miner/a"),
        {"kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
         "tablet_ids": ["APO-VC-000001"], "purpose": "retained"},
        python_member(tmp_path / "missing", path="a"),
    ], schema="atlas-agent-context-plan/2")
    with pytest.raises(ValueError, match="CONTEXT_PLAN_SEMANTIC_INVALID"):
        build_context_composition(workflow, parse_context_plan(plan))
    assert len(captured_python_roots) == 1
    assert captured_python_existence == [True]
    assert not captured_python_roots[0].exists()
    assert retained.scratch_path.is_dir()
    assert (retained.scratch_path / "stdout").read_bytes() == retained_stdout
    assert retained_artifact.is_file()
    assert retained_artifact.read_bytes() == retained_artifact_bytes


def test_public_cli_v1_forwards_real_rust_selection(tmp_path, monkeypatch):
    repo, workflow = make_repo(tmp_path)
    authority = _server(tmp_path / "rust", FAKE)
    accepted(workflow)
    (repo / "a.rs").write_text("fn main() {}\n")
    path = write_plan(tmp_path / "v1.json", [semantic_member(authority,
                                                               path="a.rs")])
    forwarded = []
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    monkeypatch.setattr(workflow, "dispatch",
                        lambda executor, observer=None, pvc_context_provider=None:
                        forwarded.append((
                            (pvc_context := pvc_context_provider(_bound_target(workflow))),
                            json.loads((pvc_context.selections[0].result.bundle_path /
                                        pvc_context.selections[0].result.validated_snapshot.document[
                                            "artifacts"][0]["relativePath"]).read_bytes()))))
    assert cli.main(["dispatch", "--context-plan", str(path)]) == 0
    composition, document = forwarded[0]
    selection = composition.selections[0]
    assert selection.purpose == "rust semantic context"
    assert document["schema"] == "atlas-rust-semantic/1"


def test_public_cli_v2_forwards_real_python_selection(tmp_path, monkeypatch):
    repo, workflow = make_repo(tmp_path)
    authority = _server(tmp_path / "python", PYTHON_FAKE)
    accepted(workflow)
    (repo / "a.py").write_bytes("é😀 target = 1\r\nprint(target)\r\n".encode())
    path = write_plan(tmp_path / "v2.json", [python_member(authority)],
                      schema="atlas-agent-context-plan/2")
    forwarded = []
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    plan_bytes = path.read_bytes()
    assert cli.main(["context-plan-check", "--context-plan", str(path)]) == 0
    assert path.read_bytes() == plan_bytes
    monkeypatch.setattr(workflow, "dispatch",
                        lambda executor, observer=None, pvc_context_provider=None:
                        forwarded.append((
                            (pvc_context := pvc_context_provider(_bound_target(workflow))),
                            json.loads((pvc_context.selections[0].result.bundle_path /
                                        pvc_context.selections[0].result.validated_snapshot.document[
                                            "artifacts"][0]["relativePath"]).read_bytes()))))
    assert cli.main(["dispatch", "--context-plan", str(path)]) == 0
    composition, document = forwarded[0]
    selection = composition.selections[0]
    assert selection.purpose == "python semantic context"
    assert document["schema"] == "atlas-python-semantic/1"


def test_cli_example_is_complete_json_without_repository(tmp_path, monkeypatch, capsys):
    def forbidden():
        pytest.fail("example must not open a workflow")
    monkeypatch.setattr(cli, "Workflow", forbidden)
    assert cli.main(["context-plan-example"]) == 0
    raw = capsys.readouterr().out
    path = tmp_path / "example.json"
    path.write_text(raw)
    plan = parse_context_plan(path)
    assert plan["schema"] == "atlas-agent-context-plan/2"
    assert [m["kind"] for m in plan["members"]] == ["REVIEW", "SOURCE", "SEMANTIC"]
    assert plan["members"][2]["backend"] == "python"


def test_cli_static_check_preserves_exact_requests_and_state(tmp_path, monkeypatch, capsys):
    from tools.atlas_agent import context_plan as adapter

    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    accepted(workflow, generation=2)
    authority = _server(tmp_path / "python", "raise RuntimeError('must not run')")
    retained = _result(repo)
    members = [python_member(authority), {"kind": "REVIEW"},
               {"kind": "SOURCE", "result_path": str(retained.scratch_path.relative_to(repo)),
                "tablet_ids": ["APO-VC-000001"], "purpose": "only this image"},
               {**semantic_member(authority), "backend": "rust"}]
    path = write_plan(tmp_path / "check.json", members,
                      schema="atlas-agent-context-plan/2")
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    plan_bytes = path.read_bytes()
    def forbidden(*args, **kwargs):
        pytest.fail("static check must not acquire context or construct temporary PVCs")
    monkeypatch.setattr(adapter, "query_python_semantics", forbidden)
    monkeypatch.setattr(adapter, "query_rust_semantics", forbidden)
    monkeypatch.setattr(adapter, "build_review_package", forbidden)
    monkeypatch.setattr(adapter, "build_python_semantic_tablet", forbidden)
    monkeypatch.setattr(adapter, "build_semantic_tablet", forbidden)
    monkeypatch.setattr(cli, "AtlasBubblewrapExecutor", forbidden)
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    assert cli.main(["context-plan-check", "--context-plan", str(path)]) == 0
    output = capsys.readouterr().out
    assert "target: g1 · implementation" in output
    assert output.index("1. SEMANTIC") < output.index("2. REVIEW") < output.index("3. SOURCE") < output.index("4. SEMANTIC")
    assert 'python hover "a.py" line=0 character=8' in output
    assert 'rust hover "a.rs" line=0 character=0' in output
    assert str(authority) in output and '"fake 1" (operator assertion)' in output
    assert 'tablets: ["APO-VC-000001"]; purpose: "only this image"' in output
    assert "No semantic acquisition" in output
    assert "Not checked: semantic file/coordinate bounds" in output
    assert "not reserved" in output
    assert before == {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    assert path.read_bytes() == plan_bytes


@pytest.mark.parametrize("failure", ["path", "executable", "source", "spool", "state"])
def test_cli_static_check_fails_closed(tmp_path, monkeypatch, capsys, failure):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    authority = _server(tmp_path / "python", "raise RuntimeError('must not run')")
    member = python_member(authority)
    if failure == "path":
        member["query"]["path"] = "../outside.py"
    elif failure == "executable":
        member["executable"] = str(tmp_path / "missing")
    elif failure == "source":
        member = {"kind": "SOURCE", "result_path": str(tmp_path / "missing"),
                  "tablet_ids": ["missing"], "purpose": "explicit"}
    elif failure == "spool":
        accepted_path = next((workflow.base / "accepted").glob("*.txt"))
        accepted_path.write_bytes(accepted_path.read_bytes() + b"tampered\n")
    else:
        state = workflow._state()
        state["generations"]["1"]["expected_head"] = "0" * 40
        workflow._save(state)
    path = write_plan(tmp_path / "bad.json", [member], schema="atlas-agent-context-plan/2")
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    assert cli.main(["context-plan-check", "--context-plan", str(path)]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert "error:" in output.err
    if failure in {"path", "executable", "source"}:
        assert "CONTEXT_PLAN_MEMBER_1_" in output.err


def test_cli_static_check_no_target_and_required_argument(tmp_path, monkeypatch, capsys):
    _, workflow = make_repo(tmp_path)
    path = write_plan(tmp_path / "review.json", [{"kind": "REVIEW"}])
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    assert cli.main(["context-plan-check", "--context-plan", str(path)]) == 0
    assert "target: none — NO_DISPATCHABLE_GENERATION" in capsys.readouterr().out
    assert cli.main(["context-plan-check"]) == 1
    assert "--context-plan PLAN.json is required" in capsys.readouterr().err
    assert cli.main(["execute", "--context-plan", str(path)]) == 1
    assert "only valid for dispatch or context-plan-check" in capsys.readouterr().err


@pytest.mark.parametrize("field,value", [("kind", []), ("kind", {}), ("path", [])])
def test_malformed_query_types_are_cli_rejections(tmp_path, monkeypatch, capsys, field, value):
    _, workflow = make_repo(tmp_path)
    member = python_member(tmp_path / "pyright")
    member["query"][field] = value
    path = write_plan(tmp_path / "bad.json", [member], schema="atlas-agent-context-plan/2")
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    assert cli.main(["context-plan-check", "--context-plan", str(path)]) == 1
    assert "CONTEXT_PLAN_SEMANTIC_INVALID" in capsys.readouterr().err


def test_source_result_path_stays_within_repository_after_resolution(tmp_path):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    (repo / "corpus_miner" / "inside").mkdir(parents=True)
    inside = _result(repo / "corpus_miner" / "inside")
    (repo / "inside-link").symlink_to(inside.scratch_path, target_is_directory=True)

    valid = write_plan(tmp_path / "inside.json", [{
        "kind": "SOURCE", "result_path": "inside-link",
        "tablet_ids": ["APO-VC-000001"], "purpose": "inside symlink",
    }])
    composition = build_context_composition(workflow, parse_context_plan(valid))
    assert composition.selections[0].result.scratch_path == inside.scratch_path

    (tmp_path / "outside").mkdir()
    outside = _result(tmp_path / "outside")
    (repo / "outside-link").symlink_to(outside.scratch_path, target_is_directory=True)
    for index, result_path in enumerate((
            str(outside.scratch_path), "../outside", "outside-link")):
        plan = write_plan(tmp_path / f"escape-{index}.json", [{
            "kind": "SOURCE", "result_path": result_path,
            "tablet_ids": ["APO-VC-000001"], "purpose": "escape",
        }])
        with pytest.raises(ValueError, match="CONTEXT_PLAN_SOURCE_INVALID"):
            build_context_composition(workflow, parse_context_plan(plan))


def test_dispatch_binds_provider_to_selected_target(tmp_path):
    from tools.atlas_agent.executor import FakeExecutor

    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    seen = []

    def acquire(target):
        seen.append((target.generation, target.prompt_sha256,
                     target.expected_head, target.prompt.body))
        return None

    result = workflow.dispatch(FakeExecutor(observed_thread_id="bound-target"),
                               pvc_context_provider=acquire)
    assert result["generation"] == 1
    assert seen[0][0] == 1
    assert seen[0][1] == workflow._state()["generations"]["1"]["prompt_sha256"]
    assert seen[0][3] == "W2.2.1\n"


def test_dispatch_rejects_workflow_change_during_context_acquisition(tmp_path):
    from tools.atlas_agent.executor import FakeExecutor
    from tools.atlas_agent.workflow import WorkflowError

    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    executor = FakeExecutor(observed_thread_id="must-not-run")

    def acquire(target):
        assert target.generation == 1
        accepted(workflow, generation=2)
        return None

    with pytest.raises(WorkflowError, match="DISPATCH_TARGET_AUTHORITY_CHANGED"):
        workflow.dispatch(executor, pvc_context_provider=acquire)
    assert executor.launched == 0
    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"


def test_dispatch_rejects_repository_change_during_context_acquisition(tmp_path):
    from tools.atlas_agent.executor import FakeExecutor
    from tools.atlas_agent.workflow import WorkflowError

    repo, workflow = make_repo(tmp_path)
    accepted(workflow)
    executor = FakeExecutor(observed_thread_id="must-not-run")

    def acquire(target):
        assert target.generation == 1
        (repo / "a").write_text("authority changed")
        return None

    with pytest.raises(WorkflowError, match="REPOSITORY_WITNESS_MISMATCH"):
        workflow.dispatch(executor, pvc_context_provider=acquire)
    assert executor.launched == 0
    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"
