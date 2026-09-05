import hashlib
import pytest

from test_agent_workflow_w221 import accepted, make_repo
from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import WorkflowError, replay_journal


def _leave_prepared_run(workflow, generation, monkeypatch):
    """Crash after durable preparation, before the transaction is renamed."""
    original_admission = workflow._admit_run_start
    monkeypatch.setattr(workflow, "_admit_run_start", lambda state, gen: None)

    def crash(stage, _transaction):
        if stage == "prepared":
            raise RuntimeError("crash after RUN_STARTED preparation")

    try:
        with pytest.raises(RuntimeError, match="crash after RUN_STARTED preparation"):
            workflow.start_run(generation, hook=crash)
    finally:
        monkeypatch.setattr(workflow, "_admit_run_start", original_admission)


def _make_prepared_concurrent_case(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path, policy=False)
    accepted(workflow, generation=1, schema=1)
    accepted(workflow, generation=2, schema=1)
    _leave_prepared_run(workflow, 1, monkeypatch)
    assert workflow.recover()["generations"]["1"]["status"] == "RUNNING"
    _leave_prepared_run(workflow, 2, monkeypatch)
    return workflow


def test_modern_metadata_free_start_is_rejected_before_transition(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    before = workflow.journal.read()

    with pytest.raises(WorkflowError, match="EXECUTION_METADATA_REQUIRED"):
        workflow.start_run(1)

    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"
    assert workflow.journal.read() == before
    workflow._preflight()


def test_start_run_rejects_second_running_generation(tmp_path):
    _, workflow = make_repo(tmp_path, policy=False)
    first = accepted(workflow, generation=1, schema=1)
    accepted(workflow, generation=2, schema=1)
    workflow.start_run(1)
    with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
        workflow.start_run(2)
    assert workflow._state()["generations"]["2"]["status"] == "ACCEPTED"
    workflow.complete_run(1, {
        "generation": 1, "prompt_sha256": hashlib.sha256(first).hexdigest(),
        "action": "implementation", "outcome": "done",
    })
    workflow.start_run(2)
    assert workflow._state()["generations"]["2"]["status"] == "RUNNING"


def test_execute_and_dispatch_do_not_bypass_single_running_admission(tmp_path):
    _, workflow = make_repo(tmp_path, policy=False)
    accepted(workflow, generation=1, schema=1)
    accepted(workflow, generation=2, schema=1)
    workflow.start_run(1)

    executor = FakeExecutor()
    with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
        workflow.execute(2, executor)
    assert executor.launched == 0
    with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
        workflow.dispatch(executor)
    assert workflow._state()["generations"]["2"]["status"] == "ACCEPTED"


def test_recovery_admits_prepared_run_started_without_another_running(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path, policy=False)
    accepted(workflow, schema=1)
    _leave_prepared_run(workflow, 1, monkeypatch)

    events = workflow.journal.read()
    assert events[-1]["event"] == "TRANSITION_PREPARED"
    state = workflow.recover()

    assert state["generations"]["1"]["status"] == "RUNNING"
    assert sum(event["event"] == "RUN_STARTED" for event in workflow.journal.read()) == 1


def test_recovery_rejects_prepared_run_started_behind_existing_running(tmp_path, monkeypatch):
    workflow = _make_prepared_concurrent_case(tmp_path, monkeypatch)
    before = workflow._state()
    events_before = workflow.journal.read()

    with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
        workflow.recover()

    events_after = workflow.journal.read()
    assert events_after == events_before
    assert sum(event["event"] == "RUN_STARTED" for event in events_after) == 1
    assert workflow._state()["generations"]["2"]["status"] == "ACCEPTED"
    assert workflow._state()["generations"]["1"] == before["generations"]["1"]
    assert replay_journal(events_after)["outstanding_transactions"]
    prepared = events_after[-1]["payload"]
    assert (workflow.base / prepared["source"]).is_file()


def test_recovery_concurrent_rejection_preserves_running_generation(tmp_path, monkeypatch):
    workflow = _make_prepared_concurrent_case(tmp_path, monkeypatch)
    running_before = workflow._state()["generations"]["1"].copy()

    with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
        workflow.recover()

    assert workflow._state()["generations"]["1"] == running_before
    assert workflow._state()["generations"]["2"]["status"] == "ACCEPTED"
    assert not any(
        event["event"] == "RUN_STARTED" and event["payload"]["generation"] == 2
        for event in workflow.journal.read()
    )


def test_previously_blocked_prepared_start_recovers_after_running_terminates(
    tmp_path, monkeypatch
):
    _, workflow = make_repo(tmp_path, policy=False)
    accepted(workflow, generation=1, schema=1)
    accepted(workflow, generation=2, schema=1)
    _leave_prepared_run(workflow, 1, monkeypatch)
    assert workflow.recover()["generations"]["1"]["status"] == "RUNNING"
    workflow.interrupt_run(1, "test termination")
    _leave_prepared_run(workflow, 2, monkeypatch)

    state = workflow.recover()
    assert state["generations"]["1"]["status"] == "INTERRUPTED"
    assert state["generations"]["2"]["status"] == "RUNNING"
    assert sum(event["event"] == "RUN_STARTED" for event in workflow.journal.read()) == 2
