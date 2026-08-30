import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import pytest
from tools.atlas_agent.workflow import Workflow,WorkflowError,replay_journal
from tools.atlas_agent.journal import canonical,_hash_event
from tools.atlas_agent.prompt import parse_prompt,PromptError
from tools.atlas_agent.repository import witness
from tools.atlas_agent.executor import FakeExecutor

def sh(p,*a): return subprocess.check_output(["git",*a],cwd=p,text=True).strip()
@pytest.fixture
def repo(tmp_path):
    p=tmp_path/"r"; p.mkdir(); sh(p,"init","-q"); sh(p,"config","user.email","t@e"); sh(p,"config","user.name","t")
    (p/"a").write_text("a"); (p/".gitignore").write_text(""); (p/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n'); sh(p,"add","."); sh(p,"commit","-qm","g"); w=Workflow(p); w.init(); return p,w
def prompt(w,g=1,parent="genesis",action="implementation",body="body",schema="atlas-agent-prompt/1"):
    parent_line=f'parent = "{parent}"' if parent=="genesis" else f"parent = {parent}"
    network_line = "network_access = false\n" if schema == "atlas-agent-prompt/2" else ""
    raw=f'''+++\nschema = "{schema}"\ngeneration = {g}\n{parent_line}\ncheckpoint = "W1"\naction = "{action}"\nexpected_head = "{sh(w.root,"rev-parse","HEAD")}"\nsession_mode = "fresh"\n{network_line}+++\n{body}\n'''.encode(); (w.base/"inbox"/f"user-{g}-{body}").write_bytes(raw); return raw
def digest(x): return hashlib.sha256(x).hexdigest()
def running(w): raw=prompt(w); w.ingest(); w.start_run(1); return raw
def test_state_and_spool_corruption_fail_closed(repo):
    p,w=repo; prompt(w); w.ingest(); st=json.loads((w.base/"state.json").read_text()); st["generations"]["1"]["witness"]["head"]="0"*40; (w.base/"state.json").write_text(json.dumps(st))
    with pytest.raises(WorkflowError): w.start_run(1)
    w.rebuild(); next((w.base/"accepted").glob("*.txt")).write_bytes(b"bad")
    with pytest.raises((WorkflowError,RuntimeError)): w.rebuild()
def test_result_generation_hash_action_mismatch(repo):
    p,w=repo; raw=running(w)
    for key,val in [("generation",2),("prompt_sha256","0"*64),("action","patch_review")]:
        r={"generation":1,"prompt_sha256":digest(raw),"action":"implementation"}; r[key]=val
        with pytest.raises(WorkflowError): w.complete_run(1,r)
def test_implementation_can_complete_with_new_file_and_binds_content(repo):
    p,w=repo; raw=running(w); (p/"new-source.py").write_text("VALUE = 1\n")
    w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
    state=w._state(); completed=state["generations"]["1"]
    assert completed["status"]=="COMPLETED"
    entry=state["latest_repository_witness"]["unexpected_untracked"][0]
    assert bytes.fromhex(entry["path"]).decode()=="new-source.py"
    assert entry["content_sha256"]==hashlib.sha256(b"file\0VALUE = 1\n").hexdigest()

def test_modern_bwrap_provenance_survives_full_workflow_and_cannot_be_removed(repo):
    p,w=repo; raw=prompt(w); w.ingest()
    descriptor={"schema":"atlas-bwrap/1","provider":"atlas","backend":"bubblewrap",
                "filesystem_mode":"workspace-write","filesystem_enforcement":"atlas-bwrap",
                "process_enforcement":"atlas-bwrap","network_enforcement":"codex",
                "requested_network_access":False,"resolved_network_access":False,
                "user_namespace":"bwrap-default","pid_namespace":True,"ipc_namespace":True,
                "mount_roles":[],"temporary_storage":{"tmp":"private-tmpfs","shm":"private-tmpfs","var_tmp":"private-disk-scratch"},
                "bwrap":"bwrap","bwrap_version":"0.12","codex_executable":"/opt/codex",
                "codex_version":"0.150.1","scratch_backing_class":"disk",
                "exec_server_transport":"CODEX_EXEC_SERVER_URL/websocket-loopback",
                "inner_codex_sandbox":"workspace-write","inner_codex_network":"restricted"}
    class ModernFake(FakeExecutor):
        def sandbox_descriptor(self): return dict(descriptor)
    w.execute(1,ModernFake(permission_envelope={"sandbox_mode":"workspace-write","approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":False}))
    path=w.journal.path; rows=[json.loads(x) for x in path.read_text().splitlines()]
    for row in rows:
        if isinstance(row["payload"].get("execution"),dict):
            row["payload"]["execution"].pop("sandbox",None)
    _append_rehashed(path,rows)
    with pytest.raises(Exception,match="sandbox provenance missing"):
        w.journal.read()

@pytest.mark.parametrize("corruption,expected", [
    ("descriptor", "sandbox provenance missing"),
    ("action", "sandbox action mismatch"),
    ("permission", "sandbox permission mismatch"),
    ("filesystem_enforcement", "sandbox filesystem enforcement mismatch"),
    ("process_enforcement", "sandbox process enforcement mismatch"),
    ("network_enforcement", "sandbox network enforcement mismatch"),
    ("network_state", "sandbox network mismatch"),
])
def test_rehashed_modern_bwrap_semantic_corruption_fails_closed(repo, corruption, expected):
    p,w=repo; prompt(w); w.ingest()
    descriptor={"schema":"atlas-bwrap/1","provider":"atlas","backend":"bubblewrap",
                "filesystem_mode":"workspace-write","filesystem_enforcement":"atlas-bwrap",
                "process_enforcement":"atlas-bwrap","network_enforcement":"codex",
                "requested_network_access":False,"resolved_network_access":False,
                "user_namespace":"bwrap-default","pid_namespace":True,"ipc_namespace":True,
                "mount_roles":[],"temporary_storage":{"tmp":"private-tmpfs","shm":"private-tmpfs","var_tmp":"private-disk-scratch"},
                "bwrap":"bwrap","bwrap_version":"0.12","codex_executable":"/opt/codex",
                "codex_version":"0.150.1","scratch_backing_class":"disk",
                "exec_server_transport":"CODEX_EXEC_SERVER_URL/websocket-loopback",
                "inner_codex_sandbox":"workspace-write","inner_codex_network":"restricted"}
    class ModernFake(FakeExecutor):
        def sandbox_descriptor(self): return dict(descriptor)
    w.execute(1,ModernFake(permission_envelope={"sandbox_mode":"workspace-write","approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":False}))
    rows=[json.loads(x) for x in w.journal.path.read_text().splitlines()]
    for row in rows:
        execution=row["payload"].get("execution")
        if not isinstance(execution,dict) or execution.get("execution_backend_schema") != "atlas-bwrap-execution/1": continue
        if corruption == "descriptor": execution.pop("sandbox",None)
        elif corruption == "action":
            execution["sandbox"]["filesystem_mode"]="read-only"
            execution["sandbox"]["inner_codex_sandbox"]="read-only"
            execution["permission_envelope"]["sandbox_mode"]="read-only"
        elif corruption == "permission": execution["permission_envelope"]["sandbox_mode"]="read-only"
        elif corruption in {"filesystem_enforcement","process_enforcement","network_enforcement"}:
            execution["sandbox"][corruption]="wrong"
        elif corruption == "network_state": execution["sandbox"]["requested_network_access"]=True
    _append_rehashed(w.journal.path,rows)
    with pytest.raises(Exception,match=expected):
        w.journal.read()


def test_terminal_descriptor_must_equal_durable_start_descriptor(repo):
    p,w=repo; prompt(w); w.ingest()
    descriptor={"schema":"atlas-bwrap/1","provider":"atlas","backend":"bubblewrap",
                "filesystem_mode":"workspace-write","filesystem_enforcement":"atlas-bwrap",
                "process_enforcement":"atlas-bwrap","network_enforcement":"codex",
                "requested_network_access":False,"resolved_network_access":False,
                "user_namespace":"bwrap-default","pid_namespace":True,"ipc_namespace":True,
                "mount_roles":[],"temporary_storage":{"tmp":"private-tmpfs","shm":"private-tmpfs","var_tmp":"private-disk-scratch"},
                "bwrap":"bwrap","bwrap_version":"0.12","codex_executable":"/opt/codex",
                "codex_version":"0.150.1","scratch_backing_class":"disk",
                "exec_server_transport":"CODEX_EXEC_SERVER_URL/websocket-loopback",
                "inner_codex_sandbox":"workspace-write","inner_codex_network":"restricted"}
    class ModernFake(FakeExecutor):
        def sandbox_descriptor(self): return dict(descriptor)
    w.execute(1,ModernFake(permission_envelope={"sandbox_mode":"workspace-write","approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":False}))
    rows=[json.loads(x) for x in w.journal.path.read_text().splitlines()]
    terminal=next(row for row in rows if row["event"] == "RUN_COMPLETED")
    terminal["payload"]["execution"]["sandbox"]["bwrap_version"]="0.13"
    _append_rehashed(w.journal.path,rows)
    with pytest.raises(Exception,match="TERMINAL_EXECUTION_MISMATCH"):
        w._validate_terminal_transition("RUN_COMPLETED", terminal["payload"],
                                        replay_journal(rows[:rows.index(terminal)]))
def test_patch_review_detects_witnessed_new_file_content_change(repo):
    p,w=repo; raw=running(w); new=p/"new-source.py"; new.write_text("reviewed\n")
    w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
    review=prompt(w,2,parent=1,action="patch_review"); w.ingest(); w.start_run(2); new.write_text("changed\n")
    with pytest.raises(WorkflowError): w.complete_run(2,{"generation":2,"prompt_sha256":digest(review),"action":"patch_review"})
    assert w._state()["generations"]["2"]["status"]=="INTERRUPTED"
def test_start_witness_guard(repo):
    p,w=repo; prompt(w); w.ingest(); (p/"a").write_text("changed")
    with pytest.raises(WorkflowError): w.start_run(1)
def test_journal_schema_rejected_even_rehashed(repo):
    p,w=repo; path=w.base/"events.jsonl"; rows=[json.loads(x) for x in path.read_text().splitlines()]; rows[0]["schema"]="bogus"; rows[0]["event_sha256"]=_hash_event(rows[0]); path.write_text("\n".join(canonical(x) for x in rows)+"\n")
    with pytest.raises(Exception): w.journal.read()
def test_journal_hash_rejected(repo):
    p,w=repo; path=w.base/"events.jsonl"; rows=[json.loads(x) for x in path.read_text().splitlines()]; rows[0]["event_sha256"]="0"*64; path.write_text("\n".join(canonical(x) for x in rows)+"\n")
    with pytest.raises(Exception): w.journal.read()
def test_recovery_hash_and_idempotence(repo):
    p,w=repo; prompt(w); w.ingest()
    def crash(point,data):
        if point=="prepared": raise RuntimeError
    with pytest.raises(RuntimeError): w.start_run(1,hook=crash)
    src=next((w.base/"accepted").glob("*.txt")); src.write_bytes(b"wrong")
    with pytest.raises(WorkflowError): Workflow(p).recover()
def test_recovery_destination_hash_both_present_and_both_absent(repo):
    p,w=repo; raw=prompt(w); w.ingest()
    def renamed(point,data):
        if point=="renamed": raise RuntimeError
    with pytest.raises(RuntimeError): w.start_run(1,hook=renamed)
    dst=next((w.base/"running/implementation").glob("*.txt")); dst.write_bytes(b"wrong")
    with pytest.raises(WorkflowError): Workflow(p).recover()
def test_recovery_ambiguous_both_present(repo):
    p,w=repo; prompt(w); w.ingest()
    def prepared(point,data):
        if point=="prepared": raise RuntimeError
    with pytest.raises(RuntimeError): w.start_run(1,hook=prepared)
    row=w.journal.read()[-1]["payload"]; src=w.base/row["source"]; dst=w.base/row["destination"]; dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(src.read_bytes())
    with pytest.raises(WorkflowError): Workflow(p).recover()
def test_recovery_missing_both(repo):
    p,w=repo; prompt(w); w.ingest()
    def prepared(point,data):
        if point=="prepared": raise RuntimeError
    with pytest.raises(RuntimeError): w.start_run(1,hook=prepared)
    row=w.journal.read()[-1]["payload"]; (w.base/row["source"]).unlink()
    with pytest.raises(WorkflowError): Workflow(p).recover()
def test_linked_worktree_runtime_path(tmp_path):
    p=tmp_path/"r"; p.mkdir(); sh(p,"init","-q"); sh(p,"config","user.email","t@e"); sh(p,"config","user.name","t"); (p/"a").write_text("a"); sh(p,"add","a"); sh(p,"commit","-qm","g"); q=tmp_path/"linked"; subprocess.check_call(["git","worktree","add","-q",str(q)],cwd=p); from tools.atlas_agent.repository import runtime_path; assert runtime_path(q)==(q/sh(q,"rev-parse","--git-path","atlas-agent")).resolve()
def test_dirty_before_start_then_content_change_interrupts(repo):
    p,w=repo; raw=running(w); (p/"a").write_text("dirty-one"); result={"generation":1,"prompt_sha256":digest(raw),"action":"implementation"}; w.complete_run(1,result)
    raw2=prompt(w,2,parent=1,action="patch_review"); w.ingest(); w.start_run(2); (p/"a").write_text("dirty-two")
    with pytest.raises(WorkflowError): w.complete_run(2,{"generation":2,"prompt_sha256":digest(raw2),"action":"patch_review"})
    assert w._state()["generations"]["2"]["status"]=="INTERRUPTED"
def test_intent_to_add_changes_index_witness_and_interrupts(repo):
    p,w=repo; raw=running(w); from tools.atlas_agent.repository import witness; before=witness(p,w.allowed); (p/"new.txt").write_text("x"); subprocess.check_call(["git","add","-N","new.txt"],cwd=p); after=witness(p,w.allowed); assert before["index_semantic_sha256"]!=after["index_semantic_sha256"]
    with pytest.raises(WorkflowError): w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"
def test_first_ingest_uses_genesis_witness(repo):
    p,w=repo; (p/"a").write_text("changed"); prompt(w)
    w.ingest(); assert not list((w.base/"accepted").glob("*.txt")); assert json.loads(next((w.base/"rejected").glob("*.reason.json")).read_text())["code"]=="REPOSITORY_WITNESS_MISMATCH"
def _append_rehashed(path, rows):
    previous="0"*64
    for n,row in enumerate(rows,1):
        row["seq"]=n; row["previous_event_sha256"]=previous; row["event_sha256"]=_hash_event(row); previous=row["event_sha256"]
    path.write_text("\n".join(canonical(row) for row in rows)+"\n")
def test_terminal_requires_exact_prepare(repo):
    p,w=repo; path=w.base/"events.jsonl"; rows=[json.loads(x) for x in path.read_text().splitlines()]; rows.append({"schema":"atlas-agent-workflow/1","seq":0,"timestamp":"2026-01-01T00:00:00Z","event":"RUN_STARTED","payload":{"transaction_id":"fake","source":"accepted/x","destination":"running/implementation/x","generation":1,"prompt_sha256":"0"*64,"action":"implementation"},"previous_event_sha256":"","event_sha256":""}); _append_rehashed(path,rows)
    with pytest.raises(WorkflowError,match="PREPARE"): replay_journal(w.journal.read())
def test_wrong_terminal_type_rejected(repo):
    p,w=repo; raw=prompt(w); w.ingest(); path=w.base/"events.jsonl"; rows=[json.loads(x) for x in path.read_text().splitlines()]; prep=rows[-2]; payload=dict(prep["payload"]); payload["logical_event"]="RUN_STARTED"; rows.append({"schema":"atlas-agent-workflow/1","seq":0,"timestamp":"2026-01-01T00:00:00Z","event":"RUN_COMPLETED","payload":{k:v for k,v in payload.items() if k!="logical_event"},"previous_event_sha256":"","event_sha256":""}); _append_rehashed(path,rows)
    with pytest.raises(Exception): replay_journal(w.journal.read())
def test_bad_parent_rejected_before_accept_and_next_parent_works(repo):
    p,w=repo; prompt(w,1); w.ingest(); prompt(w,2,parent=1,body="two"); w.ingest(); prompt(w,3,parent=1,body="bad"); w.ingest(); assert "3" not in w._state()["generations"]; assert len(list((w.base/"accepted").glob("*.txt")))==2; assert replay_journal(w.journal.read())["generations"].keys()=={"1","2"}; prompt(w,3,parent=2,body="three"); w.ingest(); assert "3" in w._state()["generations"]
def test_spool_canonical_name_archive_and_report_orphans_fail(repo):
    p,w=repo; prompt(w); w.ingest(); good=next((w.base/"accepted").glob("*.txt")); good.rename(good.with_name("g000001-"+"0"*64+".txt"))
    with pytest.raises(RuntimeError): w.rebuild()
def test_archive_and_report_orphans_fail(repo):
    p,w=repo; prompt(w); w.ingest(); (w.base/"prompts"/"orphan.txt").write_text("x")
    with pytest.raises(RuntimeError): w.rebuild()
def test_report_orphan_fail(repo):
    p,w=repo; prompt(w); w.ingest(); (w.base/"reports"/"orphan.json").write_text("{}")
    with pytest.raises(RuntimeError): w.rebuild()
def test_timestamp_and_witness_payload_strict(repo):
    p,w=repo; path=w.base/"events.jsonl"; rows=[json.loads(x) for x in path.read_text().splitlines()]; rows[0]["timestamp"]="2026-99-99T99:99:99Z"; _append_rehashed(path,rows)
    with pytest.raises(Exception): w.journal.read()
    w=Workflow(p); path=w.base/"events.jsonl"; rows=[json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
def test_malformed_witness_payload_rejected(repo):
    p,w=repo; path=w.base/"events.jsonl"; rows=[json.loads(x) for x in path.read_text().splitlines()]; rows[0]["payload"]["witness"]={"head":"bad"}; _append_rehashed(path,rows)
    with pytest.raises(Exception): w.journal.read()
def test_recover_true_noop_preserves_state(repo):
    p,w=repo; state=w._state_file(); before=state.read_bytes(); stat=state.stat().st_mtime_ns; w.recover(); assert state.read_bytes()==before; assert state.stat().st_mtime_ns==stat
def test_doctor_current_repository_policy(repo):
    p,w=repo; raw=prompt(w,action="patch_review"); w.ingest(); w.start_run(1); (p/"a").write_text("changed")
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1])); result=subprocess.run([sys.executable,"-m","tools.atlas_agent","doctor"],cwd=p,env=env,text=True,capture_output=True); assert result.returncode!=0 and "REPOSITORY_WITNESS" in result.stderr
@pytest.mark.parametrize("config",['schema = "atlas-agent-project/1"\nallowed_untracked = ["../evil"]\n','schema = "atlas-agent-project/1"\nallowed_untracked = ["/tmp/evil"]\n','schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/../x"]\n','schema = "bogus"\nallowed_untracked = []\n'])
def test_config_paths_and_schema_closed(repo,config):
    p,_=repo; (p/"atlas-agent.toml").write_text(config)
    with pytest.raises(WorkflowError): Workflow(p)
def test_prompt_exact_delimiter_and_multi_inbox_order(repo):
    p,w=repo; raw2=prompt(w,2,parent=1,body="two"); raw1=prompt(w,1,body="one"); w.ingest(); assert [x["generation"] for x in w._state()["generations"].values()]==[1,2]
    bad=b"+++evil\nschema = \"atlas-agent-prompt/1\"\n";
    with pytest.raises(PromptError): parse_prompt(bad)
@pytest.mark.parametrize("action",["patch_review","state_audit","checkpoint"])
def test_read_only_action_policies(repo,action):
    p,w=repo; raw=prompt(w,action=action); w.ingest(); w.start_run(1); (p/"a").write_text("changed")
    with pytest.raises(WorkflowError): w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":action})
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"
def test_staged_and_head_changes_interrupt_implementation(repo):
    p,w=repo; raw=running(w); (p/"a").write_text("staged"); sh(p,"add","a")
    with pytest.raises(WorkflowError): w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
def test_head_change_interrupts_implementation(repo):
    p,w=repo; raw=running(w); (p/"a").write_text("head-change"); sh(p,"add","a"); sh(p,"commit","-qm","changed")
    with pytest.raises(WorkflowError): w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
def test_lock_blocks_and_recovers_after_kill(repo):
    p,w=repo; code="from tools.atlas_agent.spool import lock; import time; open('ready','w').close();\nwith lock(__import__('pathlib').Path(__import__('sys').argv[1])): time.sleep(.5)"; ready=p/"ready"; env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1])); proc=subprocess.Popen([sys.executable,"-c",code,str(w.base/"lock")],cwd=p,env=env); deadline=time.time()+2
    while not ready.exists() and time.time()<deadline: time.sleep(.01)
    assert ready.exists(); started=time.monotonic()
    from tools.atlas_agent.spool import lock
    with lock(w.base/"lock"): pass
    assert time.monotonic()-started>=.35; proc.wait(timeout=2); proc.kill() if proc.poll() is None else None
    proc2=subprocess.Popen([sys.executable,"-c",code,str(w.base/"lock")],cwd=p,env=env); time.sleep(.1); proc2.kill(); proc2.wait(); started=time.monotonic()
    with lock(w.base/"lock"): pass
    assert time.monotonic()-started<.4

def checkpoint_ready(repo):
    p,w=repo; raw=running(w); (p/"a").write_text("reviewed tracked\n"); (p/"reviewed-new.txt").write_text("reviewed new\n")
    w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
    checkpoint_prompt=prompt(w,2,parent=1,action="checkpoint"); w.ingest()
    assert w._state()["generations"]["2"]["status"]=="ACCEPTED"
    return p,w,checkpoint_prompt

def test_checkpoint_hooks_cannot_alter_committed_tree(repo):
    p,w,_=checkpoint_ready(repo); corpus=p/"corpus_miner"; corpus.mkdir(); (corpus/"excluded.txt").write_text("excluded\n")
    hook=p/".git/hooks/pre-commit"; hook.write_text("#!/bin/sh\nprintf 'hooked\\n' > a\nprintf 'injected\\n' > hook-injected.txt\ngit add a hook-injected.txt corpus_miner/excluded.txt\n")
    hook.chmod(0o755); parent=sh(p,"rev-parse","HEAD")
    before=witness(p,w.allowed)
    with pytest.raises(WorkflowError,match="CHECKPOINT_REPOSITORY_HOOKS_PRESENT"): w.checkpoint(2,"reviewed checkpoint")
    assert sh(p,"rev-parse","HEAD")==parent
    assert witness(p,w.allowed)==before
    assert not (p/"hook-injected.txt").exists()
    assert (corpus/"excluded.txt").read_text()=="excluded\n"
    assert sh(p,"ls-files","--","corpus_miner/excluded.txt")==""

def test_checkpoint_recovery_finalizes_exact_commit_after_head_advance(repo):
    p,w,_=checkpoint_ready(repo); parent=sh(p,"rev-parse","HEAD")
    def crash(point,data):
        if point=="committed": raise RuntimeError("crash after commit")
    with pytest.raises(RuntimeError,match="crash after commit"): w.checkpoint(2,"recoverable checkpoint",hook=crash)
    commit=sh(p,"rev-parse","HEAD"); assert commit!=parent
    assert w._state()["generations"]["2"]["status"]=="ACCEPTED"
    recovered=Workflow(p).recover()
    assert recovered["generations"]["2"]["status"]=="COMPLETED"
    assert recovered["generations"]["2"]["result"]["commit_sha"]==commit
    assert sh(p,"rev-parse",f"{commit}^")==parent
    assert sh(p,"show",f"{commit}:a")=="reviewed tracked"
    assert sh(p,"show",f"{commit}:reviewed-new.txt")=="reviewed new"
    assert sh(p,"diff-tree","--no-commit-id","--name-only","-r",commit).splitlines()==["a","reviewed-new.txt"]
    assert not recovered.get("outstanding_checkpoints")

def test_checkpoint_rechecks_boundary_after_post_commit_callback(repo):
    p,w,_=checkpoint_ready(repo)
    def mutate(point,data):
        if point=="committed": (p/"a").write_text("mutated after boundary\n")
    with pytest.raises(WorkflowError,match="CHECKPOINT_RECOVERY_REQUIRED"):
        w.checkpoint(2,"must recheck boundary",hook=mutate)
    assert w._state()["generations"]["2"]["status"]=="ACCEPTED"


def test_checkpoint_rechecks_recreated_patch_owned_tombstone_after_ignore_commit(repo):
    p,w=repo
    raw=running(w)
    owned=p/"owned.txt"
    owned.write_text("owned\n")
    w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
    assert b"owned.txt".hex() in w._state()["patch_owned_untracked"]
    raw2=prompt(w,g=2,parent=1); w.ingest(); w.start_run(2)
    (p/".gitignore").write_text("owned.txt\n")
    owned.unlink()
    w.complete_run(2,{"generation":2,"prompt_sha256":digest(raw2),"action":"implementation"})
    prompt(w,g=3,parent=2,action="checkpoint"); w.ingest()

    def recreate_after_head(point,data):
        if point=="committed": owned.write_text("recreated\n")

    with pytest.raises(WorkflowError,match="CHECKPOINT_RECOVERY_REQUIRED"):
        w.checkpoint(3,"ignore owned tombstone",hook=recreate_after_head)
    assert w._state()["generations"]["3"]["status"]=="ACCEPTED"
    assert w._state()["patch_owned_untracked"] == [b"owned.txt".hex()]


def test_checkpoint_recovery_aborts_when_commit_did_not_happen(repo):
    p,w,_=checkpoint_ready(repo); parent=sh(p,"rev-parse","HEAD")
    def crash(point,data):
        if point=="intent": raise RuntimeError("crash before commit")
    with pytest.raises(RuntimeError,match="crash before commit"): w.checkpoint(2,"not advanced",hook=crash)
    assert sh(p,"rev-parse","HEAD")==parent
    recovered=Workflow(p).recover()
    assert recovered["generations"]["2"]["status"]=="ACCEPTED"
    assert not recovered.get("outstanding_checkpoints")
    assert subprocess.check_output(["git","diff","--cached","--name-only"],cwd=p,text=True)==""

@pytest.mark.parametrize("kind", ["patch-owned", "protected"])
def test_prepare_execution_preserves_durable_ownership_when_path_becomes_ignored(tmp_path,kind):
    p=tmp_path/"repo"; p.mkdir(); sh(p,"init","-q"); sh(p,"config","user.email","t@e"); sh(p,"config","user.name","t")
    (p/"a").write_text("a"); (p/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    sh(p,"add","."); sh(p,"commit","-qm","g")
    if kind=="protected": (p/"protected.txt").write_text("protected\n")
    w=Workflow(p); w.init()
    raw=prompt(w); w.ingest(); w.start_run(1)
    if kind=="patch-owned": (p/"owned.txt").write_text("owned\n")
    w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
    path_name="owned.txt" if kind=="patch-owned" else "protected.txt"
    state=w._state()
    if kind=="patch-owned":
        assert path_name.encode().hex() in state["patch_owned_untracked"]
    else:
        assert any(x["path"]==path_name.encode().hex() for x in state["protected_untracked"])
    exclude=tmp_path/"global-excludes"; sh(p,"config","core.excludesFile",str(exclude))
    raw2=prompt(w,g=2,parent=1); w.ingest()
    class PrepareIgnores(FakeExecutor):
        def prepare_execution(self,spec):
            exclude.write_text(path_name+"\n")
            assert subprocess.run(["git","check-ignore","--quiet","--",path_name],cwd=p).returncode==0
            return super().prepare_execution(spec)
    w.execute(2,PrepareIgnores())
    assert w._state()["generations"]["2"]["status"]=="COMPLETED"

def test_checkpoint_recovery_rejects_unexpected_head(repo):
    p,w,_=checkpoint_ready(repo)
    def crash(point,data):
        if point=="committed": raise RuntimeError("crash after commit")
    with pytest.raises(RuntimeError): w.checkpoint(2,"recoverable checkpoint",hook=crash)
    sh(p,"commit","--allow-empty","--no-verify","-qm","unexpected")
    with pytest.raises(WorkflowError,match="CHECKPOINT_RECOVERY_REPOSITORY_MISMATCH"): Workflow(p).recover()

def test_checkpoint_reset_failure_is_distinct(repo,monkeypatch):
    p,w,_=checkpoint_ready(repo)
    import tools.atlas_agent.repository as repository
    real_run=repository._run
    def failed_commit_and_reset(root,*args,**kwargs):
        if args and args[0]=="commit-tree": raise repository.RepositoryError("commit failed")
        if args and args[0]=="reset": raise repository.RepositoryError("reset failed")
        return real_run(root,*args,**kwargs)
    monkeypatch.setattr(repository,"_run",failed_commit_and_reset)
    with pytest.raises(WorkflowError,match="CHECKPOINT_ROLLBACK_FAILED: reset failed"): w.checkpoint(2,"will fail")


def test_bubblewrap_executes_controller_runtime_through_readonly_bind(tmp_path):
    """Regression: bwrap executes the controller's authenticated runtime bind."""
    import fcntl
    import os
    import shutil
    import subprocess

    bwrap = shutil.which("bwrap")
    if bwrap is None:
        pytest.skip("bubblewrap unavailable")
    if not hasattr(os, "memfd_create"):
        pytest.skip("memfd unavailable")

    source = shutil.which("true")
    if source is None:
        pytest.skip("true executable unavailable")

    fd = os.memfd_create(
        "atlas-bwrap-test",
        os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
    )
    try:
        with open(source, "rb") as src:
            while chunk := src.read(1024 * 1024):
                os.write(fd, chunk)

        os.fchmod(fd, 0o500)
        fcntl.fcntl(
            fd,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )

        command = [
            bwrap,
            "--die-with-parent",
            "--unshare-pid",
            "--unshare-ipc",
            "--ro-bind", "/usr", "/usr",
        ]
        for path in ("/lib", "/lib64"):
            if os.path.exists(path):
                command += ["--ro-bind", path, path]

        runtime = tmp_path / "codex.runtime"
        with open(runtime, "wb") as dst:
            dst.write(Path(source).read_bytes())
        os.chmod(runtime, 0o500)

        command += [
            "--proc", "/proc",
            "--dev", "/dev",
            "--dir", "/opt",
            "--ro-bind", str(runtime), "/opt/atlas-codex",
            "--",
            "/opt/atlas-codex",
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(fd,),
            check=False,
            timeout=5,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    finally:
        os.close(fd)
