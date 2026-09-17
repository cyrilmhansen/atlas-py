import copy
import hashlib
import json
import subprocess

import pytest

from tools.atlas_agent.workflow import Workflow, WorkflowError
from tools.atlas_agent.workflow import replay_journal
from tools.atlas_agent.repository import witness

from test_agent_checkpoint_boundary import prompt
from test_agent_workflow_w1 import repo  # noqa: F401
from tools.atlas_agent.executor import ExecutorError, FakeExecutor


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


def test_returned_executor_failure_adopts_partial_patch_for_review(repo):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")

    class PartialFailure(FakeExecutor):
        def run_execution(self, prepared):
            result = super().run_execution(prepared)
            (root / "a").write_text("partial implementation\n")
            (root / "residue.py").write_text("residue\n")
            return result

    with pytest.raises(WorkflowError, match="EXECUTOR_EXIT_7"):
        workflow.execute(1, PartialFailure(exit_code=7))

    state = workflow._state()
    assert state["generations"]["1"]["status"] == "INTERRUPTED"
    assert "726573696475652e7079" in state["patch_owned_untracked"]
    assert state["latest_repository_witness"] == witness(
        root, workflow.allowed,
        {"protected_untracked": state["protected_untracked"],
         "patch_owned_untracked": state["patch_owned_untracked"]})
    event = next(e for e in workflow.journal.read()
                 if e["event"] == "RUN_INTERRUPTED")
    assert event["payload"]["executor_result"]["execution_id"] == \
        event["payload"]["execution"]["execution_id"]
    assert "witness" not in event["payload"]
    confirmed = next(e for e in workflow.journal.read()
                     if e["event"] == "EXECUTOR_QUIESCENCE_CONFIRMED")
    assert confirmed["payload"]["execution_id"] == \
        event["payload"]["execution"]["execution_id"]
    assert confirmed["payload"]["witness"] == state["latest_repository_witness"]

    review = prompt(workflow, root, 2, "patch_review")
    workflow.start_run(2)
    workflow.complete_run(2, _result(review, 2, "patch_review"))
    assert workflow._state()["generations"]["2"]["status"] == "COMPLETED"


@pytest.mark.parametrize("failure", [
    "ATLAS_SANDBOX_SERVER_UNREAPED",
    "CODEX_PROCESS_UNREAPED",
])
def test_executor_unwind_does_not_confirm_quiescence(repo, failure):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")

    class Unreaped(FakeExecutor):
        def run_execution(self, prepared):
            raise ExecutorError(failure)

    with pytest.raises(WorkflowError, match="EXECUTOR_FAILURE"):
        workflow.execute(1, Unreaped())

    record = workflow._state()["generations"]["1"]
    assert record["status"] == "INTERRUPTED"
    assert record["executor_quiescence_confirmed"] is False
    assert not any(e["event"] == "EXECUTOR_QUIESCENCE_CONFIRMED"
                   for e in workflow.journal.read())

    prompt(workflow, root, 2, "patch_review")
    with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
        workflow.start_run(2)


def _fail_first_running_projection(workflow):
    original_save = workflow._save
    tripped = False

    def save(state):
        nonlocal tripped
        if (not tripped and
                state["generations"]["1"]["status"] == "RUNNING"):
            tripped = True
            raise OSError("post-start projection failure")
        return original_save(state)

    return save


def test_post_start_failure_with_positive_abandon_confirms_and_unblocks(repo,
                                                                         monkeypatch):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")

    class Abandonable(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.abandoned = 0

        def abandon_prepared_execution(self, prepared):
            self.abandoned += 1
            return super().abandon_prepared_execution(prepared)

    executor = Abandonable()
    monkeypatch.setattr(workflow, "_save",
                        _fail_first_running_projection(workflow))
    with pytest.raises(OSError, match="post-start projection failure"):
        workflow.execute(1, executor)

    record = workflow._state()["generations"]["1"]
    assert executor.launched == 0
    assert executor.abandoned == 1
    assert record["status"] == "INTERRUPTED"
    assert record["executor_quiescence_confirmed"] is True
    assert any(e["event"] == "EXECUTOR_QUIESCENCE_CONFIRMED"
               for e in workflow.journal.read())

    prompt(workflow, root, 2, "patch_review")
    workflow.start_run(2)


def test_post_start_failure_with_uncertain_abandon_remains_blocked(repo,
                                                                    monkeypatch):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")

    class Uncertain(FakeExecutor):
        def abandon_prepared_execution(self, prepared):
            return False

    monkeypatch.setattr(workflow, "_save",
                        _fail_first_running_projection(workflow))
    with pytest.raises(OSError, match="post-start projection failure"):
        workflow.execute(1, Uncertain())

    record = workflow._state()["generations"]["1"]
    assert record["status"] == "INTERRUPTED"
    assert record["executor_quiescence_confirmed"] is False
    assert not any(e["event"] == "EXECUTOR_QUIESCENCE_CONFIRMED"
                   for e in workflow.journal.read())
    prompt(workflow, root, 2, "patch_review")
    with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
        workflow.start_run(2)


@pytest.mark.parametrize("failure_source", ["post_start_prepare",
                                             "execution_artifact"])
@pytest.mark.parametrize("cleanup_mode", ["success", "false", "raise"])
def test_prelaunch_failure_cleans_before_quiescence_authority(
        repo, monkeypatch, failure_source, cleanup_mode):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")

    class PrelaunchFailure(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.abandon_calls = 0
            self.trace = []

        def post_start_prepare(self, prepared):
            if failure_source == "post_start_prepare":
                raise RuntimeError("post-start preparation failure")
            return super().post_start_prepare(prepared)

        def abandon_prepared_execution(self, prepared):
            self.abandon_calls += 1
            self.trace.append("cleanup")
            if cleanup_mode == "raise":
                raise RuntimeError("prepared cleanup failure")
            if cleanup_mode == "false":
                return False
            return super().abandon_prepared_execution(prepared)

    executor = PrelaunchFailure()
    original_confirm = workflow._confirm_executor_quiescence

    def record_confirmation(generation, execution_id):
        executor.trace.append("confirmation")
        return original_confirm(generation, execution_id)

    monkeypatch.setattr(workflow, "_confirm_executor_quiescence",
                        record_confirmation)
    if failure_source == "execution_artifact":
        original = workflow._publish_execution_artifact
        calls = 0

        def fail_after_run_started(path, value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("execution artifact publication failure")
            return original(path, value)

        monkeypatch.setattr(workflow, "_publish_execution_artifact",
                            fail_after_run_started)

    error = ("post-start preparation failure"
             if failure_source == "post_start_prepare"
             else "execution artifact publication failure")
    with pytest.raises((RuntimeError, WorkflowError), match=error):
        workflow.execute(1, executor)

    events = workflow.journal.read()
    interrupted = next(e for e in events if e["event"] == "RUN_INTERRUPTED")
    confirmations = [
        e for e in events
        if e["event"] == "EXECUTOR_QUIESCENCE_CONFIRMED"
    ]
    record = workflow._state()["generations"]["1"]
    assert executor.launched == 0
    assert executor.abandon_calls == 1
    assert interrupted["payload"]["executor_launched"] is False
    assert "executor_result" not in interrupted["payload"]
    assert not interrupted["payload"].get("fallback_artifacts")
    assert record["executor_launched"] is False
    assert record["executor_quiescence_confirmed"] is (cleanup_mode == "success")
    assert len(confirmations) == (1 if cleanup_mode == "success" else 0)
    assert executor.trace == (
        ["cleanup", "confirmation"]
        if cleanup_mode == "success" else ["cleanup"]
    )
    if confirmations:
        assert events.index(confirmations[0]) > events.index(interrupted)

    prompt(workflow, root, 2, "patch_review")
    if cleanup_mode == "success":
        workflow.start_run(2)
    else:
        with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
            workflow.start_run(2)


def test_confirmation_projection_gap_recovers_from_cached_interruption(repo,
                                                                        monkeypatch):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")
    original_save = workflow._save
    confirmation_save_failed = False

    def save(state):
        nonlocal confirmation_save_failed
        latest = workflow.journal.read()
        if (not confirmation_save_failed and
                latest and
                latest[-1]["event"] == "EXECUTOR_QUIESCENCE_CONFIRMED"):
            confirmation_save_failed = True
            raise OSError("confirmation projection failure")
        return original_save(state)

    monkeypatch.setattr(workflow, "_save", save)
    with pytest.raises(WorkflowError, match="EXECUTOR_EXIT_7"):
        workflow.execute(1, FakeExecutor(exit_code=7))

    assert workflow._state()["generations"]["1"]["status"] == "INTERRUPTED"
    assert workflow._state()["generations"]["1"][
        "executor_quiescence_confirmed"] is False
    assert workflow.journal.read()[-1]["event"] == \
        "EXECUTOR_QUIESCENCE_CONFIRMED"

    monkeypatch.setattr(workflow, "_save", original_save)
    recovered = workflow.recover()
    assert recovered["generations"]["1"][
        "executor_quiescence_confirmed"] is True
    assert workflow._state() == recovered


def test_stale_confirmation_cache_is_rejected(repo):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")
    with pytest.raises(WorkflowError, match="EXECUTOR_EXIT_7"):
        workflow.execute(1, FakeExecutor(exit_code=7))

    state_path = workflow._state_file()
    stale = workflow._state()
    stale["last_seq"] -= 1
    state_path.write_text(
        json.dumps(stale, sort_keys=True, indent=2) + "\n")
    with pytest.raises(WorkflowError, match="STATE_STALE_OR_TAMPERED"):
        workflow.recover()


def test_manual_interruption_does_not_adopt_observed_patch(repo):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    previous = workflow._state()["latest_repository_witness"]
    (root / "a").write_text("executor may still write\n")
    (root / "residue.py").write_text("not safely owned\n")

    workflow.interrupt_run(1, "operator interrupted")

    state = workflow._state()
    event = next(e for e in workflow.journal.read()
                 if e["event"] == "RUN_INTERRUPTED")
    assert state["generations"]["1"]["status"] == "INTERRUPTED"
    assert state["latest_repository_witness"] == previous
    assert "726573696475652e7079" not in state.get("patch_owned_untracked", [])
    assert "witness" not in event["payload"]
    assert "acquired_untracked" not in event["payload"]

    # The dirty observation was not laundered into a boundary for descendants.
    prompt(workflow, root, 2, "patch_review")
    assert "2" not in workflow._state()["generations"]


@pytest.mark.parametrize("write_before_interrupt", [False, True])
def test_manual_interruption_blocks_until_execute_confirms_quiescence(
        repo, write_before_interrupt):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")
    observations = {}

    class InterruptedThenReturned(FakeExecutor):
        def run_execution(self, prepared):
            if write_before_interrupt:
                (root / "a").write_text("partial before interrupt\n")
            # Even a result-shaped dictionary with the exact owner ID is only
            # caller data; it cannot stand in for this method returning.
            workflow.interrupt_run(
                1, "operator interrupted",
                {"execution_id": prepared.spec.execution_id})
            interrupted = workflow._state()
            observations["boundary"] = interrupted["latest_repository_witness"]
            observations["record"] = dict(interrupted["generations"]["1"])
            observations["owned"] = list(
                interrupted.get("patch_owned_untracked", []))
            with pytest.raises(WorkflowError, match="RUNNING_GENERATION_EXISTS"):
                workflow._admit_run_start(interrupted, 2)
            with pytest.raises(WorkflowError, match="EXECUTOR_QUIESCENCE_BINDING"):
                workflow._confirm_executor_quiescence(1, "wrong-execution")
            # The executor remains capable of writing after manual
            # terminalization.  This is part of the final witness only after
            # control returns to execute().
            (root / "a").write_text("final partial patch\n")
            (root / "residue.py").write_text("final residue\n")
            return super().run_execution(prepared)

    initial = workflow._state()["latest_repository_witness"]
    with pytest.raises(WorkflowError, match="EXECUTOR_EXIT_7"):
        workflow.execute(1, InterruptedThenReturned(exit_code=7))

    assert observations["boundary"] == initial
    assert observations["record"]["status"] == "INTERRUPTED"
    assert observations["record"]["executor_quiescence_confirmed"] is False
    assert "726573696475652e7079" not in observations["owned"]
    interrupted = next(e for e in workflow.journal.read()
                       if e["event"] == "RUN_INTERRUPTED")
    assert "witness" not in interrupted["payload"]
    assert "acquired_untracked" not in interrupted["payload"]

    state = workflow._state()
    assert state["generations"]["1"]["executor_quiescence_confirmed"] is True
    assert "726573696475652e7079" in state["patch_owned_untracked"]
    assert state["latest_repository_witness"] == witness(
        root, workflow.allowed,
        {"protected_untracked": state["protected_untracked"],
         "patch_owned_untracked": state["patch_owned_untracked"]})

    review = prompt(workflow, root, 2, "patch_review")
    workflow.start_run(2)
    workflow.complete_run(2, _result(review, 2, "patch_review"))
    assert workflow._state()["generations"]["2"]["status"] == "COMPLETED"


def test_execute_control_flow_not_result_identity_qualifies_interruption(repo):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")

    class ForeignFailure(FakeExecutor):
        def run_execution(self, prepared):
            from dataclasses import replace
            result = super().run_execution(prepared)
            (root / "a").write_text("foreign partial patch\n")
            return replace(result, execution_id="stale-execution")

    with pytest.raises(WorkflowError, match="RESULT_EXECUTION_MISMATCH"):
        workflow.execute(1, ForeignFailure())

    state = workflow._state()
    event = next(e for e in workflow.journal.read()
                 if e["event"] == "RUN_INTERRUPTED")
    assert state["generations"]["1"]["status"] == "INTERRUPTED"
    assert state["generations"]["1"]["executor_quiescence_confirmed"] is True
    assert "executor_result" not in event["payload"]
    assert "witness" not in event["payload"]
    assert "acquired_untracked" not in event["payload"]
    confirmed = next(e for e in workflow.journal.read()
                     if e["event"] == "EXECUTOR_QUIESCENCE_CONFIRMED")
    assert confirmed["payload"]["execution_id"] == \
        event["payload"]["execution"]["execution_id"]


def test_interruption_does_not_adopt_disallowed_staged_state(repo):
    root, workflow = repo
    prompt(workflow, root, 1, "implementation")
    workflow.start_run(1)
    previous = workflow._state()["latest_repository_witness"]
    (root / "a").write_text("staged mutation\n")
    subprocess.check_call(["git", "add", "a"], cwd=root)

    workflow.interrupt_run(1, "operator interrupted")

    state = workflow._state()
    event = next(e for e in workflow.journal.read()
                 if e["event"] == "RUN_INTERRUPTED")
    assert state["generations"]["1"]["status"] == "INTERRUPTED"
    assert state["latest_repository_witness"] == previous
    assert "witness" not in event["payload"]
    assert "acquired_untracked" not in event["payload"]


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
