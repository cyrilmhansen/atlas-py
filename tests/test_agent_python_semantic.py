import json
import stat
import sys

import pytest

from tools.atlas_agent.context_plan import (build_context_composition,
                                            cleanup_context_composition,
                                            parse_context_plan)
from tools.atlas_agent.python_semantic import (
    PythonSemanticResultError, build_python_semantic_tablet,
    validate_python_semantic_result,
)
from tools.atlas_agent.pvc_context import _stage_pvc_context
from test_agent_workflow_w221 import accepted, make_repo
from test_python_semantic_query import FAKE


def payload(**changes):
    value = {
        "schema": "atlas-python-semantic/1",
        "query": {"kind": "hover", "path": "a.py", "line": 0, "character": 1},
        "authority": {"executable": "/usr/bin/pyright-langserver",
                      "version": "pyright 1.1.412"},
        "repositoryWitness": "a" * 64,
        "positionEncoding": "utf-8",
        "result": {"kind": "hover", "value": {"contents": None, "range": None}},
    }
    value.update(changes)
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_python_result_is_deterministic_and_typed():
    one = build_python_semantic_tablet(payload())
    two = build_python_semantic_tablet(payload())
    assert (one.tablet_id, one.artifact_id, one.provenance) == (
        two.tablet_id, two.artifact_id, two.provenance)
    assert "atlas-python-semantic/1" in one.provenance
    selection = one.pvc_context()
    assert selection.result.validated_snapshot.document["artifacts"][0]["mediaType"] == (
        "application/vnd.atlas.python-semantic+json")


def test_duplicate_key_is_the_only_invalidity_and_baseline_succeeds():
    baseline = payload()
    duplicate = baseline.replace(
        b',"schema":"atlas-python-semantic/1"}',
        b',"schema":"atlas-python-semantic/1","schema":"atlas-python-semantic/1"}',
    )
    with pytest.raises(PythonSemanticResultError):
        validate_python_semantic_result(duplicate)
    assert validate_python_semantic_result(baseline)["schema"] == (
        "atlas-python-semantic/1")


@pytest.mark.parametrize("raw", [
    b"{", b"\xff", payload(schema="atlas-rust-semantic/1"),
    payload(positionEncoding="utf-16"), payload(repositoryWitness="A" * 64),
    payload()[:-1], payload() + b"\n",
    payload(repositoryWitness="a" * 63),
    payload(result={"kind": "hover", "value": float("nan")}),
    payload(result={"kind": "hover", "value": float("inf")}),
    payload(result={"kind": "hover", "value": float("-inf")}),
    payload().replace(b'{"authority"', b'{ "authority"'),
])
def test_python_result_validator_rejects_one_mutated_property(raw):
    with pytest.raises((PythonSemanticResultError, ValueError)):
        validate_python_semantic_result(raw)


def test_v2_requires_explicit_backend_and_version(tmp_path):
    def write(member):
        path = tmp_path / "plan.json"
        path.write_text(json.dumps({"schema": "atlas-agent-context-plan/2",
                                    "members": [member]}))
        return parse_context_plan(path)
    base = {"kind": "SEMANTIC", "query": {"kind": "hover", "path": "a.py",
            "line": 0, "character": 0}, "executable": "/x",
            "version": "v"}
    with pytest.raises(ValueError):
        write(base)
    with pytest.raises(ValueError):
        write({**base, "backend": "other"})
    assert write({**base, "backend": "python"})["schema"] == "atlas-agent-context-plan/2"


def test_v1_rejects_backend_field(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"schema": "atlas-agent-context-plan/1", "members": [{
        "kind": "SEMANTIC", "backend": "rust",
        "query": {"kind": "hover", "path": "a.rs", "line": 0, "character": 0},
        "executable": "/x", "version": "v"}]}))
    with pytest.raises(ValueError, match="CONTEXT_PLAN_UNKNOWN_FIELD"):
        parse_context_plan(path)


@pytest.mark.parametrize("schema", [None, True, 1, [], {}, False,
                                    ["atlas-agent-context-plan/1"]])
def test_context_plan_non_string_schema_has_stable_error(tmp_path, schema):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"schema": schema,
                                "members": [{"kind": "REVIEW"}]}))
    with pytest.raises(ValueError, match="CONTEXT_PLAN_SCHEMA_INVALID"):
        parse_context_plan(path)


def test_v2_python_bridge_uses_fake_pyright_and_stages_python_text(tmp_path):
    repo, workflow = make_repo(tmp_path)
    server = tmp_path / "pyright"
    server.write_text("#!" + sys.executable + "\n" + FAKE)
    server.chmod(server.stat().st_mode | stat.S_IXUSR)
    accepted(workflow)
    (repo / "a.py").write_bytes("é😀 target = 1\r\nprint(target)\r\n".encode())
    plan = tmp_path / "v2.json"
    plan.write_text(json.dumps({
        "schema": "atlas-agent-context-plan/2",
        "members": [{"kind": "SEMANTIC", "backend": "python",
                     "query": {"kind": "hover", "path": "a.py",
                               "line": 0, "character": 8},
                     "executable": str(server), "version": "pyright 1.1.412"}]}))
    composition = build_context_composition(workflow, parse_context_plan(plan))
    try:
        selection = composition.selections[0]
        artifact = selection.result.validated_snapshot.document["artifacts"][0]
        assert selection.purpose == "python semantic context"
        assert artifact["mediaType"] == "application/vnd.atlas.python-semantic+json"
        relative = selection.result.bundle_path / artifact["relativePath"]
        semantic = relative.read_bytes()
        assert json.loads(semantic)["schema"] == "atlas-python-semantic/1"
        staged = _stage_pvc_context(selection)
        try:
            assert len(staged.text_authorities) == 1
            assert not staged.image_authorities
            assert staged.text_authorities[0].payload == semantic
            assert staged.text_authorities[0].ordinal == 0
            assert "application/vnd.atlas.python-semantic+json" in staged.framing
        finally:
            staged.cleanup()
    finally:
        cleanup_context_composition(composition)


@pytest.mark.parametrize("version", [None, "", "   ", 1, []])
def test_v2_semantic_version_validation_isolated(tmp_path, version):
    member = {
        "kind": "SEMANTIC", "backend": "python",
        "query": {"kind": "hover", "path": "a.py", "line": 0,
                  "character": 0},
        "executable": "/not-run-by-parser",
    }
    if version is not None:
        member["version"] = version
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"schema": "atlas-agent-context-plan/2",
                                "members": [member]}))
    with pytest.raises(ValueError, match="CONTEXT_PLAN_SEMANTIC_INVALID"):
        parse_context_plan(path)


def test_v2_semantic_nonempty_string_version_succeeds(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({
        "schema": "atlas-agent-context-plan/2",
        "members": [{
            "kind": "SEMANTIC", "backend": "python",
            "query": {"kind": "hover", "path": "a.py", "line": 0,
                      "character": 0},
            "executable": "/not-run-by-parser", "version": "fake 1",
        }],
    }))
    assert parse_context_plan(path)["schema"] == "atlas-agent-context-plan/2"
