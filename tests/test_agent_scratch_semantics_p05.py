"""Executable P0.5 scratch contract.

This file deliberately describes the next (frozen) sandbox boundary.  It is
allowed to be red until the corresponding executor changes land.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.atlas_agent.bubblewrap import (
    AtlasBubblewrapExecutor,
    AtlasSandboxError,
    ScratchStore,
)
from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.cli import DispatchPresenter
from tools.atlas_agent.executor import ExecutionSpec, PreparedExecution


def _spec(tmp_path, action="patch_review"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "prompt").write_text("prompt")
    (repo / "tracked").write_text("before")
    return ExecutionSpec(
        1, "0" * 64, action, repo / "prompt", repo, "p05-run",
        tmp_path / "report", tmp_path / "runtime",
        policy_snapshot={"codex_binary_sha256": "0" * 64},
    )


def _mount(executor, spec, tmp_path):
    scratch = executor.scratch_store.create(spec.execution_id)
    return scratch, executor._mount_command(spec, scratch, Path("/bin/true"))


def _shell_command(command, script):
    """Retain every production mount argument, replacing only the payload."""
    separator = command.index("--")
    return command[:separator] + ["--", "/bin/sh", "-c", script]


def _live_run(command):
    result = subprocess.run(command, text=True, capture_output=True, timeout=8)
    if result.returncode and any(
        word in result.stderr.lower()
        for word in ("user namespace", "operation not permitted", "permission denied")
    ):
        pytest.skip(result.stderr.strip()[:240])
    return result


@pytest.fixture
def disk_backed_scratch_root():
    """Provide an isolated ScratchStore root on a non-tmpfs host filesystem."""
    try:
        root = Path(tempfile.mkdtemp(prefix="atlas-agent-p05-", dir="/var/tmp"))
    except OSError as error:
        pytest.skip(f"host /var/tmp is unavailable: {error}")
    try:
        filesystem = subprocess.run(
            ["stat", "-f", "-c", "%T", str(root)],
            text=True, capture_output=True, check=False,
        )
        if filesystem.returncode != 0 or filesystem.stdout.strip() == "tmpfs":
            shutil.rmtree(root, ignore_errors=True)
            pytest.skip("host /var/tmp does not provide writable non-tmpfs storage")
        if not os.access(root, os.W_OK):
            shutil.rmtree(root, ignore_errors=True)
            pytest.skip("host /var/tmp is not writable")
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_production_mount_argv_has_canonical_private_storage_for_both_modes(
    tmp_path, monkeypatch
):
    """The assertion is against AtlasBubblewrapExecutor, not a hand-built bwrap."""
    for action, sandbox in (("patch_review", "read-only"),
                            ("implementation", "workspace-write")):
        spec = _spec(tmp_path / action, action)
        executor = AtlasBubblewrapExecutor(
            sandbox=sandbox, executable="/bin/true", scratch_root=tmp_path / "store" / action
        )
        (tmp_path / "store" / action).mkdir(parents=True, exist_ok=True)
        # This test is about argv topology; avoid requiring an installed Codex image.
        monkeypatch.setattr(executor, "_validate_writable_namespace", lambda root: None)
        scratch, command = _mount(executor, spec, tmp_path)
        try:
            assert command[command.index("--tmpfs") + 1] == "/dev/shm"
            assert ["--tmpfs", "/tmp"] in [
                command[i:i + 2] for i in range(len(command) - 1)
            ]
            assert ["--tmpfs", "/home"] in [
                command[i:i + 2] for i in range(len(command) - 1)
            ]
            assert ["--bind", str(scratch), "/var/tmp"] in [
                command[i:i + 3] for i in range(len(command) - 2)
            ]
            assert "/var/tmp/atlas-agent" not in command
            forbidden = {str(executor.scratch_store.root), str(executor.scratch_store.control),
                         str(executor.scratch_store.runs), str(Path("/var/tmp"))}
            assert not any(
                command[i] == "--bind" and command[i + 1] in forbidden
                for i in range(len(command) - 1)
            )
            repo_bind = next(
                i for i, value in enumerate(command)
                if value in {"--bind", "--ro-bind"} and value == command[i]
                and i + 2 < len(command) and command[i + 2] == str(spec.repository_root)
            )
            assert command[repo_bind] == ("--bind" if sandbox == "workspace-write" else "--ro-bind")
            if sandbox == "workspace-write":
                assert ["--ro-bind", str(spec.repository_root / ".git"),
                        str(spec.repository_root / ".git")] in [
                    command[i:i + 3] for i in range(len(command) - 2)
                ]
        finally:
            executor.scratch_store.cleanup(scratch)


def test_generated_sandbox_environment_is_exact_and_ambient_temps_do_not_leak(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TMPDIR", "/host/tmp")
    monkeypatch.setenv("TMP", "/host/tmp2")
    monkeypatch.setenv("TEMP", "/host/tmp3")
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(executable="/bin/true",
                                       scratch_root=tmp_path / "store")
    monkeypatch.setattr(executor, "_validate_writable_namespace", lambda root: None)
    scratch, command = _mount(executor, spec, tmp_path)
    try:
        result = _live_run(_shell_command(command, r'''
set -eu
[ "$HOME" = /home/atlas ]
[ "$TMPDIR" = /tmp ] && [ "$TMP" = /tmp ] && [ "$TEMP" = /tmp ]
[ "$(env | grep -Ec '^(TMPDIR|TMP|TEMP)=')" -eq 3 ]
! env | grep -E '^ATLAS_.*SCRATCH|^HOST_HOME='
'''))
        assert result.returncode == 0, result.stderr
    finally:
        executor.scratch_store.cleanup(scratch)


def test_live_production_topology_reaches_current_run_and_keeps_storage_distinct(
    tmp_path, disk_backed_scratch_root
):
    if not Path("/usr/bin/bwrap").exists() and not __import__("shutil").which("bwrap"):
        pytest.skip("bubblewrap unavailable")
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(executable="/bin/true",
                                       scratch_root=disk_backed_scratch_root / "store")
    scratch, command = _mount(executor, spec, tmp_path)
    marker = "current-run"
    try:
        result = _live_run(_shell_command(command, f'''
set -eu
test -w /tmp; test -w /var/tmp; test -w /home/atlas
test "$(stat -f -c %T /tmp)" = tmpfs
test "$(stat -f -c %T /var/tmp)" != tmpfs
printf x >/tmp/{marker}; printf x >/var/tmp/{marker}
'''))
        assert result.returncode == 0, result.stderr
        assert (scratch / marker).read_text() == "x"
        assert not (executor.scratch_store.control / marker).exists()
        assert not (executor.scratch_store.runs / marker).exists()
    finally:
        executor.scratch_store.cleanup(scratch)


def test_workspace_mode_only_changes_repository_bind_not_temporary_storage(tmp_path):
    if not __import__("shutil").which("bwrap"):
        pytest.skip("bubblewrap unavailable")
    for action, sandbox, repository_write in (
        ("review", "read-only", "denied"),
        ("implementation", "workspace-write", "allowed"),
    ):
        spec = _spec(tmp_path / action, "patch_review" if sandbox == "read-only"
                     else "implementation")
        executor = AtlasBubblewrapExecutor(
            sandbox=sandbox, executable="/bin/true",
            scratch_root=tmp_path / "store" / action,
        )
        (tmp_path / "store" / action).mkdir(parents=True, exist_ok=True)
        scratch, command = _mount(executor, spec, tmp_path)
        try:
            workspace = str(spec.repository_root)
            result = _live_run(_shell_command(command, f'''
set -eu
test -w /tmp; test -w /var/tmp; test -w /home/atlas
if test "{repository_write}" = allowed; then
  printf changed >"{workspace}/tracked"
else
  ! printf changed >"{workspace}/tracked" 2>/dev/null
fi
! printf changed >"{workspace}/.git/index" 2>/dev/null
'''))
            assert result.returncode == 0, result.stderr
        finally:
            executor.scratch_store.cleanup(scratch)


def test_sequential_runs_cannot_observe_previous_sibling_control_or_host(tmp_path):
    store = ScratchStore(tmp_path / "store")
    host = tmp_path / "host-only"
    host.write_text("secret")
    first = store.create("first")
    (first / "previous").write_text("old")
    second = store.create("second")
    try:
        assert not (second / "previous").exists()
        assert not (second / store.MARKER).exists()
        assert not (second / "host-only").exists()
        assert (store.control / "first").is_file()
        assert (store.runs / "first").is_dir()
    finally:
        store.cleanup(first)
        store.cleanup(second)


@pytest.mark.parametrize("terminal_path", ["success", "executor-exception"])
def test_positive_reap_removes_execution_owned_scratch(tmp_path, terminal_path):
    store = ScratchStore(tmp_path / "store")
    run = store.create("reaped-" + terminal_path)
    (run / "temporary").write_text(terminal_path)
    # Both normal completion and an exception/interruption that reaches the
    # owning lifecycle have the same positive-reap obligation.
    store.cleanup(run)
    assert not run.exists()
    assert not (store.control / run.name).exists()


def test_descriptor_and_executor_info_publish_frozen_scratch_contract(tmp_path):
    executor = AtlasBubblewrapExecutor(executable="/bin/true",
                                       scratch_root=tmp_path / "store")
    executor._descriptor = {
        "temporary_storage": {"tmp": "private-tmpfs", "shm": "private-tmpfs",
                              "var_tmp": "private-disk-scratch"},
        "scratch_backing_class": "disk",
    }
    descriptor = executor.sandbox_descriptor()
    assert descriptor["temporary_storage"]["var_tmp"] == "private-disk-scratch"
    info = executor.info()
    contract = info["scratch_contract"]
    assert contract["canonical_disk_path"] == "/var/tmp"
    assert contract["memory"] == {
        "path": "/tmp", "writable": True, "backing": "tmpfs",
        "scope": "execution", "lifetime": "terminal-cleanup",
    }
    assert contract["disk"] == {
        "path": "/var/tmp", "writable": True, "backing": "host-filesystem-non-tmpfs",
        "scope": "execution", "lifetime": "terminal-cleanup",
    }
    assert contract["environment"] == {"TMPDIR": "/tmp", "TMP": "/tmp", "TEMP": "/tmp"}
    assert contract["verification"] == "per-execution-write-probe-before-run-started"


def test_dispatch_presents_canonical_temporary_storage(capsys):
    DispatchPresenter().event({
        "kind": "dispatch_started", "generation": 1, "action": "implementation",
        "permission_envelope": {"sandbox_mode": "workspace-write", "network_access": False},
        "sandbox": {"backend": "bubblewrap", "filesystem_mode": "workspace-write"},
    })
    output = capsys.readouterr().out
    assert "temporary: /tmp writable tmpfs · /var/tmp writable disk-backed scratch (private, per execution)" in output
    assert "temp env: TMPDIR=/tmp · TMP=/tmp · TEMP=/tmp" in output
    assert "tmp memory · var/tmp disk" not in output


def test_pre_run_failure_abandons_prepared_execution_resources(tmp_path):
    executor = AtlasBubblewrapExecutor(executable="/bin/true",
                                       scratch_root=tmp_path / "store")
    prepared = PreparedExecution(_spec(tmp_path), "atlas", ("atlas",), "v", {}, {})
    assert hasattr(executor, "abandon_prepared_execution")
    executor.abandon_prepared_execution(prepared)
    assert not (tmp_path / "store" / "runs").exists()


def test_executor_handoff_keyboard_interrupt_has_one_owner(tmp_path, monkeypatch):
    """An interrupt in the executor's first protected phase is not ownerless."""
    executor = AtlasBubblewrapExecutor(
        executable="/bin/true", scratch_root=tmp_path / "store"
    )
    descriptor = object()
    executor._descriptor = descriptor
    specs = [_spec(tmp_path / name) for name in ("first", "second")]
    specs[1] = replace(specs[1], execution_id="p05-second")

    def prepare_locked(spec):
        scratch = executor.scratch_store.create(spec.execution_id)
        executor._scratch = scratch
        return PreparedExecution(spec, "atlas-test", ("/bin/true",), "test", {}, None, descriptor)

    monkeypatch.setattr(executor, "_prepare_execution_locked", prepare_locked)
    cleanups = []
    cleanup = executor.scratch_store.cleanup
    monkeypatch.setattr(
        executor.scratch_store, "cleanup",
        lambda path: (cleanups.append(path), cleanup(path))[1],
    )
    started = []
    monkeypatch.setattr(
        executor, "_validate_runtime_identity",
        lambda snapshot: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(executor, "_start_server", lambda spec, fd: started.append(spec))
    prepared = executor.prepare_execution(specs[0])
    with pytest.raises(KeyboardInterrupt):
        executor.run_execution(prepared)

    assert len(cleanups) == 1
    assert not started
    assert not (executor.scratch_store.runs / specs[0].execution_id).exists()
    assert not executor._run_lock.locked()
    # The workflow-side fallback may be invoked after executor ownership has
    # transferred, but must not perform a second cleanup.
    executor.abandon_prepared_execution(prepared)
    assert len(cleanups) == 1

    monkeypatch.setattr(executor, "_validate_runtime_identity", lambda snapshot: None)
    monkeypatch.setattr(executor, "_sealed_runtime_fd", lambda snapshot: None)
    monkeypatch.setattr(executor, "_validate_sealed_runtime_fd", lambda fd, snapshot: None)
    monkeypatch.setattr(executor, "_start_server", lambda spec, fd: None)
    monkeypatch.setattr(
        CodexExecutor,
        "run_execution",
        lambda self, prepared, _runtime_binary_fd=None: SimpleNamespace(
            timed_out=False, exit_code=0, outcome="success"
        ),
    )
    second = executor.prepare_execution(specs[1])
    executor.run_execution(second)
    assert not (executor.scratch_store.runs / specs[1].execution_id).exists()
    assert not executor._run_lock.locked()


def test_executor_handoff_gap_is_already_inside_cleanup_scope(tmp_path, monkeypatch):
    """A failure at the former post-handoff gap still reaches executor teardown."""
    import inspect

    executor = AtlasBubblewrapExecutor(
        executable="/bin/true", scratch_root=tmp_path / "store"
    )
    descriptor = object()
    executor._descriptor = descriptor
    spec = _spec(tmp_path / "gap")
    prepared = None

    def prepare_locked(value):
        scratch = executor.scratch_store.create(value.execution_id)
        executor._scratch = scratch
        return PreparedExecution(
            value, "atlas-test", ("/bin/true",), "test", {}, {}, descriptor
        )

    monkeypatch.setattr(executor, "_prepare_execution_locked", prepare_locked)
    prepared = executor.prepare_execution(spec)
    assert executor._scratch is not None

    stop_calls = []
    stop_server = executor._stop_server

    def tracked_stop():
        stop_calls.append((executor._server, executor._scratch))
        return stop_server()

    monkeypatch.setattr(executor, "_stop_server", tracked_stop)
    monkeypatch.setattr(
        executor, "_validate_runtime_identity",
        lambda snapshot: (_ for _ in ()).throw(RuntimeError("execution witness")),
    )
    source, first_line = inspect.getsourcelines(executor.run_execution)
    # Inject at the transition from the protected execution body to teardown.
    # In the old layout, this was the first line of the separate cleanup
    # try: ownership had already transferred, but that try was not entered.
    former_gap = next(
        first_line + offset for offset, text in enumerate(source)
        if "primary=error" in text.replace(" ", "")
    )
    reached = []

    def inject(frame, event, arg):
        if (frame.f_code is executor.run_execution.__code__ and event == "line"
                and frame.f_lineno == former_gap
                and executor._execution_ownership_transferred):
            reached.append(True)
            sys.settrace(None)
            raise KeyboardInterrupt("former ownership gap")
        return inject

    sys.settrace(inject)
    try:
        with pytest.raises(KeyboardInterrupt, match="former ownership gap"):
            executor.run_execution(prepared)
    finally:
        sys.settrace(None)

    assert reached
    assert executor._execution_ownership_transferred
    assert len(stop_calls) == 1
    assert stop_calls[0][0] is None
    assert not (executor.scratch_store.runs / spec.execution_id).exists()
    assert not executor._run_lock.locked()
    executor.abandon_prepared_execution(prepared)
    assert len(stop_calls) == 1
    monkeypatch.setattr(executor, "_validate_runtime_identity", lambda snapshot: None)
    monkeypatch.setattr(executor, "_sealed_runtime_fd", lambda snapshot: None)
    monkeypatch.setattr(executor, "_validate_sealed_runtime_fd",
                        lambda fd, snapshot: None)
    monkeypatch.setattr(executor, "_start_server", lambda spec, fd: None)
    monkeypatch.setattr(
        CodexExecutor, "run_execution",
        lambda self, prepared, _runtime_binary_fd=None: SimpleNamespace(
            timed_out=False, exit_code=0, outcome="success"
        ),
    )
    next_spec = replace(spec, execution_id="p05-gap-followup")
    followup = executor.prepare_execution(next_spec)
    executor.run_execution(followup)
    assert not (executor.scratch_store.runs / next_spec.execution_id).exists()
    assert not executor._run_lock.locked()


@pytest.mark.parametrize("failure", ["creation", "backing", "mount", "probe"])
def test_scratch_preparation_failures_fail_closed_before_run_started(tmp_path, monkeypatch, failure):
    """Each named seam is a controller-side failure, never a model failure."""
    executor = AtlasBubblewrapExecutor(executable="/bin/true",
                                       scratch_root=tmp_path / "store")
    assert hasattr(executor, "_prepare_scratch")
    with pytest.raises(AtlasSandboxError, match="ATLAS_SANDBOX_SCRATCH_PROBE_FAILED"):
        executor._prepare_scratch(failure)
    assert not (tmp_path / "store" / "runs").exists()


@pytest.mark.parametrize("failure", [RuntimeError("witness recheck failed"), KeyboardInterrupt()])
def test_workflow_abandons_real_prepared_run_before_ownership_transfer(
    tmp_path, monkeypatch, failure
):
    """A post-prepare controller failure releases the actual run authority."""
    from test_agent_workflow_w221 import accepted, make_repo
    from tools.atlas_agent.executor import ExecutionResult

    _, workflow = make_repo(tmp_path)

    class ScratchExecutor(AtlasBubblewrapExecutor):
        def __init__(self):
            super().__init__(executable="/bin/true", scratch_root=tmp_path / "store")
            self.prepared_ids = []
            self.run_called = False
            self.allow_run = False

        def prepare_execution(self, spec):
            assert self._run_lock.acquire(blocking=False)
            scratch = self.scratch_store.create(str(spec.execution_id))
            self._scratch = scratch
            self.prepared_ids.append(str(spec.execution_id))
            snapshot = spec.policy_snapshot
            envelope = {
                "sandbox_mode": snapshot["sandbox_mode"],
                "approval_policy": "never", "approvals_reviewer": "user",
                "strict_config": True, "ignore_rules": True,
                "network_access": snapshot["network_access"],
            }
            return PreparedExecution(
                spec, "atlas-test", ("/bin/true",), "test", envelope, {},
            )

        def abandon_prepared_execution(self, prepared):
            self.scratch_store.cleanup(self._scratch)
            self._scratch = None
            self._run_lock.release()

        def post_start_prepare(self, prepared):
            return prepared

        def run_execution(self, prepared):
            self.run_called = True
            if not self.allow_run:
                raise AssertionError("model workload must not start")
            result = ExecutionResult(
                prepared.spec.execution_id, "atlas-test", list(prepared.command), "test",
                "now", "now", 0, "", "", "test-session", "success", "",
                execution_input_sha256=prepared.spec.expected_input_sha256,
            )
            self.scratch_store.cleanup(self._scratch)
            self._scratch = None
            self._run_lock.release()
            return result

    executor = ScratchExecutor()
    accepted(workflow)
    original = workflow._validate_authoritative_provenance

    def injected_failure(*args):
        raise failure

    monkeypatch.setattr(workflow, "_validate_authoritative_provenance", injected_failure)
    with pytest.raises(type(failure), match=str(failure) if str(failure) else None):
        workflow.execute(1, executor)

    assert executor.prepared_ids
    assert not executor.run_called
    assert not any(event["event"] == "RUN_STARTED" for event in workflow.journal.read())
    assert not (executor.scratch_store.runs / executor.prepared_ids[0]).exists()
    assert not (executor.scratch_store.control / executor.prepared_ids[0]).exists()
    assert executor._run_lock.acquire(blocking=False)
    executor._run_lock.release()

    monkeypatch.setattr(workflow, "_validate_authoritative_provenance", original)
    # Reuse the same executor: a valid subsequent preparation proves that the
    # workflow resolved, rather than merely hid, the prior preparation owner.
    executor.allow_run = True
    workflow.execute(1, executor)
    assert len(executor.prepared_ids) == 2
