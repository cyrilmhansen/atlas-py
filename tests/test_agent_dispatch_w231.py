import json
import threading
from dataclasses import replace

import pytest

from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import WorkflowError

from test_agent_workflow_w221 import accepted, git, make_repo


@pytest.mark.parametrize("fail_after_publish", [False, True])
def test_prepared_execution_publication_is_recoverable(tmp_path, monkeypatch, fail_after_publish):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    original = workflow._publish_execution_artifact

    def fail_publication(path, value):
        if fail_after_publish:
            original(path, value)
        raise OSError("simulated publication crash")

    monkeypatch.setattr(workflow, "_publish_execution_artifact", fail_publication)
    with pytest.raises(OSError, match="simulated publication crash"):
        workflow.execute(1, FakeExecutor())

    events = workflow.journal.read()
    assert events[-1]["event"] == "TRANSITION_PREPARED"
    monkeypatch.setattr(workflow, "_publish_execution_artifact", original)
    state = workflow.recover()

    record = state["generations"]["1"]
    assert record["status"] == "RUNNING"
    report = workflow.base / record["execution"]["report_dir"]
    assert {path.name for path in report.iterdir()} == {"execution.json"}
    workflow._preflight()


def test_failed_journal_prepare_never_publishes_execution_owner(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    original = workflow.journal.append

    def fail_prepare(event, **fields):
        if event == "TRANSITION_PREPARED":
            raise OSError("journal unavailable")
        return original(event, **fields)

    monkeypatch.setattr(workflow.journal, "append", fail_prepare)
    with pytest.raises(OSError, match="journal unavailable"):
        workflow.execute(1, FakeExecutor())

    executions = workflow.base / "reports" / "executions"
    assert not executions.exists() or not any(executions.iterdir())
    workflow._preflight()


def test_failed_run_started_append_recovers_published_owner(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    original = workflow.journal.append

    def fail_terminal(event, **fields):
        if event == "RUN_STARTED":
            raise OSError("terminal journal failure")
        return original(event, **fields)

    monkeypatch.setattr(workflow.journal, "append", fail_terminal)
    with pytest.raises(OSError, match="terminal journal failure"):
        workflow.execute(1, FakeExecutor())
    assert workflow.journal.read()[-1]["event"] == "TRANSITION_PREPARED"

    monkeypatch.setattr(workflow.journal, "append", original)
    state = workflow.recover()
    record = state["generations"]["1"]
    assert record["status"] == "RUNNING"
    assert (workflow.base / record["execution"]["report_dir"] / "execution.json").is_file()
    workflow._preflight()


def test_execution_directory_publication_fsyncs_parent(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    synced = []
    from tools.atlas_agent import workflow as workflow_module
    original = workflow_module.fsync_dir

    def record_sync(path):
        synced.append(path)
        return original(path)

    monkeypatch.setattr(workflow_module, "fsync_dir", record_sync)
    workflow.execute(1, FakeExecutor(observed_thread_id="durability-thread"))
    report = workflow.base / workflow._state()["generations"]["1"]["execution"]["report_dir"]
    assert report.parent in synced


def test_recover_completed_run_started_when_state_save_failed(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    original = workflow._save

    def fail_running_save(state):
        if state["generations"]["1"]["status"] == "RUNNING":
            raise OSError("state save crash")
        return original(state)

    monkeypatch.setattr(workflow, "_save", fail_running_save)
    with pytest.raises(OSError, match="state save crash"):
        workflow.execute(1, FakeExecutor())
    assert workflow.journal.read()[-1]["event"] == "RUN_STARTED"

    monkeypatch.setattr(workflow, "_save", original)
    state = workflow.recover()
    assert state["generations"]["1"]["status"] == "RUNNING"
    workflow._preflight()


def test_recovery_rejects_corrupt_prepared_execution_artifact(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    original = workflow._publish_execution_artifact

    def publish_then_crash(path, value):
        original(path, value)
        raise OSError("publication crash")

    monkeypatch.setattr(workflow, "_publish_execution_artifact", publish_then_crash)
    with pytest.raises(OSError, match="publication crash"):
        workflow.execute(1, FakeExecutor())
    prepared = workflow.journal.read()[-1]["payload"]
    artifact = workflow.base / prepared["execution"]["report_dir"] / "execution.json"
    artifact.write_text("{}\n")

    monkeypatch.setattr(workflow, "_publish_execution_artifact", original)
    with pytest.raises(WorkflowError, match="RECOVERY_EXECUTION_ARTIFACT_CONFLICT"):
        workflow.recover()


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


def _completed_usage(workflow):
    accepted(workflow)
    stdout=(json.dumps({"type":"turn.completed","usage":{"input_tokens":12,"cached_input_tokens":3,"output_tokens":4,"reasoning_output_tokens":2,"total_tokens":16}})+"\n").encode()
    workflow.execute(1,FakeExecutor(stdout=stdout,observed_thread_id="usage-thread",observed_model="gpt-5.6-sol",observed_reasoning="medium"))
    state=workflow._state(); record=state["generations"]["1"]
    path=workflow.base/record["execution"]["report_dir"]/"usage.json"
    return state,record,path


def test_dispatch_summary_displays_valid_usage(tmp_path):
    _,workflow=make_repo(tmp_path); state,_,_= _completed_usage(workflow)
    assert workflow._dispatch_summary(1,state)["tokens"]["input_tokens"]==12


@pytest.mark.parametrize("mutation",["array","schema","generation","execution_id","status","metrics","complete_unavailable","unavailable_exec","partial_without_cause","complete_malformed"])
def test_dispatch_summary_omits_untrusted_usage(tmp_path,mutation):
    _,workflow=make_repo(tmp_path); state,record,path=_completed_usage(workflow)
    usage=json.loads(path.read_text())
    if mutation=="array": usage=[]
    elif mutation=="schema": usage["schema"]="foreign-usage/9"
    elif mutation=="generation": usage["generation"]=99
    elif mutation=="execution_id": usage["execution_id"]="foreign-owner"
    elif mutation=="status": usage["status"]="trusted"
    elif mutation=="metrics": usage["run"]={"input_tokens":"twelve"}
    elif mutation=="complete_unavailable": usage["sources"]=["unavailable"]
    elif mutation=="unavailable_exec": usage.update(status="unavailable",run=None,sources=["exec-jsonl"])
    elif mutation=="partial_without_cause": usage["status"]="partial"
    elif mutation=="complete_malformed": usage["parser_malformed_lines"]=1
    path.write_text(json.dumps(usage)+"\n")
    summary=workflow._dispatch_summary(1,state)
    assert "tokens" not in summary
    assert state["generations"]["1"]["status"]=="COMPLETED"


def test_dispatch_summary_omits_unavailable_usage(tmp_path):
    _,workflow=make_repo(tmp_path); accepted(workflow); workflow.execute(1,FakeExecutor(observed_thread_id="usage-thread",observed_model="gpt-5.6-sol",observed_reasoning="medium"))
    state=workflow._state()
    assert "tokens" not in workflow._dispatch_summary(1,state)


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


def test_concurrent_dispatch_cannot_validate_private_execution_artifact(tmp_path, monkeypatch):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    publishing = threading.Event()
    release = threading.Event()
    original = workflow._publish_execution_artifact
    original_execute = workflow.execute
    selected = threading.Barrier(2)

    def paused_publish(path, value):
        publishing.set()
        assert release.wait(2)
        return original(path, value)

    def synchronized_execute(*args, **kwargs):
        selected.wait(2)
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(workflow, "_publish_execution_artifact", paused_publish)
    monkeypatch.setattr(workflow, "execute", synchronized_execute)
    executors = [FakeExecutor(observed_thread_id=value) for value in ("one", "two")]
    outcomes = []

    def dispatch(executor):
        try:
            outcomes.append(workflow.dispatch(executor))
        except WorkflowError as error:
            outcomes.append(str(error))

    first = threading.Thread(target=dispatch, args=(executors[0],))
    second = threading.Thread(target=dispatch, args=(executors[1],))
    first.start()
    second.start()
    assert publishing.wait(2)
    assert first.is_alive() and second.is_alive()
    assert not any(event["event"] == "RUN_STARTED" for event in workflow.journal.read())
    release.set()
    first.join(2); second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert sum(executor.launched for executor in executors) == 1
    assert sum(isinstance(outcome, dict) for outcome in outcomes) == 1
    errors = [outcome for outcome in outcomes if isinstance(outcome, str)]
    assert len(errors) == 1 and "GENERATION_1" in errors[0]
    assert "SPOOL_CORRUPT" not in errors[0]


def test_dispatch_executor_error_interrupts_generation(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)

    with pytest.raises(WorkflowError, match=r"GENERATION_1: EXECUTOR_EXIT_7"):
        workflow.dispatch(FakeExecutor(exit_code=7))

    assert workflow._state()["generations"]["1"]["status"] == "INTERRUPTED"


def test_dispatch_preserves_repository_policy_interruption(tmp_path, monkeypatch):
    repo, workflow = make_repo(tmp_path)
    accepted(workflow)

    class PolicyViolatingExecutor(FakeExecutor):
        def run_execution(self, prepared):
            result = super().run_execution(prepared)
            (repo / "a").write_text("executor changed tracked content")
            git(repo, "add", "a")
            return result

    def reject_second_interruption(*args, **kwargs):
        pytest.fail("dispatch attempted to interrupt an already interrupted generation")

    events=[]
    monkeypatch.setattr(workflow, "interrupt_run", reject_second_interruption)
    with pytest.raises(
        WorkflowError,
        match=r"^GENERATION_1: REPOSITORY_POLICY_VIOLATION$",
    ):
        workflow.dispatch(PolicyViolatingExecutor(observed_thread_id="policy-thread"),observer=events.append)

    assert workflow._state()["generations"]["1"]["status"] == "INTERRUPTED"
    interruptions = [
        event for event in workflow.journal.read()
        if event["event"] == "RUN_INTERRUPTED"
    ]
    assert len(interruptions) == 1
    assert interruptions[0]["payload"]["reason"] == "REPOSITORY_POLICY_VIOLATION"
    executor_result=interruptions[0]["payload"]["executor_result"]
    assert executor_result["session_id"]=="policy-thread"
    assert executor_result["execution_id"]==interruptions[0]["payload"]["execution"]["execution_id"]
    assert executor_result["started_at"] and executor_result["finished_at"]
    finished=next(event for event in events if event["kind"]=="dispatch_finished")
    assert finished["thread_id"]=="policy-thread"
    assert finished["started_at"]==executor_result["started_at"]
    assert finished["finished_at"]==executor_result["finished_at"]


def test_reports_and_history_require_terminal_lifecycle(tmp_path):
    _,workflow=make_repo(tmp_path)
    def message(text):
        return (json.dumps({"type":"item.completed","item":{"type":"agent_message","text":text}})+"\n").encode()
    class CodexFake(FakeExecutor):
        def prepare_execution(self,spec):
            return replace(super().prepare_execution(spec),executor="codex")
    accepted(workflow)
    workflow.execute(1,CodexFake(stdout=message("older terminal report"),observed_thread_id="report-thread-1"))
    accepted(workflow,generation=2)
    ready=threading.Event(); release=threading.Event(); errors=[]
    class BlockingCodex(CodexFake):
        def run_execution(self,prepared):
            prepared.spec.report_dir.mkdir(parents=True,exist_ok=True)
            (prepared.spec.report_dir/"stdout.log").write_bytes(message("running commentary"))
            ready.set()
            assert release.wait(2)
            return super().run_execution(prepared)
    executor=BlockingCodex(stdout=message("new terminal report"),observed_thread_id="report-thread-2")
    thread=threading.Thread(target=lambda: _capture_execute(workflow,2,executor,errors))
    thread.start(); assert ready.wait(2)
    with pytest.raises(WorkflowError,match="EXECUTION_NOT_TERMINAL"):
        workflow.report(2)
    assert workflow.report()=="older terminal report"
    running=next(row for row in workflow.history() if row["generation"]==2)
    assert running["status"]=="RUNNING" and running["report_available"] is False
    release.set(); thread.join(2)
    assert not thread.is_alive() and errors==[]
    accepted(workflow,generation=3)
    with pytest.raises(WorkflowError,match="EXECUTOR_EXIT_7"):
        workflow.execute(3,CodexFake(exit_code=7,stdout=message("interrupted final report"),observed_thread_id="report-thread-3"))
    assert workflow.report(3)=="interrupted final report"
    interrupted=next(row for row in workflow.history() if row["generation"]==3)
    assert interrupted["status"]=="INTERRUPTED" and interrupted["report_available"] is True


def _capture_execute(workflow,generation,executor,errors):
    try: workflow.execute(generation,executor)
    except Exception as error: errors.append(error)


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
