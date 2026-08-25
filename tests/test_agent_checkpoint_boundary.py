import hashlib
import json
import subprocess

import pytest

from tools.atlas_agent.cli import main
from tools.atlas_agent.repository import checkpoint_commit, witness
from tools.atlas_agent.workflow import Workflow, WorkflowError

from test_agent_workflow_w1 import repo  # noqa: F401


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def prompt(workflow, root, generation, action):
    parent='"genesis"' if generation == 1 else str(generation - 1)
    raw=(f'''+++
schema = "atlas-agent-prompt/1"
generation = {generation}
parent = {parent}
checkpoint = "boundary-{generation}"
action = "{action}"
expected_head = "{git(root, "rev-parse", "HEAD")}"
session_mode = "fresh"
+++
body
''').encode()
    (workflow.base/"inbox"/f"g{generation}.txt").write_bytes(raw)
    workflow.ingest()
    return raw


def accepted_dirty_checkpoint(root, workflow, change=None):
    raw=prompt(workflow,root,1,"implementation")
    workflow.start_run(1)
    if change is None: (root/"a").write_text("reviewed\n")
    else: change(root)
    workflow.complete_run(1,{"generation":1,"prompt_sha256":hashlib.sha256(raw).hexdigest(),"action":"implementation","outcome":"done","classification":"manual"})
    prompt(workflow,root,2,"checkpoint")


def test_checkpoint_cli_commits_and_records_new_boundary_without_allowed_untracked(repo,monkeypatch,capsys):
    root,workflow=repo
    accepted_dirty_checkpoint(root,workflow)
    (root/"corpus_miner").mkdir()
    (root/"corpus_miner"/"keep.txt").write_text("out of scope\n")
    old_head=git(root,"rev-parse","HEAD")
    monkeypatch.chdir(root)

    assert main(["checkpoint","2","--message","Complete reviewed boundary"])==0

    new_head=git(root,"rev-parse","HEAD")
    assert new_head!=old_head
    assert git(root,"show","--pretty=format:","--name-only",new_head)=="a"
    assert git(root,"log","-1","--pretty=%s")=="Complete reviewed boundary"
    assert (root/"corpus_miner"/"keep.txt").read_text()=="out of scope\n"
    assert "?? corpus_miner/" in git(root,"status","--short","--untracked-files=normal")
    state=workflow._state()
    record=state["generations"]["2"]
    assert record["status"]=="COMPLETED"
    assert record["result"]["commit_sha"]==new_head
    assert state["latest_repository_witness"]==witness(root,workflow.allowed)
    assert main(["status"])==0
    assert "repository witness: MATCH" in capsys.readouterr().out
    assert main(["doctor"])==0


def test_checkpoint_commits_exact_witnessed_new_file_without_staging_allowed_untracked(repo):
    root,workflow=repo
    raw=prompt(workflow,root,1,"implementation")
    workflow.start_run(1)
    (root/"new-module.py").write_text("VALUE = 1\n")
    (root/"corpus_miner").mkdir()
    (root/"corpus_miner"/"keep.txt").write_text("out of scope\n")
    workflow.complete_run(1,{"generation":1,"prompt_sha256":hashlib.sha256(raw).hexdigest(),"action":"implementation"})
    expected=workflow._state()["latest_repository_witness"]

    checkpoint_commit(root,workflow.allowed,expected,"Add new module")

    assert git(root,"show","--pretty=format:","--name-only","HEAD")=="new-module.py"
    assert git(root,"show","HEAD:new-module.py")=="VALUE = 1"
    assert (root/"corpus_miner"/"keep.txt").read_text()=="out of scope\n"
    assert "?? corpus_miner/" in git(root,"status","--short","--untracked-files=normal")
    assert git(root,"diff","--cached","--name-only")==""


def test_checkpoint_rejects_new_file_content_change_after_witness(repo):
    root,workflow=repo
    raw=prompt(workflow,root,1,"implementation")
    workflow.start_run(1)
    (root/"new-module.py").write_text("REVIEWED = True\n")
    workflow.complete_run(1,{"generation":1,"prompt_sha256":hashlib.sha256(raw).hexdigest(),"action":"implementation"})
    prompt(workflow,root,2,"checkpoint")
    (root/"new-module.py").write_text("REVIEWED = False\n")
    head=git(root,"rev-parse","HEAD")

    with pytest.raises(WorkflowError,match="REPOSITORY_WITNESS_MISMATCH"):
        workflow.checkpoint(2,"must not commit")

    assert git(root,"rev-parse","HEAD")==head
    assert git(root,"diff","--cached","--name-only")==""
    assert workflow._state()["generations"]["2"]["status"]=="ACCEPTED"


@pytest.mark.parametrize(
    ("mutation","error"),
    [
        (lambda root: (root/"a").unlink(),"CHECKPOINT_UNHANDLED_REPOSITORY_CONTENT"),
        (lambda root: (root/"a").write_text("trailing space \n"),"CHECKPOINT_DIFF_CHECK_FAILED"),
    ],
)
def test_checkpoint_fails_closed_on_unhandled_or_bad_tracked_content(repo,mutation,error):
    root,workflow=repo
    accepted_dirty_checkpoint(root,workflow,mutation)
    checkpoint=workflow._state()["generations"]["2"]
    with pytest.raises(WorkflowError,match=error):
        workflow.checkpoint(2,"must not commit")
    assert git(root,"rev-parse","HEAD")==checkpoint["expected_head"]
    assert workflow._state()["generations"]["2"]["status"]=="ACCEPTED"


def test_checkpoint_rejects_repository_change_after_acceptance(repo):
    root,workflow=repo
    accepted_dirty_checkpoint(root,workflow)
    (root/"surprise.txt").write_text("unexpected\n")
    head=git(root,"rev-parse","HEAD")
    with pytest.raises(WorkflowError,match="REPOSITORY_WITNESS_MISMATCH"):
        workflow.checkpoint(2,"must not commit")
    assert git(root,"rev-parse","HEAD")==head
    assert workflow._state()["generations"]["2"]["status"]=="ACCEPTED"


def test_checkpoint_rejects_preexisting_index_content(tmp_path):
    root=tmp_path/"indexed"; root.mkdir()
    git(root,"init","-q")
    git(root,"config","user.email","t@e")
    git(root,"config","user.name","t")
    (root/"atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    (root/"a").write_text("original\n")
    git(root,"add",".")
    git(root,"commit","-qm","genesis")
    (root/"a").write_text("staged\n")
    git(root,"add","a")
    workflow=Workflow(root); workflow.init()
    prompt(workflow,root,1,"checkpoint")

    with pytest.raises(WorkflowError,match="CHECKPOINT_UNHANDLED_REPOSITORY_CONTENT"):
        workflow.checkpoint(1,"must not commit")

    assert git(root,"diff","--cached","--name-only")=="a"
    assert workflow._state()["generations"]["1"]["status"]=="ACCEPTED"


def test_failed_git_commit_is_not_completed_and_restores_unstaged_patch(repo):
    root,workflow=repo
    accepted_dirty_checkpoint(root,workflow)
    hook=root/".git"/"hooks"/"pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    head=git(root,"rev-parse","HEAD")

    with pytest.raises(WorkflowError):
        workflow.checkpoint(2,"rejected by hook")

    assert git(root,"rev-parse","HEAD")==head
    assert git(root,"diff","--cached","--name-only")==""
    assert git(root,"diff","--name-only")=="a"
    assert workflow._state()["generations"]["2"]["status"]=="ACCEPTED"


def test_checkpoint_requires_message(repo,monkeypatch):
    root,workflow=repo
    prompt(workflow,root,1,"checkpoint")
    with pytest.raises(WorkflowError,match="CHECKPOINT_COMMIT_MESSAGE_REQUIRED"):
        workflow.checkpoint(1,"")
    monkeypatch.chdir(root)
    assert main(["checkpoint","1"])==1
