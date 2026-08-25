import threading

import pytest

from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import WorkflowError

from test_agent_workflow_w221 import accepted, make_repo


def test_dispatch_runs_one_accepted_generation(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    fake = FakeExecutor(observed_thread_id="dispatch-thread")

    result = workflow.dispatch(fake)

    assert result["generation"] == 1
    assert result["action"] == "implementation"
    assert result["status"] == "COMPLETED"
    assert result["execution_id"]
    assert result["thread_id"] == "dispatch-thread"
    assert fake.launched == 1


def test_dispatch_without_accepted_generation_does_not_launch(tmp_path):
    _, workflow = make_repo(tmp_path)
    fake = FakeExecutor()

    with pytest.raises(WorkflowError, match="NO_DISPATCHABLE_GENERATION"):
        workflow.dispatch(fake)

    assert fake.launched == 0


def test_dispatch_does_not_skip_blocked_next_generation(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow, action="checkpoint")
    accepted(workflow, generation=2)
    fake = FakeExecutor()

    with pytest.raises(WorkflowError, match=r"GENERATION_1: CHECKPOINT_MANUAL_REQUIRED"):
        workflow.dispatch(fake)

    assert fake.launched == 0
    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"
    assert workflow._state()["generations"]["2"]["status"] == "ACCEPTED"


def test_concurrent_dispatches_start_one_generation_once(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    executors = [FakeExecutor(delay=0.05, observed_thread_id="one") for _ in range(2)]
    outcomes = []

    def dispatch(executor):
        try:
            outcomes.append(workflow.dispatch(executor))
        except WorkflowError as error:
            outcomes.append(str(error))

    threads = [threading.Thread(target=dispatch, args=(executor,)) for executor in executors]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(executor.launched for executor in executors) == 1
    assert sum(isinstance(outcome, dict) for outcome in outcomes) == 1
    assert sum("GENERATION_1" in outcome for outcome in outcomes if isinstance(outcome, str)) == 1
    events = workflow.journal.read()
    assert sum(event["event"] == "RUN_STARTED" for event in events) == 1
    assert sum(event["event"] == "RUN_COMPLETED" for event in events) == 1


def test_dispatch_executor_error_interrupts_generation(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)

    with pytest.raises(WorkflowError, match=r"GENERATION_1: EXECUTOR_EXIT_7"):
        workflow.dispatch(FakeExecutor(exit_code=7))

    assert workflow._state()["generations"]["1"]["status"] == "INTERRUPTED"


def test_dispatch_uses_existing_fresh_reuse_policy(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    first = FakeExecutor(observed_thread_id="policy-thread", observed_model="gpt-5.6-sol", observed_reasoning="medium")
    workflow.dispatch(first)
    target = workflow._state()["generations"]["1"]["execution"]["execution_id"]
    accepted(workflow, generation=2, session="reuse", target=target)
    second = FakeExecutor(observed_thread_id="policy-thread", observed_model="gpt-5.6-sol", observed_reasoning="medium")

    workflow.dispatch(second)

    snapshot = workflow._state()["generations"]["2"]["execution"]["policy_snapshot"]
    assert snapshot["session_mode"] == "reuse"
    assert snapshot["reused_from_execution_id"] == target
    assert snapshot["requested_thread_id"] == "policy-thread"
    assert second.launched == 1


def test_dispatch_checkpoint_is_manual_and_never_launches_codex(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow, action="checkpoint")
    fake = FakeExecutor()

    with pytest.raises(WorkflowError, match=r"GENERATION_1: CHECKPOINT_MANUAL_REQUIRED"):
        workflow.dispatch(fake)

    assert fake.launched == 0
