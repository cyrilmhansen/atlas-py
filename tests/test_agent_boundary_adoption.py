import subprocess
import pytest

from tools.atlas_agent.workflow import Workflow, WorkflowError, replay_journal
from tools.atlas_agent.repository import witness

def git(p, *args):
    return subprocess.check_output(["git", *args], cwd=p, text=True).strip()

@pytest.fixture
def repo(tmp_path):
    p=tmp_path/"repo"; p.mkdir()
    git(p,"init","-q"); git(p,"config","user.email","t@e"); git(p,"config","user.name","t")
    (p/"a").write_text("a")
    (p/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    git(p,"add","."); subprocess.check_call(["git","commit","-qm","genesis"],cwd=p)
    w=Workflow(p); w.init()
    return p,w

def advance_clean(p):
    (p/"a").write_text("b")
    git(p,"add","a")
    subprocess.check_call(["git","commit","-qm","external qualified change"],cwd=p)
    return git(p,"rev-parse","HEAD")

def put(w, head):
    raw=(
        "+++\n"
        'schema = "atlas-agent-prompt/1"\n'
        "generation = 1\n"
        'parent = "genesis"\n'
        'checkpoint = "W1"\n'
        'action = "implementation"\n'
        f'expected_head = "{head}"\n'
        'session_mode = "fresh"\n'
        "+++\n"
        "body\n"
    ).encode()
    (w.base/"inbox"/"input.txt").write_bytes(raw)

def test_adopt_boundary_records_clean_descendant(repo):
    p,w=repo
    previous=w._state()["latest_repository_witness"]
    new_head=advance_clean(p)
    state=w.adopt_boundary(previous["head"],new_head,"qualified promotion")
    assert state["latest_repository_witness"] == witness(p,w.allowed)
    assert state["latest_repository_witness"]["head"] == new_head
    assert state.get("patch_owned_untracked") == []
    event=w.journal.read()[-1]
    assert event["event"] == "REPOSITORY_BOUNDARY_ADOPTED"
    assert event["payload"]["previous_witness"] == previous
    assert event["payload"]["reason"] == "qualified promotion"
    assert replay_journal(w.journal.read()) == state

def test_adopt_boundary_rejects_dirty_repository(repo):
    p,w=repo
    previous=w._state()["latest_repository_witness"]
    new_head=advance_clean(p)
    (p/"a").write_text("dirty")
    with pytest.raises(WorkflowError,match="BOUNDARY_ADOPTION_DIRTY_REPOSITORY"):
        w.adopt_boundary(previous["head"],new_head,"qualified promotion")

def test_adopt_boundary_rejects_nonterminal_generation(repo):
    p,w=repo
    previous=w._state()["latest_repository_witness"]
    put(w,previous["head"]); w.ingest()
    new_head=advance_clean(p)
    with pytest.raises(WorkflowError,match="BOUNDARY_ADOPTION_NONTERMINAL"):
        w.adopt_boundary(previous["head"],new_head,"qualified promotion")

def test_adopt_boundary_requires_exact_operator_heads(repo):
    p,w=repo
    previous=w._state()["latest_repository_witness"]
    new_head=advance_clean(p)
    with pytest.raises(WorkflowError,match="BOUNDARY_ADOPTION_EXPECTED_HEAD_MISMATCH"):
        w.adopt_boundary("0"*40,new_head,"qualified promotion")
    with pytest.raises(WorkflowError,match="BOUNDARY_ADOPTION_NEW_HEAD_MISMATCH"):
        w.adopt_boundary(previous["head"],"0"*40,"qualified promotion")

def test_adopt_boundary_rejects_branch_change(repo):
    p,w=repo
    previous=w._state()["latest_repository_witness"]
    git(p,"checkout","-qb","other")
    new_head=advance_clean(p)
    with pytest.raises(WorkflowError,match="BOUNDARY_ADOPTION_BRANCH_MISMATCH"):
        w.adopt_boundary(previous["head"],new_head,"qualified promotion")
