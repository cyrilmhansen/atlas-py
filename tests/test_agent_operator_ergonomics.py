import json
import os
import sys
import time
from dataclasses import replace

import pytest

from tools.atlas_agent.cli import DispatchPresenter, main
from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutorError, ExecutionSpec, FakeExecutor
from tools.atlas_agent.workflow import WorkflowError

from test_agent_checkpoint_boundary import accepted_dirty_checkpoint, git as checkpoint_git, prompt as checkpoint_prompt
from test_agent_workflow_w221 import accepted, make_repo


def jsonl(*events):
    return b"".join(json.dumps(event).encode()+b"\n" for event in events)


def agent(text):
    return {"type":"item.completed","item":{"type":"agent_message","text":text}}


class CodexFake(FakeExecutor):
    def prepare_execution(self,spec):
        return replace(super().prepare_execution(spec),executor="codex")


def test_fresh_dispatch_summary_and_unavailable_telemetry_is_omitted(tmp_path,capsys):
    _,workflow=make_repo(tmp_path); accepted(workflow)
    presenter=DispatchPresenter()
    result=workflow.dispatch(CodexFake(stdout=jsonl({"type":"thread.started","thread_id":"fresh-thread"},agent("done")),observed_thread_id="fresh-thread"),observer=presenter.event)

    output=capsys.readouterr().out
    assert "Atlas dispatch\ng1 · implementation · fresh" in output
    assert "profile implementation" in output
    assert "model gpt-5.6-luna · reasoning medium" in output
    assert "sandbox workspace-write · network disabled" in output
    assert "Atlas dispatch result\ng1 · implementation · COMPLETED" in output
    assert "tokens " not in output
    assert "report available" in output
    assert result["status"]=="COMPLETED"


def test_dispatch_presentation_uses_model_from_resolved_policy_snapshot(capsys):
    DispatchPresenter().event({
        "kind":"dispatch_started",
        "generation":7,
        "action":"implementation",
        "session_mode":"fresh",
        "policy_snapshot":{"profile":"implementation","requested_model":"policy-selected-model","requested_reasoning_effort":"medium"},
        "permission_envelope":{"sandbox_mode":"workspace-write","network_access":False},
    })
    output=capsys.readouterr().out
    assert "model policy-selected-model · reasoning medium" in output


def test_reuse_dispatch_summary_names_requested_execution_and_thread(tmp_path,capsys):
    _,workflow=make_repo(tmp_path); accepted(workflow)
    workflow.dispatch(CodexFake(stdout=jsonl({"type":"thread.started","thread_id":"thread-A"},agent("first")),observed_thread_id="thread-A"))
    target=workflow._state()["generations"]["1"]["execution"]["execution_id"]
    accepted(workflow,generation=2,session="reuse",target=target)
    presenter=DispatchPresenter()
    workflow.dispatch(CodexFake(stdout=jsonl({"type":"thread.started","thread_id":"thread-A"},agent("second")),observed_thread_id="thread-A"),observer=presenter.event)

    output=capsys.readouterr().out
    assert "g2 · implementation · reuse" in output
    assert f"reuse execution {target} · thread thread-A" in output


def test_report_selects_final_agent_message_and_explicit_generation(tmp_path):
    _,workflow=make_repo(tmp_path); accepted(workflow)
    workflow.execute(1,CodexFake(stdout=jsonl(agent("progress"),agent("final report")),observed_thread_id="thread-1"))
    assert workflow.report(1)=="final report"


def oversized_event(text="x"):
    return json.dumps({"type":"future.event","payload":text}).encode()


def test_report_skips_oversized_unrelated_events_until_a_valid_message(tmp_path):
    path=tmp_path/"stdout.log"
    path.write_bytes(oversized_event("x"*400)+b"\n"+jsonl(agent("final report")))
    assert CodexExecutor.latest_agent_report(path,max_line_bytes=128)=="final report"


def test_report_fails_closed_after_oversized_event_following_message(tmp_path):
    path=tmp_path/"stdout.log"
    path.write_bytes(jsonl(agent("older"))+oversized_event("x"*400)+b"\n")
    with pytest.raises(ExecutorError,match="EXECUTOR_OUTPUT_MALFORMED: oversized JSONL record"):
        CodexExecutor.latest_agent_report(path,max_line_bytes=128)


@pytest.mark.parametrize("records",[
    [oversized_event("x"*400)],
    [oversized_event("x"*400),oversized_event("y"*400)],
])
def test_report_does_not_fabricate_report_from_oversized_records(tmp_path,records):
    path=tmp_path/"stdout.log"
    path.write_bytes(b"\n".join(records)+b"\n")
    with pytest.raises(ExecutorError,match="EXECUTOR_OUTPUT_MALFORMED: oversized JSONL record"):
        CodexExecutor.latest_agent_report(path,max_line_bytes=128)


def test_report_later_message_reestablishes_latest_after_multiple_oversized_events(tmp_path):
    path=tmp_path/"stdout.log"
    path.write_bytes(oversized_event("x"*400)+b"\n"+oversized_event("y"*400)+b"\n"+jsonl(agent("final report")))
    assert CodexExecutor.latest_agent_report(path,max_line_bytes=128)=="final report"


def test_report_rejects_malformed_bounded_json_after_oversized_event(tmp_path):
    path=tmp_path/"stdout.log"
    path.write_bytes(oversized_event("x"*400)+b"\nnot-json\n"+jsonl(agent("final report")))
    with pytest.raises(ExecutorError,match="EXECUTOR_OUTPUT_MALFORMED"):
        CodexExecutor.latest_agent_report(path,max_line_bytes=128)


def test_report_without_generation_selects_most_recent_available(tmp_path):
    _,workflow=make_repo(tmp_path); accepted(workflow)
    workflow.execute(1,CodexFake(stdout=jsonl(agent("older")),observed_thread_id="thread-1"))
    accepted(workflow,generation=2)
    workflow.execute(2,CodexFake(stdout=jsonl(agent("newer")),observed_thread_id="thread-2"))
    assert workflow.report()=="newer"


@pytest.mark.parametrize(("stdout","error"),[(b"not-json\n","EXECUTOR_OUTPUT_MALFORMED"),(jsonl({"type":"turn.completed"}),"EXECUTION_REPORT_MISSING")])
def test_missing_or_malformed_report_fails_clearly(tmp_path,stdout,error):
    _,workflow=make_repo(tmp_path); accepted(workflow)
    workflow.execute(1,CodexFake(stdout=stdout,observed_thread_id="thread-1"))
    with pytest.raises(WorkflowError,match=error): workflow.report(1)


def test_progress_presentation_is_non_tty_and_cannot_change_outcome(tmp_path,capsys):
    _,workflow=make_repo(tmp_path); accepted(workflow)
    presenter=DispatchPresenter()
    class ProgressFake(CodexFake):
        def run_execution(self,prepared):
            presenter.progress({"kind":"agent_message","elapsed_seconds":61,"message":"useful progress"})
            presenter.progress({"kind":"heartbeat","elapsed_seconds":92})
            return super().run_execution(prepared)
    result=workflow.dispatch(ProgressFake(stdout=jsonl(agent("final")),observed_thread_id="thread-1"),observer=presenter.event)
    output=capsys.readouterr().out
    assert "[1m 01s] useful progress" in output and "[1m 32s] still running..." in output
    assert result["status"]=="COMPLETED"
    # A broken presentation sink is also observational only.
    _,workflow2=make_repo(tmp_path/"broken"); accepted(workflow2)
    assert workflow2.dispatch(CodexFake(stdout=jsonl(agent("final")),observed_thread_id="thread-2"),observer=lambda event: (_ for _ in ()).throw(RuntimeError("closed pipe")))["status"]=="COMPLETED"


def test_codex_streams_messages_and_heartbeats_without_changing_artifact(tmp_path):
    executable=tmp_path/"fake-codex"
    executable.write_text("""#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "codex-cli test"
  exit 0
fi
printf '%s\\n' '{"type":"thread.started","thread_id":"thread-live"}'
sleep 0.05
printf '%s\\n' '{"type":"item.completed","item":{"type":"agent_message","text":"live update"}}'
""")
    executable.chmod(0o755)
    prompt=tmp_path/"prompt.txt"; prompt.write_text("work\n")
    events=[]
    executor=CodexExecutor(executable=str(executable),timeout_seconds=2,heartbeat_seconds=0.01,progress_callback=events.append)
    spec=ExecutionSpec(1,"a"*64,"implementation",prompt,tmp_path,"execution",tmp_path/"report",tmp_path,input_mode="legacy")
    prepared=executor.post_start_prepare(executor.prepare_execution(spec))

    result=executor.run_execution(prepared)

    assert result.outcome=="success"
    assert any(event["kind"]=="heartbeat" for event in events)
    assert any(event["kind"]=="agent_message" and event["message"]=="live update" for event in events)
    assert CodexExecutor.latest_agent_report(tmp_path/"report"/"stdout.log")=="live update"


def test_codex_closes_stdin_after_input_handoff(tmp_path):
    body='''import json, sys
if "--version" in sys.argv:
    print("codex-cli test")
    raise SystemExit(0)
sys.stdin.buffer.read()
print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"received"}}), flush=True)
'''
    executor,prepared=_prepared_script_executor(tmp_path,body,timeout_seconds=1,heartbeat_seconds=1)

    result=executor.run_execution(prepared)

    assert result.outcome=="success"
    assert (tmp_path/"report"/"stdout.log").read_bytes()==jsonl(agent("received"))


def _prepared_script_executor(tmp_path, body, **kwargs):
    executable=tmp_path/"fake-codex"
    executable.write_text(f"#!{sys.executable}\n" + body)
    executable.chmod(0o755)
    prompt=tmp_path/"prompt.txt"; prompt.write_text("work\n")
    executor=CodexExecutor(executable=str(executable),**kwargs)
    spec=ExecutionSpec(1,"a"*64,"implementation",prompt,tmp_path,"execution",tmp_path/"report",tmp_path,input_mode="legacy")
    return executor,executor.post_start_prepare(executor.prepare_execution(spec))


def test_progress_write_failure_terminates_and_reaps_child(tmp_path):
    pid_path=tmp_path/"pid"
    marker=tmp_path/"continued"
    body=f'''import json, os, sys, time
if "--version" in sys.argv:
    print("codex-cli test")
    raise SystemExit(0)
open({str(pid_path)!r}, "w").write(str(os.getpid()))
print(json.dumps({{"type":"item.completed","item":{{"type":"agent_message","text":"update"}}}}), flush=True)
time.sleep(2)
open({str(marker)!r}, "w").write("continued")
'''
    def broken_output(event):
        raise OSError("closed progress stream")
    executor,prepared=_prepared_script_executor(tmp_path,body,timeout_seconds=4,heartbeat_seconds=1,progress_callback=broken_output)

    with pytest.raises(Exception,match="closed progress stream"):
        executor.run_execution(prepared)

    pid=int(pid_path.read_text())
    with pytest.raises(ChildProcessError): os.waitpid(pid,os.WNOHANG)
    time.sleep(0.05)
    assert not marker.exists()


def test_stdout_eof_does_not_disable_timeout_and_shutdown_is_bounded(tmp_path):
    body='''import os, signal, sys, time
if "--version" in sys.argv:
    print("codex-cli test")
    raise SystemExit(0)
signal.signal(signal.SIGINT, signal.SIG_IGN)
os.close(1)
time.sleep(10)
'''
    executor,prepared=_prepared_script_executor(tmp_path,body,timeout_seconds=0.1,heartbeat_seconds=1)
    executor.SHUTDOWN_GRACE_SECONDS=0.1
    executor.SHUTDOWN_KILL_SECONDS=0.5

    started=time.monotonic()
    result=executor.run_execution(prepared)
    elapsed=time.monotonic()-started

    assert result.timed_out is True and result.outcome=="timeout"
    assert elapsed < 1


def test_human_history_has_stable_operator_fields(tmp_path,monkeypatch,capsys):
    root,workflow=make_repo(tmp_path); accepted(workflow)
    workflow.execute(1,CodexFake(stdout=jsonl(agent("report")),observed_thread_id="thread-1"))
    execution=workflow._state()["generations"]["1"]["execution"]["execution_id"]
    monkeypatch.chdir(root)
    assert main(["history"])==0
    output=capsys.readouterr().out
    assert f"g1 · implementation · COMPLETED" in output
    assert f"exec {execution[:12]}" in output
    assert "report yes" in output


def test_successful_checkpoint_prints_result_without_changing_error_behavior(tmp_path,monkeypatch,capsys):
    root,workflow=make_repo(tmp_path); accepted_dirty_checkpoint(root,workflow)
    monkeypatch.chdir(root)
    assert main(["checkpoint","2","--message","Operator checkpoint"])==0
    commit=checkpoint_git(root,"rev-parse","HEAD")
    output=capsys.readouterr().out
    assert "g2 · COMPLETED" in output
    assert f"commit {commit[:12]} · Operator checkpoint" in output
    assert "repository witness MATCH" in output
    assert "push not performed" in output

    checkpoint_prompt(workflow,root,3,"implementation")
    assert main(["checkpoint","3","--message","must fail"])==1
    assert "GENERATION_IS_NOT_CHECKPOINT" in capsys.readouterr().err
