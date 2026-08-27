import hashlib
import subprocess

import pytest

from tools.atlas_agent.workflow import Workflow, WorkflowError
from tools.atlas_agent.workflow import replay_journal

from test_agent_checkpoint_boundary import prompt
from test_agent_workflow_w1 import repo  # noqa: F401
from tools.atlas_agent.executor import FakeExecutor


def _result(raw, generation, action="implementation"):
    return {
        "generation": generation,
        "prompt_sha256": hashlib.sha256(raw).hexdigest(),
        "action": action,
    }


def test_completed_implementation_owns_new_file_for_corrective_generation(repo):
    root, workflow = repo
    first = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "new.py").write_text("one\n")
    workflow.complete_run(1, _result(first, 1))

    second = prompt(workflow, root, 2, "implementation")
    workflow.start_run(2)
    (root / "new.py").write_text("two\n")
    workflow.complete_run(2, _result(second, 2))
    assert workflow._state()["patch_owned_untracked"] == ["6e65772e7079"]


def test_checkpoint_does_not_adopt_initial_untracked_user_file(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    import subprocess
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    git("init", "-q")
    git("config", "user.email", "t@e")
    git("config", "user.name", "t")
    (root / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n'
    )
    (root / "a").write_text("a\n")
    git("add", ".")
    git("commit", "-qm", "genesis")
    (root / "user.txt").write_text("keep me\n")
    from tools.atlas_agent.workflow import Workflow
    workflow = Workflow(root)
    workflow.init()
    raw = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "new.py").write_text("patch\n")
    workflow.complete_run(1, _result(raw, 1))
    prompt(workflow, root, 2, "checkpoint")

    workflow.checkpoint(2, "checkpoint patch")
    assert "user.txt" not in git("show", "--pretty=format:", "--name-only", "HEAD")
    assert (root / "user.txt").is_file()
    assert "?? user.txt" in git("status", "--short", "--untracked-files=normal")


def test_owned_deletion_is_a_tombstone_and_rename_acquires_new_target(repo):
    root, workflow = repo
    first = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "old.py").write_text("old\n")
    workflow.complete_run(1, _result(first, 1))

    second = prompt(workflow, root, 2, "implementation")
    workflow.start_run(2)
    (root / "old.py").unlink()
    workflow.complete_run(2, _result(second, 2))
    assert "6f6c642e7079" in workflow._state()["patch_owned_untracked"]

    third = prompt(workflow, root, 3, "implementation")
    workflow.start_run(3)
    (root / "new.py").write_text("new\n")
    workflow.complete_run(3, _result(third, 3))
    assert set(workflow._state()["patch_owned_untracked"]) == {
        "6f6c642e7079", "6e65772e7079"
    }


def test_read_only_generation_cannot_modify_owned_path(repo):
    root, workflow = repo
    first = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "owned.py").write_text("one\n")
    workflow.complete_run(1, _result(first, 1))
    second = prompt(workflow, root, 2, "patch_review")
    workflow.start_run(2)
    (root / "owned.py").write_text("two\n")
    with pytest.raises(WorkflowError, match="REPOSITORY_POLICY_VIOLATION"):
        workflow.complete_run(2, _result(second, 2, "patch_review"))
    assert "6f776e65642e7079" in workflow._state()["patch_owned_untracked"]


def test_interrupted_creation_is_not_acquired(repo):
    root, workflow = repo
    first = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    workflow.complete_run(1, _result(first, 1))
    second = prompt(workflow, root, 2, "implementation")
    workflow.start_run(2)
    (root / "residue.py").write_text("residue\n")
    workflow.interrupt_run(2, "interrupted")
    assert "726573696475652e7079" not in workflow._state()["patch_owned_untracked"]


def test_ownership_replays_without_state_and_checkpoint_clears(repo):
    root, workflow = repo
    first = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "owned.py").write_text("one\n")
    workflow.complete_run(1, _result(first, 1))
    expected = workflow._state()["patch_owned_untracked"]
    workflow._state_file().unlink()
    rebuilt = workflow.rebuild()
    assert rebuilt["patch_owned_untracked"] == expected
    prompt(workflow, root, 2, "checkpoint")
    workflow.checkpoint(2, "clear ownership")
    assert workflow._state()["patch_owned_untracked"] == []


def test_owned_path_cannot_be_laundered_by_ignore_before_checkpoint(repo):
    root, workflow = repo
    first = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "owned.py").write_text("one\n")
    workflow.complete_run(1, _result(first, 1))
    second = prompt(workflow, root, 2, "implementation")
    workflow.start_run(2)
    (root / ".gitignore").write_text("owned.py\n")
    (root / "owned.py").write_text("two\n")
    workflow.complete_run(2, _result(second, 2))
    assert "6f776e65642e7079" in workflow._state()["patch_owned_untracked"]
    prompt(workflow, root, 3, "checkpoint")
    workflow.checkpoint(3, "checkpoint owned")
    git_show = subprocess.check_output(["git", "show", "HEAD:owned.py"], cwd=root, text=True)
    assert git_show == "two\n"


def test_checkpoint_recovery_preserves_protected_path_that_becomes_ignored(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    git("init", "-q")
    git("config", "user.email", "t@e")
    git("config", "user.name", "t")
    (root / "atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    (root / "a").write_text("a\n")
    git("add", ".")
    git("commit", "-qm", "g")
    protected = root / "keep.txt"
    protected.write_bytes(b"durable bytes\n")
    workflow = Workflow(root)
    workflow.init()
    first = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / ".gitignore").write_text("keep.txt\n")
    workflow.complete_run(1, _result(first, 1))
    prompt(workflow, root, 2, "checkpoint")
    def crash(stage, payload):
        if stage == "committed":
            raise RuntimeError("crash after commit")
    with pytest.raises(RuntimeError, match="crash after commit"):
        workflow.checkpoint(2, "ignore configuration", hook=crash)
    recovered = workflow.recover()
    assert recovered["generations"]["2"]["status"] == "COMPLETED"
    assert recovered["protected_untracked"][0]["path"] == protected.name.encode().hex()
    assert recovered["patch_owned_untracked"] == []
    assert protected.read_bytes() == b"durable bytes\n"
    assert workflow.recover() == recovered


@pytest.mark.parametrize("owned_kind", ["patch-owned", "protected"])
def test_execute_preflights_retain_owned_or_protected_path_after_prepare_ignores_it(tmp_path, owned_kind):
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    git("init", "-q"); git("config", "user.email", "t@e"); git("config", "user.name", "t")
    (root / "atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    (root / "a").write_text("a\n"); git("add", "."); git("commit", "-qm", "g")
    if owned_kind == "protected": (root / "kept.txt").write_text("kept\n")
    workflow = Workflow(root); workflow.init()
    raw = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    if owned_kind == "patch-owned": (root / "owned.txt").write_text("owned\n")
    (root / ".gitignore").write_text("owned.txt\nkept.txt\n")
    workflow.complete_run(1, _result(raw, 1))
    raw = prompt(workflow, root, 2, "implementation")

    class PrepareMutation(FakeExecutor):
        def prepare_execution(self, spec):
            ignored = root / ("owned.txt" if owned_kind == "patch-owned" else "kept.txt")
            original = ignored.read_bytes()
            ignored.write_bytes(original + b"temporary")
            ignored.write_bytes(original)
            return super().prepare_execution(spec)

    workflow.execute(2, PrepareMutation())
    assert workflow._state()["generations"]["2"]["status"] == "COMPLETED"


def test_legacy_replay_reconstructs_unambiguous_ownership(repo):
    root, workflow = repo
    raw = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "legacy.py").write_text("legacy\n")
    workflow.complete_run(1, _result(raw, 1))
    events = workflow.journal.read()
    for event in events:
        event["payload"].pop("validation_epoch", None)
        event["payload"].pop("prompt_schema", None)
    state = replay_journal(events)
    assert state["patch_owned_untracked"] == ["6c65676163792e7079"]


def test_replay_rejects_completion_that_omits_acquired_path(repo):
    root, workflow = repo
    raw = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    (root / "real.py").write_text("real\n")
    workflow.complete_run(1, _result(raw, 1))
    events = workflow.journal.read()
    completed = next(e for e in events if e["event"] == "RUN_COMPLETED")
    completed["payload"]["acquired_untracked"] = []
    prepared = next(e for e in events if e["event"] == "TRANSITION_PREPARED" and e["payload"].get("logical_event") == "RUN_COMPLETED")
    prepared["payload"]["acquired_untracked"] = []
    with pytest.raises(WorkflowError, match="JOURNAL_OWNERSHIP_DELTA"):
        replay_journal(events)


def test_owned_tombstone_can_be_recreated(repo):
    root, workflow = repo
    raw = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1); (root / "gone.py").write_text("one\n")
    workflow.complete_run(1, _result(raw, 1))
    raw = prompt(workflow, root, 2, "implementation")
    workflow.start_run(2); (root / "gone.py").unlink(); workflow.complete_run(2, _result(raw, 2))
    raw = prompt(workflow, root, 3, "implementation")
    workflow.start_run(3); (root / "gone.py").write_text("again\n"); workflow.complete_run(3, _result(raw, 3))
    assert "676f6e652e7079" in workflow._state()["patch_owned_untracked"]


def test_owned_file_symlink_replacement_is_allowed(repo):
    root, workflow = repo
    raw = prompt(workflow, root, 1, "implementation")
    workflow.start_run(1); (root / "swap.py").write_text("one\n"); workflow.complete_run(1, _result(raw, 1))
    raw = prompt(workflow, root, 2, "implementation")
    workflow.start_run(2); (root / "swap.py").unlink(); (root / "target").write_text("target\n"); (root / "swap.py").symlink_to("target")
    workflow.complete_run(2, _result(raw, 2))
    assert "737761702e7079" in workflow._state()["patch_owned_untracked"]


def test_policy_violation_does_not_acquire_candidate(repo):
    root, workflow = repo
    raw = prompt(workflow, root, 1, "patch_review")
    workflow.start_run(1); (root / "a").write_text("unauthorized\n"); (root / "candidate.py").write_text("candidate\n")
    # This path is not owned: the run must fail closed even though it also
    # creates a plausible candidate.
    with pytest.raises(WorkflowError, match="REPOSITORY_POLICY_VIOLATION"):
        workflow.complete_run(1, _result(raw, 1, "patch_review"))
    assert "63616e6469646174652e7079" not in workflow._state().get("patch_owned_untracked", [])
