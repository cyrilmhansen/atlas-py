"""Experimental closed-repository patch-review authority and topology."""
import hashlib
import io
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_agent_workflow_w221 import make_repo
from tools.atlas_agent.bubblewrap import AtlasBubblewrapExecutor, AtlasSandboxError
from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionResult, PreparedExecution, utc_now
from tools.atlas_agent.policy import load_policy, resolve_policy, validate_snapshot
from tools.atlas_agent.prompt import PromptError, parse_prompt
from tools.atlas_agent.pvc_context import PvcContextComposition
from tools.atlas_agent.review import build_review_package
from tools.atlas_agent.workflow import WorkflowError


def raw(repo, *, action="patch_review", session="fresh", visibility=None):
    extra = '' if visibility is None else f'repository_visibility = "{visibility}"\n'
    reuse = '' if session == "fresh" else 'reuse_execution_id = "prior"\n'
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo,
                                   text=True).strip()
    return (f'''+++\nschema = "atlas-agent-prompt/3"\ngeneration = 1\nparent = "genesis"\ncheckpoint = "closed-v0"\naction = "{action}"\nexpected_head = "{head}"\nsession_mode = "{session}"\nnetwork_access = false\ncompute_profile = "sol-medium"\n{reuse}{extra}+++\nreview\n''').encode()


def snapshot(repo, **kwargs):
    prompt = parse_prompt(raw(repo, **kwargs))
    return prompt, resolve_policy(load_policy(repo / "atlas-agent-policy.toml"),
                                  prompt, for_new_execution=True)


def test_full_default_and_current_cwd_mount_are_preserved(tmp_path):
    repo, _ = make_repo(tmp_path)
    prompt, authority = snapshot(repo)
    assert prompt.repository_visibility == authority["repository_visibility"] == "full"
    spec = type("S", (), {"repository_root": repo, "executor_workdir": None,
                           "policy_snapshot": authority, "execution_id": "full"})()
    command = CodexExecutor(executable="/bin/true")._build_command(spec, authority)
    assert command[command.index("-C") + 1] == str(repo)

    scratch = tmp_path / "scratch"; scratch.mkdir()
    executor = AtlasBubblewrapExecutor(executable="/bin/true", bwrap="/bin/true",
                                       codex_home=tmp_path / "home")
    mount = executor._mount_command(spec, scratch, Path("/bin/true"))
    assert ["--ro-bind", str(repo.resolve()), str(repo.resolve())] == mount[-11:-8]
    assert mount[mount.index("--chdir") + 1] == str(repo.resolve())


def test_closed_admission_is_patch_review_fresh_only(tmp_path):
    repo, _ = make_repo(tmp_path)
    prompt, authority = snapshot(repo, visibility="closed")
    assert prompt.repository_visibility == "closed"
    assert authority["repository_visibility"] == "closed"
    assert authority["session_storage"] == "ephemeral"
    assert validate_snapshot(authority) is authority
    with pytest.raises(PromptError) as forbidden:
        parse_prompt(raw(repo, action="implementation", visibility="closed"))
    assert forbidden.value.code == "REPOSITORY_VISIBILITY_FORBIDDEN"
    with pytest.raises(PromptError) as reuse:
        parse_prompt(raw(repo, session="reuse", visibility="closed"))
    assert reuse.value.code == "CLOSED_SESSION_REUSE_FORBIDDEN"


def test_public_prompt_create_closed_is_accepted_v3_authority(
        tmp_path, monkeypatch, capsys):
    repo, workflow = make_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        "tools.atlas_agent.cli.Workflow", lambda: workflow)
    from tools.atlas_agent import cli

    class BinaryStdin:
        buffer = io.BytesIO(b"public closed review\n")

    monkeypatch.setattr(cli.sys, "stdin", BinaryStdin())
    assert cli.main([
        "prompt-create", "--checkpoint", "public-closed",
        "--action", "patch_review", "--repository-visibility", "closed",
    ]) == 0
    capsys.readouterr()
    candidate = next((workflow.base / "inbox").glob("g*.txt"))
    parsed = parse_prompt(candidate.read_bytes())
    assert parsed.prompt_schema == "atlas-agent-prompt/3"
    assert parsed.repository_visibility == "closed"

    assert cli.main(["ingest"]) == 0
    state = workflow._state()
    assert state["generations"]["1"]["status"] == "ACCEPTED"
    assert state["generations"]["1"]["repository_visibility"] == "closed"


def test_closed_requires_integrated_context_before_executor_preparation(tmp_path):
    repo, workflow = make_repo(tmp_path)
    (workflow.base / "inbox" / "closed.txt").write_bytes(raw(repo, visibility="closed"))
    workflow.ingest()

    class Never:
        def prepare_execution(self, spec):
            raise AssertionError("executor preparation must not be reached")

    with pytest.raises(WorkflowError, match="CLOSED_INTEGRATED_CONTEXT_REQUIRED"):
        workflow.execute(1, Never())


def test_closed_composition_without_diff_rejects_before_preparation(tmp_path):
    repo, workflow = make_repo(tmp_path)
    (workflow.base / "inbox" / "closed.txt").write_bytes(
        raw(repo, visibility="closed"))
    workflow.ingest()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    package = build_review_package(repo, head, "review\n", workflow.allowed)
    selection = package.pvc_context()
    task_id = next(
        tablet["id"] for tablet in
        selection.result.validated_snapshot.document["tablets"]
        if next(artifact["mediaType"] for artifact in
                selection.result.validated_snapshot.document["artifacts"]
                if artifact["artifactId"] == tablet["artifactId"]) ==
        "text/vnd.atlas.review-task")
    composition = PvcContextComposition((
        replace(selection, tablet_ids=(task_id,)),
    ))

    class Never(CodexExecutor):
        supports_authoritative_pvc_context = True
        supports_closed_repository_visibility = True

        def prepare_execution_with_pvc(self, spec, staged):
            raise AssertionError("executor preparation must not be reached")

    try:
        with pytest.raises(WorkflowError,
                           match="CLOSED_INTEGRATED_DIFF_REQUIRED"):
            workflow.execute(1, Never(), pvc_context=composition)
    finally:
        shutil.rmtree(selection.result.scratch_path)


class Capture(CodexExecutor):
    supports_authoritative_pvc_context = True
    supports_closed_repository_visibility = True
    def __init__(self):
        super().__init__(executable="/bin/true")
        self.spec = None
    def prepare_execution_with_pvc(self, spec, staged):
        self.spec = spec
        return PreparedExecution(spec, "capture", ("capture",), "capture/1",
                                 self._envelope(), spec.policy_snapshot)
    def run_execution(self, prepared):
        now = utc_now(); spec = prepared.spec
        return ExecutionResult(str(spec.execution_id), "capture", ["capture"], "capture/1",
            now, now, 0, "reports/x/out", "reports/x/err", "thread-closed", "success",
            "reports/x/result", prepared.permission_envelope,
            observed_model=spec.policy_snapshot["requested_model"],
            observed_reasoning=spec.policy_snapshot["requested_reasoning_effort"],
            execution_input_sha256=spec.expected_input_sha256)
    def execution_returned_quiescent(self, prepared, result): return True
    def abandon_prepared_execution(self, prepared): return True


def test_controller_acquires_real_repo_and_visibility_replays(tmp_path):
    repo, workflow = make_repo(tmp_path)
    sentinel = repo / "unselected-secret"; sentinel.write_text("controller-visible")
    old = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo,
                                  text=True).strip()
    subprocess.run(["git", "add", "unselected-secret"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "sentinel"], cwd=repo, check=True)
    new = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo,
                                  text=True).strip()
    workflow.adopt_boundary(old, new, "test sentinel")
    (workflow.base / "inbox" / "closed.txt").write_bytes(raw(repo, visibility="closed"))
    workflow.ingest()
    selection = build_review_package(repo, new, "review\n", workflow.allowed).pvc_context()
    composition = PvcContextComposition((selection,))
    executor = Capture()
    seen = []
    def acquire(target):
        seen.append(sentinel.read_text())
        return composition
    try:
        workflow.dispatch(executor=executor, pvc_context_provider=acquire)
        state = workflow._state()
        assert seen == ["controller-visible"]
        assert state["generations"]["1"]["repository_visibility"] == "closed"
        assert state["generations"]["1"]["execution"]["policy_snapshot"]["repository_visibility"] == "closed"
        assert workflow._replayed()[1]["generations"]["1"]["execution"]["policy_snapshot"]["repository_visibility"] == "closed"
    finally:
        shutil.rmtree(selection.result.scratch_path)


def test_closed_command_has_private_cwd_and_no_repository_mount(tmp_path):
    repo, _ = make_repo(tmp_path)
    _, authority = snapshot(repo, visibility="closed")
    scratch = tmp_path / "private-run"; scratch.mkdir()
    workdir = scratch / "workspace"; workdir.mkdir()
    spec = type("S", (), {"repository_root": repo, "executor_workdir": workdir,
                           "policy_snapshot": authority, "capability_plan": None,
                           "execution_id": "closed"})()
    codex = CodexExecutor(executable="/bin/true")
    outer = codex._build_command(spec, authority)
    assert outer[outer.index("-C") + 1] == str(workdir)
    assert str(repo) not in outer

    executor = AtlasBubblewrapExecutor(executable="/bin/true", bwrap="/bin/true",
                                       codex_home=tmp_path / "home")
    mount = executor._mount_command(spec, scratch, Path("/bin/true"))
    assert mount[mount.index("--chdir") + 1] == str(workdir.resolve())
    assert str(repo.resolve()) not in mount
    assert str((repo / ".git").resolve()) not in mount


def test_closed_rejects_repository_beneath_capability_host_mount(tmp_path):
    visible = tmp_path / "capability-host"
    repo, _ = make_repo(visible)
    _, authority = snapshot(repo, visibility="closed")
    scratch = tmp_path / "private-run"
    scratch.mkdir()
    workdir = scratch / "workspace"
    workdir.mkdir()
    capability = SimpleNamespace(
        mounts=(SimpleNamespace(host_root=visible),), caches=())
    spec = SimpleNamespace(
        repository_root=repo, executor_workdir=workdir,
        policy_snapshot=authority, capability_plan=capability,
        execution_id="closed")
    executor = AtlasBubblewrapExecutor(
        executable="/bin/true", bwrap="/bin/true",
        codex_home=tmp_path / "home")
    with pytest.raises(AtlasSandboxError,
                       match="ATLAS_CLOSED_REPOSITORY_MOUNT_OVERLAP"):
        executor._mount_command(spec, scratch, Path("/bin/true"))


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap unavailable")
def test_unselected_sentinel_is_unreachable_in_closed_namespace(tmp_path):
    repo, _ = make_repo(tmp_path)
    sentinel = repo / "unselected-secret"; sentinel.write_text("secret")
    _, authority = snapshot(repo, visibility="closed")
    scratch = tmp_path / "private-run"; scratch.mkdir()
    workdir = scratch / "workspace"; workdir.mkdir()
    spec = type("S", (), {"repository_root": repo, "executor_workdir": workdir,
                           "policy_snapshot": authority, "capability_plan": None,
                           "execution_id": "closed"})()
    executor = AtlasBubblewrapExecutor(executable="/bin/true", bwrap="bwrap",
                                       codex_home=tmp_path / "home")
    # Production preparation copies qualified assets into the run before the
    # mount command is built; avoid fallback host projections in this probe.
    (scratch / "atlas-sol-local.config.toml").touch()
    (scratch / "atlas-agent-prompts").mkdir()
    command = executor._mount_command(spec, scratch, Path("/bin/true"))
    command = command[:command.index("--")] + ["--", "/bin/sh", "-c",
        f'test "$PWD" = {str(workdir)!r} && ! test -e {str(sentinel)!r} && ! test -e {str(repo / ".git")!r}']
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0 and b"Operation not permitted" in result.stderr:
        pytest.skip("bubblewrap namespace unavailable")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")

def test_closed_prelaunch_failure_cleans_private_workdir(tmp_path, monkeypatch):
    """Closed workdir remains under the existing preparation ownership barrier."""
    repo, _ = make_repo(tmp_path)
    _, authority = snapshot(repo, visibility="closed")
    prompt_path = repo / "prompt"; prompt_path.write_bytes(b"review")
    from tools.atlas_agent.executor import ExecutionSpec
    spec = ExecutionSpec(1, hashlib.sha256(b"review").hexdigest(), "patch_review",
        prompt_path, repo, "closed-cleanup", tmp_path / "reports", tmp_path,
        policy_snapshot=authority, prompt_bytes=b"review", input_mode="bytes-v1",
        expected_input_sha256=hashlib.sha256(b"review").hexdigest())
    executor = AtlasBubblewrapExecutor(executable="/bin/true", bwrap="/bin/true",
        codex_home=tmp_path / "home", scratch_root=tmp_path / "scratch-store")
    monkeypatch.setattr(executor, "_validate_disk_scratch", lambda: None)
    monkeypatch.setattr(executor, "_scratch_probe", lambda scratch: None)
    monkeypatch.setattr(executor, "_validate_namespace", lambda: None)
    monkeypatch.setattr(executor, "_bwrap_version", lambda: "test")
    monkeypatch.setattr("tools.atlas_agent.bubblewrap._native_codex",
                        lambda executable: Path("/bin/true"))
    def fail_after_workdir(self, effective):
        assert effective.executor_workdir.is_dir()
        assert effective.executor_workdir.parent == executor._scratch
        raise RuntimeError("prelaunch failure")
    monkeypatch.setattr(CodexExecutor, "prepare_execution", fail_after_workdir)
    with pytest.raises(RuntimeError, match="prelaunch failure"):
        executor.prepare_execution(spec)
    assert not (executor.scratch_store.runs / "closed-cleanup").exists()
    assert not executor._run_lock.locked()
