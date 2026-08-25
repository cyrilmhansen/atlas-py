import pytest

from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import WorkflowError

from test_agent_workflow_w221 import accepted, make_repo


def _first_execution(workflow):
    return workflow._state()["generations"]["1"]["execution"]


def test_fresh_new_thread_completes(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="thread-A"))
    record = workflow._state()["generations"]["1"]
    assert record["status"] == "COMPLETED"
    assert record["result"]["freshness_verification"] == "verified"


def test_fresh_without_thread_interrupts(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    with pytest.raises(WorkflowError, match="FRESHNESS_UNVERIFIED"):
        workflow.execute(1, FakeExecutor())
    assert workflow._state()["generations"]["1"]["status"] == "INTERRUPTED"


def test_fresh_known_thread_interrupts(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="thread-A"))
    accepted(workflow, generation=2)
    with pytest.raises(WorkflowError, match="FRESHNESS_VIOLATION"):
        workflow.execute(2, FakeExecutor(observed_thread_id="thread-A"))
    assert workflow._state()["generations"]["2"]["status"] == "INTERRUPTED"


def test_reuse_same_thread_completes(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="thread-A"))
    target = _first_execution(workflow)["execution_id"]
    accepted(workflow, generation=2, session="reuse", target=target)
    workflow.execute(2, FakeExecutor(observed_thread_id="thread-A"))
    assert workflow._state()["generations"]["2"]["status"] == "COMPLETED"


def test_reuse_without_thread_interrupts(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="thread-A"))
    target = _first_execution(workflow)["execution_id"]
    accepted(workflow, generation=2, session="reuse", target=target)
    with pytest.raises(WorkflowError, match="REUSE_THREAD_UNVERIFIED"):
        workflow.execute(2, FakeExecutor())
    assert workflow._state()["generations"]["2"]["status"] == "INTERRUPTED"


def test_reuse_other_thread_interrupts(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="thread-A"))
    target = _first_execution(workflow)["execution_id"]
    accepted(workflow, generation=2, session="reuse", target=target)
    with pytest.raises(WorkflowError, match="REUSE_THREAD_MISMATCH"):
        workflow.execute(2, FakeExecutor(observed_thread_id="thread-B"))
    assert workflow._state()["generations"]["2"]["status"] == "INTERRUPTED"


def test_reuse_failure_interrupts_with_stable_code(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="thread-A"))
    target = _first_execution(workflow)["execution_id"]
    accepted(workflow, generation=2, session="reuse", target=target)
    with pytest.raises(WorkflowError, match="REUSE_SESSION_UNAVAILABLE"):
        workflow.execute(2, FakeExecutor(exit_code=7))
    assert workflow._state()["generations"]["2"]["status"] == "INTERRUPTED"
    interrupted = [event for event in workflow.journal.read() if event["event"] == "RUN_INTERRUPTED"]
    assert interrupted[-1]["payload"]["reason"] == "REUSE_SESSION_UNAVAILABLE"


def test_state_audit_freshness_is_verified_after_observation(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow, action="state_audit")
    workflow.execute(1, FakeExecutor(observed_thread_id="audit-thread"))
    result = workflow._state()["generations"]["1"]["result"]
    assert result["freshness_verification"] == "verified"
