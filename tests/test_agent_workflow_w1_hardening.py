import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import pytest
from tools.atlas_agent.workflow import Workflow,WorkflowError,replay_journal
from tools.atlas_agent.journal import canonical,_hash_event
from tools.atlas_agent.prompt import parse_prompt,PromptError

def sh(p,*a): return subprocess.check_output(["git",*a],cwd=p,text=True).strip()
@pytest.fixture
def repo(tmp_path):
    p=tmp_path/"r"; p.mkdir(); sh(p,"init","-q"); sh(p,"config","user.email","t@e"); sh(p,"config","user.name","t")
    (p/"a").write_text("a"); (p/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n'); sh(p,"add","."); sh(p,"commit","-qm","g"); w=Workflow(p); w.init(); return p,w
def prompt(w,g=1,parent="genesis",action="implementation",body="body"):
    parent_line=f'parent = "{parent}"' if parent=="genesis" else f"parent = {parent}"
    raw=f'''+++\nschema = "atlas-agent-prompt/1"\ngeneration = {g}\n{parent_line}\ncheckpoint = "W1"\naction = "{action}"\nexpected_head = "{sh(w.root,"rev-parse","HEAD")}"\nsession_mode = "fresh"\n+++\n{body}\n'''.encode(); (w.base/"inbox"/f"user-{g}-{body}").write_bytes(raw); return raw
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
def test_implementation_unexpected_untracked_interrupts(repo):
    p,w=repo; raw=running(w); (p/"unexpected.txt").write_text("x")
    with pytest.raises(WorkflowError): w.complete_run(1,{"generation":1,"prompt_sha256":digest(raw),"action":"implementation"})
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"
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
