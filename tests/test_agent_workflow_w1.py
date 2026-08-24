import hashlib, json, subprocess
from pathlib import Path
import pytest

from tools.atlas_agent.workflow import Workflow, WorkflowError
from tools.atlas_agent.repository import runtime_path

def git(p, *args): return subprocess.check_output(["git", *args], cwd=p, text=True).strip()

@pytest.fixture
def repo(tmp_path):
    p=tmp_path/"repo"; p.mkdir(); git(p,"init","-q"); git(p,"config","user.email","t@e"); git(p,"config","user.name","t")
    (p/"a").write_text("a"); (p/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    git(p,"add","."); subprocess.check_call(["git","commit","-qm","genesis"],cwd=p)
    w=Workflow(p); w.init(); return p,w

def put(w, head, generation=1, parent="genesis", action="implementation", body="body"):
    text=f'''+++\nschema = "atlas-agent-prompt/1"\ngeneration = {generation}\nparent = "{parent}"\ncheckpoint = "W1"\naction = "{action}"\nexpected_head = "{head}"\nsession_mode = "fresh"\n+++\n{text if False else body}\n'''.encode()
    (w.base/"inbox"/f"input-{generation}.txt").write_bytes(text); return text

def digest(raw): return hashlib.sha256(raw).hexdigest()

def test_init_twice_and_valid_lifecycle(repo):
    p,w=repo
    with pytest.raises(WorkflowError): w.init()
    raw=put(w,git(p,"rev-parse","HEAD")); w.ingest(); assert list((w.base/"accepted").glob("*.txt"))
    w.start_run(1); running=next((w.base/"running/implementation").glob("*.txt")); result={"generation":1,"prompt_sha256":digest(raw),"action":"implementation","outcome":"done","classification":"manual"}; w.complete_run(1,result)
    assert list((w.base/"completed").glob("*.txt")); assert w._state()["generations"]["1"]["status"]=="COMPLETED"

@pytest.mark.parametrize("kind",["bad-head","unknown-parent","bad-generation","malformed"])
def test_rejections(repo, kind):
    p,w=repo; head=git(p,"rev-parse","HEAD")
    if kind=="bad-head": raw=put(w,"0"*40)
    elif kind=="unknown-parent": raw=put(w,head,parent="7")
    elif kind=="bad-generation": raw=put(w,head,generation=2,parent="genesis")
    else: raw=b"not front matter"; (w.base/"inbox"/"malformed.txt").write_bytes(raw)
    w.ingest(); reasons=list((w.base/"rejected").glob("*.reason.json")); assert reasons
    assert json.loads(reasons[0].read_text())["code"] in {"HEAD_MISMATCH","UNKNOWN_PARENT","BAD_GENERATION","MALFORMED_FRONT_MATTER"}

def test_duplicate_and_collision(repo):
    p,w=repo; h=git(p,"rev-parse","HEAD"); raw=put(w,h); w.ingest()
    (w.base/"inbox"/"second.txt").write_bytes(raw); w.ingest()
    assert json.loads(next((w.base/"rejected").glob("*.reason.json")).read_text())["code"]=="DUPLICATE_PROMPT"
    raw2=raw.replace(b"body",b"other"); (w.base/"inbox"/"third.txt").write_bytes(raw2); w.ingest()
    assert sorted(json.loads(x.read_text())["code"] for x in (w.base/"rejected").glob("*.reason.json"))==["DUPLICATE_PROMPT","GENERATION_COLLISION"]

def test_allowed_untracked_and_unexpected_witness(repo):
    p,w=repo; (p/"corpus_miner").mkdir(); (p/"corpus_miner"/"x").write_text("x"); before=w._state()["latest_repository_witness"]
    from tools.atlas_agent.repository import witness
    assert witness(p,w.allowed)==before
    (p/"surprise").write_text("x"); assert witness(p,w.allowed)!=before

def test_bad_result_and_rebuild(repo):
    p,w=repo; raw=put(w,git(p,"rev-parse","HEAD")); w.ingest(); w.start_run(1)
    with pytest.raises(WorkflowError): w.complete_run(1,{"generation":1,"prompt_sha256":"0"*64,"action":"implementation"})
    state=json.loads((w.base/"state.json").read_text()); (w.base/"state.json").unlink(); assert w.rebuild()==state

@pytest.mark.parametrize("stage",["prepared","renamed"])
def test_recovery_after_crash(repo, stage):
    p,w=repo; raw=put(w,git(p,"rev-parse","HEAD")); w.ingest()
    def hook(point, data):
        if point==stage: raise RuntimeError("simulated crash")
    with pytest.raises(RuntimeError): w.start_run(1,hook=hook)
    w2=Workflow(p); w2.recover(); assert list((w2.base/"running/implementation").glob("*.txt")); assert w2._state()["generations"]["1"]["status"]=="RUNNING"

def test_journal_tamper_fails(repo):
    p,w=repo; path=w.base/"events.jsonl"; path.write_text(path.read_text().replace("WORKFLOW_INITIALIZED","TAMPERED",1))
    with pytest.raises(Exception): w.journal.read()
