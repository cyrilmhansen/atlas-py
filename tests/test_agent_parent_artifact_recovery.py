import hashlib
import json
import pytest

from test_agent_operator_ergonomics import CodexFake, agent, jsonl
from test_agent_workflow_w221 import accepted, make_repo
from tools.atlas_agent.journal import Journal, JournalError, canonical
from tools.atlas_agent.spool import sha
from tools.atlas_agent.workflow import WorkflowError


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


def _journaled_run(w):
    accepted(w)
    w.execute(1, CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "p"}, agent("done")), observed_thread_id="p"))
    return w._state()["generations"]["1"]["execution"]


def test_rehashed_context_provenance_is_strictly_validated(tmp_path):
    _, w = make_repo(tmp_path)
    owner = _journaled_run(w)
    path = w.journal.path

    def inject(rows):
        for row in rows:
            if row["event"] == "TRANSITION_PREPARED" and "context_supplement" in row["payload"]:
                row["payload"]["context_supplement"] += "\nforged"
                return
        raise AssertionError("missing RUN_STARTED preparation")

    _rehash(path, inject)
    with pytest.raises(JournalError):
        Journal(path).read()
    assert owner["context_path"].startswith("reports/contexts/")


@pytest.mark.parametrize("field,value", [
    ("context_path", 7),
    ("effective_prompt_sha256", None),
    ("context_sha256", "not-a-sha256"),
    ("effective_prompt_path", "reports/contexts/../escape.txt"),
])
def test_rehashed_provenance_wrong_type_hash_and_path_are_rejected(tmp_path, field, value):
    _, w = make_repo(tmp_path)
    _journaled_run(w)

    def mutate(rows):
        for row in rows:
            if row["event"] == "TRANSITION_PREPARED" and "execution" in row["payload"]:
                row["payload"]["execution"][field] = value
                return
        raise AssertionError("missing execution provenance")

    _rehash(w.journal.path, mutate)
    with pytest.raises(JournalError):
        w.journal.read()


def test_unpublishable_context_does_not_strand_authoritative_recovery(tmp_path):
    _, w = make_repo(tmp_path)
    raw = accepted(w)
    prompt_sha = hashlib.sha256(raw).hexdigest()
    supplement = w._parent_context({"generations": {}}, 1)[0].decode()
    execution_id = "123e4567-e89b-12d3-a456-426614174000"
    context = w.base / "reports" / "contexts"
    context.mkdir(parents=True)
    (context / (execution_id + ".txt")).mkdir()
    # Use the public launcher boundary to construct the owner.  In particular,
    # start_run resolves and archives the policy authority rather than leaving
    # a hand-built modern snapshot with no historical policy binding.
    execution = {
        "execution_id": execution_id, "executor": "fake", "started_at": "2026-08-26T00:00:00Z",
        "pid": None, "report_dir": "reports/executions/" + execution_id,
        "permission_envelope": {"sandbox_mode": "workspace-write", "approval_policy": "never",
                                 "approvals_reviewer": "user", "strict_config": True,
                                 "ignore_rules": True, "network_access": False},
    }
    def crash_after_prepare(stage, _transaction):
        if stage == "prepared":
            raise RuntimeError("simulated crash after authoritative preparation")
    with pytest.raises(RuntimeError, match="simulated crash"):
        w.start_run(1, hook=crash_after_prepare, execution=execution)
    state = w.recover()
    assert state["generations"]["1"]["status"] == "RUNNING"


def test_recovery_uses_journaled_context_and_immutable_prompt(tmp_path):
    _, w = make_repo(tmp_path)
    accepted(w)
    accepted(w, generation=2)
    child = w.execute(2, CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "c"}, agent("done")), observed_thread_id="c"))
    owner = w._state()["generations"]["2"]["execution"]
    original = (w.base / owner["context_path"]).read_bytes()
    (w.base / owner["context_path"]).unlink()
    (w.base / owner["effective_prompt_path"]).unlink()
    # The parent legitimately changes after the child was prepared.  Recovery
    # must retain the child transaction's historical supplement.
    w.execute(1, CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "p"}, agent("done")), observed_thread_id="p"))
    state = w.recover()
    restored = (w.base / owner["context_path"]).read_bytes()
    effective = (w.base / owner["effective_prompt_path"]).read_bytes()
    prompt = (w.base / "prompts" / (state["generations"]["2"]["prompt_sha256"] + ".txt")).read_bytes()
    assert restored == original
    assert effective == prompt + original
    assert hashlib.sha256(effective).hexdigest() == owner["effective_prompt_sha256"]
    assert child is not None
