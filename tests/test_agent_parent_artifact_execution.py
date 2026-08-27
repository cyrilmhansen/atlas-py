import hashlib
import json

import pytest

from test_agent_operator_ergonomics import CodexFake, agent, jsonl
from test_agent_workflow_w221 import accepted, make_repo
from tools.atlas_agent.journal import canonical, encode_context_supplement
from tools.atlas_agent.workflow import WorkflowError


class PublicArtifactSaboteur(CodexFake):
    def __init__(self, mode):
        super().__init__(stdout=jsonl({"type": "thread.started", "thread_id": "t"}, agent("done")), observed_thread_id="t")
        self.mode = mode
        self.input_bytes = None

    def post_start_prepare(self, prepared):
        prepared = super().post_start_prepare(prepared)
        public = prepared.spec.runtime_root / "reports" / "contexts" / (prepared.spec.execution_id + "-effective.txt")
        if self.mode == "conflict":
            public.write_bytes(b"attacker bytes")
        elif self.mode == "symlink":
            target = prepared.spec.runtime_root.parent / "attacker-target.txt"
            target.write_bytes(b"attacker bytes")
            public.unlink()
            public.symlink_to(target)
        elif self.mode == "missing":
            public.unlink()
        elif self.mode == "directory":
            public.unlink()
            public.mkdir()
        return prepared

    def run_execution(self, prepared):
        self.input_bytes = prepared.spec.prompt_path.read_bytes()
        return super().run_execution(prepared)


@pytest.mark.parametrize("mode", ["conflict", "symlink", "missing", "directory"])
def test_public_effective_artifact_never_controls_execution(tmp_path, mode):
    _, workflow = make_repo(tmp_path)
    raw = accepted(workflow)
    executor = PublicArtifactSaboteur(mode)
    workflow.execute(1, executor)
    owner = workflow._state()["generations"]["1"]["execution"]
    context = encode_context_supplement({"kind": "none"}).encode()
    assert executor.input_bytes == raw + context
    assert hashlib.sha256(executor.input_bytes).hexdigest() == owner["effective_prompt_sha256"]


def _rehash(path, mutate):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    mutate(rows)
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        body = dict(row)
        body.pop("event_sha256", None)
        row["event_sha256"] = hashlib.sha256(canonical(body).encode()).hexdigest()
        previous = row["event_sha256"]
    path.write_text("".join(canonical(row) + "\n" for row in rows))


def test_preflight_rejects_rehashed_false_effective_hash(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "t"}, agent("done")), observed_thread_id="t"))

    def corrupt(rows):
        for row in rows:
            if row["event"] == "RUN_STARTED":
                row["payload"]["execution"]["effective_prompt_sha256"] = "f" * 64

    _rehash(workflow.journal.path, corrupt)
    with pytest.raises(WorkflowError):
        workflow.history()


def test_private_execution_input_failure_is_durably_interrupted(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    monkeypatch.setattr(workflow, "_stage_execution_input", lambda data, digest: (_ for _ in ()).throw(OSError("staging unavailable")))
    with pytest.raises(WorkflowError, match="EXECUTOR_FAILURE"):
        workflow.execute(1, CodexFake())
    assert workflow._state()["generations"]["1"]["status"] == "INTERRUPTED"


def test_unsafe_optional_parent_identifiers_are_omitted_consistently(tmp_path):
    _, workflow = make_repo(tmp_path)
    state = {"generations": {"1": {
        "generation": 1, "action": "implementation", "status": "COMPLETED",
        "execution": {"execution_id": "unsafe/id"},
        "result": {"executor_result": {"session_id": "unsafe thread"}},
    }}}
    data, _ = workflow._parent_context(state, 2)
    assert "execution_id:" not in data.decode()
    assert "thread_id:" not in data.decode()
