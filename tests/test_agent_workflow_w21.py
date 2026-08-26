import hashlib,json,os,subprocess,sys,threading
from pathlib import Path
import pytest
from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import Workflow,WorkflowError

def git(p,*args): return subprocess.check_output(["git",*args],cwd=p,text=True).strip()
@pytest.fixture
def repo(tmp_path):
    p=tmp_path/"repo"; p.mkdir(); git(p,"init","-q"); git(p,"config","user.email","t@e"); git(p,"config","user.name","t"); (p/"a").write_text("a"); (p/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n'); git(p,"add","."); git(p,"commit","-qm","g"); w=Workflow(p); w.init(); return p,w
def prompt(w):
    raw=f'''+++\nschema = "atlas-agent-prompt/1"\ngeneration = 1\nparent = "genesis"\ncheckpoint = "W21"\naction = "implementation"\nexpected_head = "{git(w.root,"rev-parse","HEAD")}"\nsession_mode = "fresh"\n+++\nReturn exactly: ATLAS_CODEX_SMOKE_OK\n'''.encode(); (w.base/"inbox"/"prompt.txt").write_bytes(raw); return raw
def sha(raw): return hashlib.sha256(raw).hexdigest()
def accepted(w): raw=prompt(w); w.ingest(); return raw
def test_fake_success_completed_and_captured(repo):
    p,w=repo; raw=accepted(w); fake=FakeExecutor(stdout=b"out",stderr=b"err"); w.execute(1,fake); rec=w._state()["generations"]["1"]; assert rec["status"]=="COMPLETED"; assert fake.launched==1; execution=rec["execution"]; d=w.base/execution["report_dir"]; assert (d/"stdout.log").read_bytes()==b"out"; assert (d/"stderr.log").read_bytes()==b"err"; result=json.loads((d/"result.json").read_text()); assert result["execution_id"]==execution["execution_id"]; assert rec["result"]["prompt_sha256"]==sha(raw)
def test_fake_nonzero_interrupts(repo):
    p,w=repo; accepted(w); fake=FakeExecutor(exit_code=7)
    with pytest.raises(WorkflowError,match="EXECUTOR_EXIT"): w.execute(1,fake)
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"; assert fake.launched==1

def test_durable_interruption_survives_projection_save_failure(repo, monkeypatch):
    p,w=repo; accepted(w); original_save=w._save; original_interrupt=w.interrupt_run; calls=[]
    def fail_terminal_projection(state):
        if state["generations"]["1"]["status"]=="INTERRUPTED":
            raise OSError("simulated projection failure")
        return original_save(state)
    def counted_interrupt(*args,**kwargs):
        calls.append((args,kwargs)); return original_interrupt(*args,**kwargs)
    monkeypatch.setattr(w,"_save",fail_terminal_projection)
    monkeypatch.setattr(w,"interrupt_run",counted_interrupt)
    with pytest.raises(WorkflowError,match=r"^EXECUTOR_EXIT_7$"):
        w.execute(1,FakeExecutor(exit_code=7,observed_thread_id="terminal-thread"))
    assert len(calls)==1
    assert [event["event"] for event in w.journal.read()].count("RUN_INTERRUPTED")==1
    assert w._state()["generations"]["1"]["status"]=="RUNNING"
    monkeypatch.setattr(w,"_save",original_save)
    recovered=w.recover()
    assert recovered["generations"]["1"]["status"]=="INTERRUPTED"
    assert recovered["generations"]["1"]["execution_result"]["session_id"]=="terminal-thread"
    assert w._state()==recovered

def test_recovery_reconstructs_missing_artifacts_after_durable_executor_exception(repo, monkeypatch):
    p,w=repo; accepted(w); original_save=w._save; original_interrupt=w.interrupt_run; calls=[]
    def fail_terminal_projection(state):
        if state["generations"]["1"]["status"]=="INTERRUPTED":
            raise OSError("simulated projection failure")
        return original_save(state)
    def counted_interrupt(*args,**kwargs):
        calls.append((args,kwargs)); return original_interrupt(*args,**kwargs)
    monkeypatch.setattr(w,"_save",fail_terminal_projection)
    monkeypatch.setattr(w,"interrupt_run",counted_interrupt)
    with pytest.raises(WorkflowError,match=r"^EXECUTOR_FAILURE: fake executor crash$"):
        w.execute(1,FakeExecutor(crash=True))
    interrupted=[event for event in w.journal.read() if event["event"]=="RUN_INTERRUPTED"]
    assert len(calls)==1 and len(interrupted)==1
    assert interrupted[0]["payload"]["reason"]=="EXECUTOR_FAILURE: fake executor crash"
    assert interrupted[0]["payload"]["fallback_artifacts"]==["stdout.log","stderr.log","result.json"]
    report=w.base/interrupted[0]["payload"]["execution"]["report_dir"]
    assert {path.name for path in report.iterdir()}=={"execution.json"}
    monkeypatch.setattr(w,"_save",original_save)
    recovered=w.recover()
    assert recovered["generations"]["1"]["status"]=="INTERRUPTED"
    assert (report/"stdout.log").read_bytes()==b"" and (report/"stderr.log").read_bytes()==b""
    result=json.loads((report/"result.json").read_text())
    assert result["error"]==interrupted[0]["payload"]["reason"]
    assert result["execution_id"]==interrupted[0]["payload"]["execution"]["execution_id"]
    w._preflight()

def test_recovery_does_not_replace_mismatched_interruption_artifact(repo, monkeypatch):
    p,w=repo; accepted(w); original_save=w._save
    def fail_terminal_projection(state):
        if state["generations"]["1"]["status"]=="INTERRUPTED": raise OSError("projection failed")
        return original_save(state)
    monkeypatch.setattr(w,"_save",fail_terminal_projection)
    with pytest.raises(WorkflowError,match="fake executor crash"):
        w.execute(1,FakeExecutor(crash=True))
    event=next(event for event in reversed(w.journal.read()) if event["event"]=="RUN_INTERRUPTED")
    report=w.base/event["payload"]["execution"]["report_dir"]
    (report/"result.json").write_text(json.dumps({"execution_id":"foreign"})+"\n")
    monkeypatch.setattr(w,"_save",original_save)
    with pytest.raises(WorkflowError,match="RECOVERY_FALLBACK_ARTIFACT_CONFLICT"):
        w.recover()
    assert json.loads((report/"result.json").read_text())["execution_id"]=="foreign"

def _crashed_missing_fallback(repo,monkeypatch):
    p,w=repo; accepted(w); original_save=w._save
    def fail_terminal_projection(state):
        if state["generations"]["1"]["status"]=="INTERRUPTED": raise OSError("projection failed")
        return original_save(state)
    monkeypatch.setattr(w,"_save",fail_terminal_projection)
    with pytest.raises(WorkflowError,match="fake executor crash"):
        w.execute(1,FakeExecutor(crash=True))
    event=next(event for event in reversed(w.journal.read()) if event["event"]=="RUN_INTERRUPTED")
    monkeypatch.setattr(w,"_save",original_save)
    return w,event,w.base/event["payload"]["execution"]["report_dir"]

def test_recovery_accepts_exact_existing_fallback_and_resyncs_directory(repo,monkeypatch):
    w,event,report=_crashed_missing_fallback(repo,monkeypatch)
    w.recover()
    expected={name:(report/name).read_bytes() for name in event["payload"]["fallback_artifacts"]}
    from tools.atlas_agent import workflow as workflow_module
    original_sync=workflow_module.fsync_dir; synced=[]
    monkeypatch.setattr(workflow_module,"fsync_dir",lambda path: synced.append(path) or original_sync(path))
    recovered=w.recover()
    assert recovered["generations"]["1"]["status"]=="INTERRUPTED"
    assert all((report/name).read_bytes()==data for name,data in expected.items())
    assert synced.count(report)==len(expected)

def test_repeated_fallback_recovery_after_each_publication_is_idempotent(repo,monkeypatch):
    w,event,report=_crashed_missing_fallback(repo,monkeypatch)
    original=w._publish_missing_execution_file; publications=[]
    def publish_then_crash(path,data):
        was_missing=not path.exists(); original(path,data)
        if was_missing:
            publications.append(path.name)
            raise OSError("crash after fallback publication")
    monkeypatch.setattr(w,"_publish_missing_execution_file",publish_then_crash)
    for _ in event["payload"]["fallback_artifacts"]:
        with pytest.raises(OSError,match="crash after fallback publication"): w.recover()
    assert publications==event["payload"]["fallback_artifacts"]
    monkeypatch.setattr(w,"_publish_missing_execution_file",original)
    w.recover(); before={name:(report/name).read_bytes() for name in event["payload"]["fallback_artifacts"]}
    w.recover()
    assert {name:(report/name).read_bytes() for name in before}==before

@pytest.mark.parametrize("content",[b"{partial",b"foreign bytes\n"])
def test_recovery_rejects_corrupt_existing_fallback_bytes(repo,monkeypatch,content):
    w,event,report=_crashed_missing_fallback(repo,monkeypatch)
    path=report/"result.json"; path.write_bytes(content)
    with pytest.raises(WorkflowError,match="RECOVERY_FALLBACK_ARTIFACT_CONFLICT"):
        w.recover()
    assert path.read_bytes()==content

def test_recovery_rejects_owner_correct_fallback_with_foreign_reason(repo,monkeypatch):
    w,event,report=_crashed_missing_fallback(repo,monkeypatch)
    w.recover(); path=report/"result.json"; foreign=json.loads(path.read_text())
    foreign["error"]="foreign reason with canonical owner"
    path.write_text(json.dumps(foreign,sort_keys=True,indent=2)+"\n")
    before=path.read_bytes()
    with pytest.raises(WorkflowError,match="RECOVERY_FALLBACK_ARTIFACT_CONFLICT"):
        w.recover()
    assert path.read_bytes()==before

def test_recovery_does_not_reconstruct_unexplained_later_artifact_loss(repo):
    p,w=repo; accepted(w)
    with pytest.raises(WorkflowError,match="EXECUTOR_EXIT_7"): w.execute(1,FakeExecutor(exit_code=7))
    event=next(event for event in reversed(w.journal.read()) if event["event"]=="RUN_INTERRUPTED")
    assert "fallback_artifacts" not in event["payload"]
    report=w.base/event["payload"]["execution"]["report_dir"]
    (report/"stdout.log").unlink()
    with pytest.raises(RuntimeError,match="MISSING_EXECUTION_ARTIFACT"): w.recover()

def test_fake_timeout_is_explicit_and_interrupts(repo):
    p,w=repo; accepted(w); fake=FakeExecutor(timed_out=True,exit_code=-2)
    with pytest.raises(WorkflowError,match="EXECUTOR_TIMEOUT"): w.execute(1,fake)
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"
    execution=w._state()["generations"]["1"]["execution"]
    result=json.loads((w.base/execution["report_dir"]/"result.json").read_text())
    assert result["outcome"]=="timeout" and result["timed_out"] is True
def test_fake_exception_interrupts(repo):
    p,w=repo; accepted(w); fake=FakeExecutor(crash=True)
    with pytest.raises(WorkflowError,match="EXECUTOR_FAILURE"): w.execute(1,fake)
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"
def test_fail_before_launch_for_stale_state_and_repository(repo):
    p,w=repo; accepted(w); state=w._state_file(); data=json.loads(state.read_text()); data["generations"]["1"]["status"]="COMPLETED"; state.write_text(json.dumps(data)); fake=FakeExecutor()
    with pytest.raises(WorkflowError): w.execute(1,fake)
    assert fake.launched==0
    w.rebuild(); (p/"a").write_text("changed"); fake=FakeExecutor()
    with pytest.raises(WorkflowError): w.execute(1,fake)
    assert fake.launched==0
def test_execution_ids_unique_and_reports_associated(repo):
    p,w=repo; raw=accepted(w); fake=FakeExecutor(); w.execute(1,fake); execution=w._state()["generations"]["1"]["execution"]; assert execution["execution_id"]; assert (w.base/execution["report_dir"]/"result.json").is_file(); assert w._state()["generations"]["1"]["result"]["report_path"].endswith("result.json")
def test_concurrent_incompatible_execution_refused(repo):
    p,w=repo; accepted(w); w.start_run(1); fake=FakeExecutor()
    with pytest.raises(WorkflowError): w.execute(1,fake)
    assert fake.launched==0
def test_restart_after_launcher_crash_is_visible(repo):
    p,w=repo; accepted(w); metadata={"execution_id":"crashed","executor":"fake","started_at":"2026-01-01T00:00:00Z","pid":123,"report_dir":"reports/executions/crashed"}; w.start_run(1,execution=metadata); w2=Workflow(p)
    with pytest.raises((WorkflowError,RuntimeError)): w2.rebuild()
    assert w2._state()["generations"]["1"]["status"]=="RUNNING"
def test_codex_executor_configuration_is_explicit():
    from tools.atlas_agent.codex_executor import CodexExecutor
    info=CodexExecutor().info(); assert info["executor"]=="codex"; assert "exec" in info["capabilities"] or not info["available"]

def test_codex_heartbeats_continue_after_stdout_eof(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec,PreparedExecution
    executable=tmp_path/"close-stdout"
    executable.write_text("#!/bin/sh\nexec 1>&-\nsleep 0.08\n")
    executable.chmod(0o755)
    prompt_path=tmp_path/"prompt"; prompt_path.write_text("prompt")
    report_dir=tmp_path/"report"; events=[]
    envelope={"sandbox_mode":"read-only","approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":False}
    spec=ExecutionSpec(1,"0"*64,"implementation",prompt_path,tmp_path,"eof-heartbeat",report_dir,tmp_path)
    prepared=PreparedExecution(spec,"codex",(str(executable),),"codex/test",envelope)
    result=CodexExecutor(executable=str(executable),timeout_seconds=.3,heartbeat_seconds=.02,progress_callback=events.append).run_execution(prepared)
    assert result.exit_code==0 and result.timed_out is False
    assert any(event["kind"]=="heartbeat" for event in events)
    assert (report_dir/"stdout.log").read_bytes()==b""

def test_fake_result_has_permission_contract(repo):
    p,w=repo; accepted(w); w.execute(1,FakeExecutor()); execution=w._state()["generations"]["1"]["execution"]
    result=json.loads((w.base/execution["report_dir"]/"result.json").read_text())
    assert result["permission_envelope"] == {"sandbox_mode":"read-only","approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":False}
    assert result["permission_observation_status"] == "unavailable"
    assert result["permission_failures"] is None

def test_fake_explicit_permission_observation_is_preserved(repo):
    p,w=repo; accepted(w); failures=[{"source":"stderr","message":"sandbox denied write"}]
    w.execute(1,FakeExecutor(permission_observation_status="observed",permission_failures=failures)); execution=w._state()["generations"]["1"]["execution"]
    result=json.loads((w.base/execution["report_dir"]/"result.json").read_text())
    assert result["permission_observation_status"] == "observed" and result["permission_failures"] == failures

def test_codex_noninteractive_argv_and_mutation_guards(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec
    from pathlib import Path
    root=tmp_path; prompt_path=root/"prompt"; prompt_path.write_text("hello")
    spec=ExecutionSpec(1,"0"*64,"implementation",prompt_path,root,"e",root/"report",root)
    ex=CodexExecutor(executable="/bin/true")
    ex.info=lambda: {"available":True,"version":"codex-cli 0.149.1"}
    prepared=ex.prepare_execution(spec); argv=list(prepared.command)
    assert "--strict-config" in argv and "--ignore-rules" in argv
    assert 'approval_policy="never"' in argv and 'approvals_reviewer="user"' in argv
    assert argv[argv.index("--sandbox")+1] == "read-only"
    for kwargs in ({"approval_policy":"on-request"},{"approvals_reviewer":"auto_review"},{"ignore_rules":False},{"strict_config":False}):
        bad=CodexExecutor(executable="/bin/true",**kwargs)
        with pytest.raises(Exception,match="NONINTERACTIVE_PERMISSION_POLICY_REQUIRED"):
            bad.prepare_execution(spec)

def test_workspace_write_network_is_explicit(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    ex=CodexExecutor(executable="/bin/true",sandbox="workspace-write",network_access=False)
    ex.info=lambda: {"available":True,"version":"codex-cli 0.149.1"}
    from pathlib import Path
    root=tmp_path; path=root/"p"; path.write_text("x")
    from tools.atlas_agent.executor import ExecutionSpec
    argv=list(ex.prepare_execution(ExecutionSpec(1,"0"*64,"implementation",path,root,"e",root/"r",root)).command)
    assert "sandbox_workspace_write.network_access=false" in argv

def test_permission_refusal_observation_is_not_inferred_from_exit_zero():
    from tools.atlas_agent.codex_executor import CodexExecutor
    status, failures=CodexExecutor._permission_observations(b'{"type":"turn.completed"}\n',b"")
    assert status == "unavailable" and failures is None
    status, failures=CodexExecutor._permission_observations(b"",b"sandbox denied write outside workspace\n")
    assert status == "observed" and failures

def test_wrong_inputs_do_not_discover_or_launch_codex(repo, monkeypatch):
    p,w=repo; accepted(w)
    from tools.atlas_agent.codex_executor import CodexExecutor
    calls=[]
    monkeypatch.setattr(CodexExecutor,"info",lambda self: calls.append("info") or {"available":True,"version":"x"})
    monkeypatch.setattr("subprocess.Popen",lambda *a,**k: calls.append("popen"))
    ex=CodexExecutor(executable="/bin/true")
    with pytest.raises(WorkflowError): w.execute(2,ex)
    (w.base/"accepted"/next((w.base/"accepted").iterdir()).name).write_bytes(b"corrupt")
    with pytest.raises(Exception): w.execute(1,ex)
    assert calls == []

@pytest.mark.parametrize("kind",["wrong_generation","wrong_hash","wrong_action"])
def test_fail_before_launch_matrix_has_no_discovery_or_process(repo, monkeypatch, kind):
    p,w=repo; accepted(w)
    from tools.atlas_agent.codex_executor import CodexExecutor
    calls=[]; monkeypatch.setattr(CodexExecutor,"info",lambda self: calls.append("info") or {"available":True,"version":"x"}); monkeypatch.setattr("subprocess.Popen",lambda *a,**k: calls.append("popen"))
    if kind=="wrong_generation": generation=2
    else:
        generation=1; state=json.loads(w._state_file().read_text())
        if kind=="wrong_hash": state["generations"]["1"]["prompt_sha256"]="0"*64
        else: state["generations"]["1"]["action"]="patch_review"
        w._state_file().write_text(json.dumps(state))
    with pytest.raises(Exception): w.execute(generation,CodexExecutor(executable="/bin/true"))
    assert calls==[]

def prompt_generation(w,g,parent,body="next"):
    raw=(f"+++\nschema = \"atlas-agent-prompt/1\"\ngeneration = {g}\nparent = {parent}\ncheckpoint = \"W21-{g}\"\naction = \"implementation\"\nexpected_head = \"{git(w.root,'rev-parse','HEAD')}\"\nsession_mode = \"fresh\"\n+++\n{body}\n").encode()
    (w.base/"inbox"/f"prompt-{g}.txt").write_bytes(raw); return raw

def test_execution_id_collision_is_refused_without_overwrite(repo, monkeypatch):
    p,w=repo; accepted(w); monkeypatch.setattr("tools.atlas_agent.workflow.new_execution_id",lambda:"same-id")
    w.execute(1,FakeExecutor()); first=w._state()["generations"]["1"]["execution"]; report=w.base/first["report_dir"]; before=(report/"result.json").read_bytes()
    prompt_generation(w,2,1); w.ingest(); second=FakeExecutor()
    with pytest.raises(WorkflowError,match="COLLISION"): w.execute(2,second)
    assert second.launched==0 and (report/"result.json").read_bytes()==before

def test_foreign_executor_result_interrupts_and_never_completes(repo):
    p,w=repo; accepted(w)
    class Foreign(FakeExecutor):
        def run_execution(self,prepared):
            result=super().run_execution(prepared)
            from dataclasses import replace
            return replace(result,execution_id="foreign-id")
    with pytest.raises(WorkflowError,match="EXECUTOR_FAILURE.*RESULT_EXECUTION_MISMATCH"):
        w.execute(1,Foreign())
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"

def test_real_concurrent_same_generation_has_one_owner(repo):
    p,w=repo; accepted(w); executors=[FakeExecutor(delay=.15),FakeExecutor(delay=.15)]; errors=[]
    def run(ex):
        try: Workflow(p).execute(1,ex)
        except Exception as error: errors.append(error)
    threads=[threading.Thread(target=run,args=(ex,)) for ex in executors]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sum(ex.launched for ex in executors)==1
    assert w._state()["generations"]["1"]["status"]=="COMPLETED"
    assert len(list((w.base/"reports"/"executions").glob("*/execution.json")))==1

def test_prepare_is_pure_and_discovery_is_post_start(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec
    root=tmp_path; prompt_path=root/"prompt"; prompt_path.write_text("hello")
    ex=CodexExecutor(executable="/bin/true"); ex.info=lambda: (_ for _ in ()).throw(AssertionError("discovery before start"))
    spec=ExecutionSpec(1,"0"*64,"implementation",prompt_path,root,"e",root/"report",root)
    prepared=ex.prepare_execution(spec)
    assert prepared.version=="unresolved" and not (root/"report").exists()

def test_doctor_validates_report_owners_after_completion(repo):
    p,w=repo; accepted(w); w.execute(1,FakeExecutor()); assert subprocess.run([sys.executable,"-m","tools.atlas_agent","doctor"],cwd=p,env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1])),capture_output=True).returncode==0
    execution=w._state()["generations"]["1"]["execution"]; path=w.base/execution["report_dir"]/"execution.json"; data=json.loads(path.read_text()); data["generation"]=99; path.write_text(json.dumps(data))
    assert subprocess.run([sys.executable,"-m","tools.atlas_agent","doctor"],cwd=p,env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1])),capture_output=True).returncode!=0
    data["generation"]=1; path.write_text(json.dumps(data)); result=w.base/execution["report_dir"]/("result.json"); r=json.loads(result.read_text()); r["execution_id"]="foreign"; result.write_text(json.dumps(r))
    assert subprocess.run([sys.executable,"-m","tools.atlas_agent","doctor"],cwd=p,env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1])),capture_output=True).returncode!=0

def test_doctor_rejects_permission_artifact_forgery_against_canonical_owner(repo):
    p,w=repo; accepted(w); w.execute(1,FakeExecutor()); execution=w._state()["generations"]["1"]["execution"]; report=w.base/execution["report_dir"]
    execution_path=report/"execution.json"; result_path=report/"result.json"
    original_execution=execution_path.read_bytes(); original_result=result_path.read_bytes()
    def doctor_fails():
        return subprocess.run([sys.executable,"-m","tools.atlas_agent","doctor"],cwd=p,env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1])),capture_output=True).returncode != 0
    data=json.loads(execution_path.read_text()); data["permission_envelope"]["sandbox_mode"]="danger-full-access"; execution_path.write_text(json.dumps(data)); assert doctor_fails()
    execution_path.write_bytes(original_execution)
    data=json.loads(result_path.read_text()); data["permission_envelope"]["approval_policy"]="on-request"; result_path.write_text(json.dumps(data)); assert doctor_fails()
    result_path.write_bytes(original_result)
    for path in (execution_path,result_path):
        data=json.loads(path.read_text()); data["permission_envelope"]["sandbox_mode"]="danger-full-access"; path.write_text(json.dumps(data))
    assert doctor_fails()
    execution_path.write_bytes(original_execution); result_path.write_bytes(original_result)
    data=json.loads(execution_path.read_text()); data["permission_envelope"]["magic"]=True; execution_path.write_text(json.dumps(data)); assert doctor_fails()
    execution_path.write_bytes(original_execution)
    data=json.loads(result_path.read_text()); del data["permission_envelope"]["network_access"]; result_path.write_text(json.dumps(data)); assert doctor_fails()
def test_true_baseline_w1_runtime_is_read_compatibly(tmp_path):
    import io,tarfile
    source=Path(__file__).parents[1]; archive_root=tmp_path/"baseline-source"; archive_root.mkdir()
    blob=subprocess.check_output(["git","archive","cda0fd15e5982ac4516847409c78656215d61610"],cwd=source)
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:") as archive: archive.extractall(archive_root)
    repo_path=tmp_path/"baseline-repo"; repo_path.mkdir(); subprocess.run(["git","init","-q"],cwd=repo_path,check=True); subprocess.run(["git","config","user.email","t@e"],cwd=repo_path,check=True); subprocess.run(["git","config","user.name","t"],cwd=repo_path,check=True)
    (repo_path/"a").write_text("a"); (repo_path/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n'); subprocess.run(["git","add","."],cwd=repo_path,check=True); subprocess.run(["git","commit","-qm","baseline"],cwd=repo_path,check=True)
    env=dict(os.environ,PYTHONPATH=str(archive_root)); subprocess.run([sys.executable,"-m","tools.atlas_agent","init"],cwd=repo_path,env=env,check=True,capture_output=True)
    runtime=Path(subprocess.check_output(["git","rev-parse","--git-path","atlas-agent"],cwd=repo_path,text=True).strip()); runtime=(repo_path/runtime).resolve() if not runtime.is_absolute() else runtime.resolve()
    baseline_prompt=(f'''+++
schema = "atlas-agent-prompt/1"
generation = 1
parent = "genesis"
checkpoint = "W1-BASELINE"
action = "implementation"
expected_head = "{git(repo_path, "rev-parse", "HEAD")}"
session_mode = "fresh"
+++
baseline lifecycle
''').encode()
    (runtime/"inbox"/"baseline.txt").write_bytes(baseline_prompt)
    for command in (["ingest"],["start-run","1"],["complete-run","1","--result",json.dumps({"generation":1,"prompt_sha256":sha(baseline_prompt),"action":"implementation","outcome":"done","classification":"manual"})]):
        subprocess.run([sys.executable,"-m","tools.atlas_agent",*command],cwd=repo_path,env=env,check=True,capture_output=True)
    state=runtime/"state.json"; journal=runtime/"events.jsonl"
    before=state.read_bytes(); state_hash=hashlib.sha256(before).hexdigest(); state_mtime=state.stat().st_mtime_ns
    journal_before=journal.read_bytes(); journal_hash=hashlib.sha256(journal_before).hexdigest(); journal_mtime=journal.stat().st_mtime_ns
    projected=json.loads(before)
    assert projected["generations"]["1"]["status"]=="COMPLETED"
    assert "execution" not in projected["generations"]["1"]
    candidate_env=dict(os.environ,PYTHONPATH=str(source)); checked=subprocess.run([sys.executable,"-m","tools.atlas_agent","doctor"],cwd=repo_path,env=candidate_env,capture_output=True,text=True)
    assert checked.returncode==0, checked.stderr
    assert state.read_bytes()==before and hashlib.sha256(state.read_bytes()).hexdigest()==state_hash and state.stat().st_mtime_ns==state_mtime
    assert journal.read_bytes()==journal_before and hashlib.sha256(journal.read_bytes()).hexdigest()==journal_hash and journal.stat().st_mtime_ns==journal_mtime
    assert json.loads(state.read_bytes())["generations"]["1"]["status"]=="COMPLETED"
    assert "execution" not in json.loads(state.read_bytes())["generations"]["1"]
