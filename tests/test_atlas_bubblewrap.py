import hashlib
import io
import os
import subprocess
import time
from pathlib import Path

import pytest

from tools.atlas_agent.bubblewrap import AtlasBubblewrapExecutor, AtlasSandboxError, ScratchStore, _native_codex
from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionSpec, PreparedExecution


def _spec(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "prompt").write_bytes(b"hello")
    return ExecutionSpec(1, hashlib.sha256(b"hello").hexdigest(), "patch_review", root / "prompt",
                         root, "execution-test", tmp_path / "report", tmp_path / "runtime",
                         input_mode="bytes-v1", prompt_bytes=b"hello",
                         expected_input_sha256=hashlib.sha256(b"hello").hexdigest())



def _stub_codex_prepare(monkeypatch):
    """Unit-isolate Bubblewrap from the authenticated Codex preparation layer."""
    def prepare(self, spec):
        envelope = {
            "sandbox_mode": self.sandbox,
            "approval_policy": "never",
            "approvals_reviewer": "user",
            "strict_config": True,
            "ignore_rules": True,
            "network_access": self.network_access,
        }
        return PreparedExecution(
            spec,
            "codex",
            (str(self.executable),),
            "codex/test",
            envelope,
            spec.policy_snapshot,
        )

    monkeypatch.setattr(CodexExecutor, "prepare_execution", prepare)


def test_scratch_store_requires_positive_ownership(tmp_path):
    store = ScratchStore(tmp_path / "atlas-agent")
    path = store.create("run-a")
    assert store.owned(path)
    store.cleanup(path)
    assert not path.exists()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    with pytest.raises(AtlasSandboxError, match="SCRATCH_NOT_OWNED"):
        store.cleanup(foreign)


def test_stale_scratch_is_not_removed_by_new_run(tmp_path):
    store = ScratchStore(tmp_path / "atlas-agent")
    stale = store.root / "runs" / "crashed-run"
    stale.mkdir(parents=True)
    (stale / "data").write_text("keep")
    store.create("new-run")
    assert (stale / "data").read_text() == "keep"
    assert stale.is_dir()


def test_scratch_collision_fails_closed_without_touching_existing_tree(tmp_path):
    store = ScratchStore(tmp_path / "atlas-agent")
    existing = store.root / "runs" / "run-a"
    (existing / "sentinel" / "nested").mkdir(parents=True)
    (existing / "sentinel" / "nested" / "keep").write_text("untouched")
    (store.root / "control").mkdir(parents=True)
    (store.root / "control" / "run-a").write_text("foreign metadata")
    before = sorted((p.relative_to(existing), p.read_bytes() if p.is_file() else None)
                    for p in existing.rglob("*"))
    with pytest.raises(AtlasSandboxError, match="SCRATCH_COLLISION"):
        store.create("run-a")
    after = sorted((p.relative_to(existing), p.read_bytes() if p.is_file() else None)
                   for p in existing.rglob("*"))
    assert after == before
    assert (store.root / "control" / "run-a").read_text() == "foreign metadata"


def test_current_run_cleanup_rejects_replaced_inode(tmp_path):
    store = ScratchStore(tmp_path / "atlas-agent")
    run = store.create("run-a")
    (run / "original").write_text("original")
    moved = tmp_path / "moved-original"
    run.rename(moved)
    replacement = store.runs / "run-a"
    replacement.mkdir()
    (replacement / "sentinel").write_text("keep")
    with pytest.raises(AtlasSandboxError, match="SCRATCH_CLEANUP_FAILED|SCRATCH_CHANGED"):
        store.cleanup(run)
    assert (replacement / "sentinel").read_text() == "keep"
    assert (moved / "original").read_text() == "original"


def test_mount_plan_has_distinct_storage_and_readonly_git(tmp_path, monkeypatch):
    _stub_codex_prepare(monkeypatch)
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    native = _native_codex(executor.executable)
    if native is None:
        pytest.skip("installed native Codex unavailable")
    monkeypatch.setattr(executor, "_filesystem_class", lambda path: "disk")
    executor.prepare_execution(spec)
    command = executor._mount_command(spec, tmp_path / "scratch" / "execution-test", 32123)
    text = " ".join(command)
    assert "--tmpfs /tmp" in text
    assert "--tmpfs /dev/shm" in text
    assert str(tmp_path / "scratch" / "execution-test") in text
    assert "--unshare-pid" in command and "--unshare-ipc" in command
    assert "--clearenv" in command
    assert "--ro-bind" in command
    repo_bind = next(i for i, value in enumerate(command)
                     if value == "--ro-bind" and command[i + 1] == str(spec.repository_root))
    assert repo_bind >= 0
    assert "--unshare-net" not in command


def test_implementation_mount_keeps_git_metadata_readonly(tmp_path, monkeypatch):
    _stub_codex_prepare(monkeypatch)
    spec = _spec(tmp_path)
    spec = spec.__class__(**{**spec.__dict__, "action": "implementation"})
    executor = AtlasBubblewrapExecutor(sandbox="workspace-write", scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_filesystem_class", lambda path: "disk")
    executor.prepare_execution(spec)
    command = executor._mount_command(spec, tmp_path / "scratch" / "execution-test", 32123)
    repo_bind = next(i for i, value in enumerate(command)
                     if value == "--bind" and command[i + 1] == str(spec.repository_root))
    assert command[repo_bind + 1] == str(spec.repository_root)
    assert str(spec.repository_root / ".git") in command


def test_network_enabled_is_supported_by_sandbox_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tools.atlas_agent.bubblewrap._native_codex",
        lambda _: Path("/bin/true"),
    )
    executor = AtlasBubblewrapExecutor(
        executable="/bin/true",
        bwrap="/bin/true",
        network_access=True,
        scratch_root=tmp_path / "scratch",
    )
    executor._validate_policy()
    assert not (tmp_path / "scratch").exists()



@pytest.mark.parametrize("action", ["patch_review", "state_audit"])
def test_restricted_actions_reject_network_before_sandbox_launch(tmp_path, monkeypatch, action):
    _stub_codex_prepare(monkeypatch)
    from dataclasses import replace
    spec=replace(_spec(tmp_path), action=action)
    executor=AtlasBubblewrapExecutor(network_access=True, scratch_root=tmp_path/"scratch")
    with pytest.raises(AtlasSandboxError, match="ATLAS_SANDBOX_ACTION_NETWORK_MISMATCH"):
        executor.prepare_execution(spec)

def test_descriptor_distinguishes_enforcement_layers(tmp_path, monkeypatch):
    _stub_codex_prepare(monkeypatch)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_filesystem_class", lambda path: "disk")
    executor.prepare_execution(_spec(tmp_path))
    descriptor = executor.sandbox_descriptor()
    assert descriptor["filesystem_enforcement"] == "atlas-bwrap"
    assert descriptor["process_enforcement"] == "atlas-bwrap"
    assert descriptor["network_enforcement"] == "codex"
    assert descriptor["temporary_storage"] == {
        "tmp": "private-tmpfs", "shm": "private-tmpfs", "var_tmp": "private-disk-scratch"}


def test_tmpfs_scratch_is_rejected(tmp_path, monkeypatch):
    _stub_codex_prepare(monkeypatch)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_filesystem_class", lambda path: "tmpfs")
    with pytest.raises(AtlasSandboxError, match="DISK_SCRATCH_REQUIRED"):
        executor.prepare_execution(_spec(tmp_path))


def test_scratch_control_is_not_child_visible(tmp_path):
    store = ScratchStore(tmp_path / "scratch")
    run = store.create("run-a")
    assert (store.control / "run-a").is_file()
    assert not (run / store.MARKER).exists()


def test_action_mode_is_bound_before_launch(tmp_path, monkeypatch):
    _stub_codex_prepare(monkeypatch)
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(sandbox="workspace-write", scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_filesystem_class", lambda path: "disk")
    with pytest.raises(AtlasSandboxError, match="ACTION_MODE_MISMATCH"):
        executor.prepare_execution(spec)


@pytest.fixture
def pinned_runtime_fd():
    fd = os.open("/usr/bin/true", os.O_RDONLY | os.O_CLOEXEC)
    try:
        yield fd
    finally:
        os.close(fd)


def test_server_command_uses_child_assigned_port(tmp_path, monkeypatch, pinned_runtime_fd):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_filesystem_class", lambda path: "disk")
    command = executor._mount_command(
        spec, tmp_path / "scratch" / "run-a", pinned_runtime_fd
    )
    assert "ws://127.0.0.1:0" in command
    assert "--exit-on-stdin-close" in command
    assert not any(value == "--listen" and command[i + 1] != "ws://127.0.0.1:0" for i, value in enumerate(command[:-1]))


class _StartupProcess:
    def __init__(self, output):
        self.stdin = io.BytesIO()
        read_fd, write_fd = os.pipe()
        os.write(write_fd, output)
        os.close(write_fd)
        self.stdout = os.fdopen(read_fd, "rb")
        self.stderr = io.BytesIO()
        self.pid = 12345

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


class _OpenStartupProcess(_StartupProcess):
    def __init__(self):
        self.stdin = io.BytesIO()
        read_fd, self.write_fd = os.pipe()
        os.write(self.write_fd, b"ws://127.0.0.1:43210")
        self.stdout = os.fdopen(read_fd, "rb")
        self.stderr = io.BytesIO()
        self.pid = 12345

    def wait(self, timeout=None):
        os.close(self.write_fd)
        return 0


@pytest.mark.parametrize("output", [
    b"prefix ws://127.0.0.1:1234\n",
    b"ws://127.0.0.1:1234 trailing\n",
    b"ws://192.0.2.1:1234\n",
    b"ws://127.0.0.1:0\n",
    b"ws://127.0.0.1:1234\nws://127.0.0.1:1235\n",
    b"not an endpoint\n",
    b"",
])
def test_exec_server_accepts_only_one_exact_endpoint(
    tmp_path, monkeypatch, output, pinned_runtime_fd
):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(
        executor, "_mount_command",
        lambda spec, scratch, runtime_fd: ["fake"],
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: _StartupProcess(output))
    with pytest.raises(AtlasSandboxError):
        executor._start_server(spec, pinned_runtime_fd)
    assert not (tmp_path / "scratch" / "runs" / "execution-test").exists()


def test_exec_server_accepts_exact_loopback_endpoint(
    tmp_path, monkeypatch, pinned_runtime_fd
):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(
        executor, "_mount_command",
        lambda spec, scratch, runtime_fd: ["fake"],
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: _StartupProcess(b"ws://127.0.0.1:1234\n"))
    executor._start_server(spec, pinned_runtime_fd)
    assert executor._server_url == "ws://127.0.0.1:1234"
    executor._stop_server()


def test_exec_server_partial_endpoint_hits_startup_deadline(
    tmp_path, monkeypatch, pinned_runtime_fd
):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    executor.STARTUP_TIMEOUT_SECONDS = .1
    monkeypatch.setattr(
        executor, "_mount_command",
        lambda spec, scratch, runtime_fd: ["fake"],
    )
    process = _OpenStartupProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    started = time.monotonic()
    with pytest.raises(AtlasSandboxError, match="URL_UNAVAILABLE"):
        executor._start_server(spec, pinned_runtime_fd)
    assert time.monotonic() - started < 1
    assert not (tmp_path / "scratch" / "runs" / "execution-test").exists()


class TeardownError(RuntimeError): pass
class CleanupError(ValueError): pass


@pytest.mark.parametrize("execution,teardown,cleanup", [
    (RuntimeError("execution E"), TeardownError("teardown T"), CleanupError("cleanup C")),
    (None, TeardownError("teardown T"), CleanupError("cleanup C")),
    (None, None, CleanupError("cleanup C")),
])
def test_all_failure_diagnostics_are_concrete(
    tmp_path, monkeypatch, execution, teardown, cleanup, pinned_runtime_fd
):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_validate_runtime_identity", lambda snapshot: None)
    executor._descriptor = object()
    prepared = PreparedExecution(spec, "atlas", (), "test", {}, None, executor._descriptor)
    monkeypatch.setattr(
        executor, "_sealed_runtime_fd",
        lambda snapshot: os.dup(pinned_runtime_fd),
    )
    monkeypatch.setattr(
        executor, "_validate_sealed_runtime_fd",
        lambda fd, snapshot: None,
    )
    monkeypatch.setattr(executor, "_start_server", lambda spec, runtime_fd: None)
    monkeypatch.setattr(
        CodexExecutor,
        "run_execution",
        lambda self, prepared, _runtime_binary_fd=None:
            (_ for _ in ()).throw(execution) if execution else object(),
    )
    def stop():
        if teardown:
            raise teardown
        if cleanup:
            raise cleanup
    # A teardown failure carrying cleanup is the same contract as _stop_server.
    if teardown and cleanup:
        teardown.add_note(f"cleanup: {type(cleanup).__name__}: {cleanup}")
    monkeypatch.setattr(executor, "_stop_server", stop)
    assert executor._run_lock.acquire()
    try:
        with pytest.raises((RuntimeError, TeardownError, CleanupError)) as raised:
            executor.run_execution(prepared)
    finally:
        if executor._run_lock.locked(): executor._run_lock.release()
    text = " ".join(getattr(raised.value, "__notes__", ()))
    if execution:
        assert raised.value is execution
        assert "TeardownError" in text and "teardown T" in text
        assert "CleanupError" in text and "cleanup C" in text
    elif teardown:
        assert raised.value is teardown
        assert "CleanupError" in text and "cleanup C" in text
    else:
        assert raised.value is cleanup


def test_execution_teardown_and_cleanup_keep_all_types(
    tmp_path, monkeypatch, pinned_runtime_fd
):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_validate_runtime_identity", lambda snapshot: None)
    executor._descriptor = object()
    prepared = PreparedExecution(spec, "atlas", (), "test", {}, None, executor._descriptor)
    class Server:
        stderr = io.BytesIO()
        def wait(self, timeout=None): raise TeardownError("teardown T")
    executor._server = Server(); executor._scratch = tmp_path / "scratch" / "run"
    monkeypatch.setattr(
        executor, "_sealed_runtime_fd",
        lambda snapshot: os.dup(pinned_runtime_fd),
    )
    monkeypatch.setattr(
        executor, "_validate_sealed_runtime_fd",
        lambda fd, snapshot: None,
    )
    monkeypatch.setattr(executor, "_start_server", lambda spec, runtime_fd: None)
    monkeypatch.setattr(
        executor.scratch_store,
        "cleanup",
        lambda path: (_ for _ in ()).throw(CleanupError("cleanup C")),
    )
    monkeypatch.setattr(
        CodexExecutor,
        "run_execution",
        lambda self, prepared, _runtime_binary_fd=None:
            (_ for _ in ()).throw(RuntimeError("execution E")),
    )
    assert executor._run_lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="execution E") as raised:
            executor.run_execution(prepared)
    finally:
        if executor._run_lock.locked(): executor._run_lock.release()
    notes = " ".join(raised.value.__notes__)
    assert "TeardownError: teardown T" in notes
    assert "CleanupError: cleanup C" in notes


def test_execution_error_wins_over_teardown_error(
    tmp_path, monkeypatch, pinned_runtime_fd
):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(executor, "_validate_runtime_identity", lambda snapshot: None)
    descriptor = object()
    executor._descriptor = descriptor
    prepared = PreparedExecution(spec, "atlas", (), "test", {}, None, descriptor)
    monkeypatch.setattr(
        executor, "_sealed_runtime_fd",
        lambda snapshot: os.dup(pinned_runtime_fd),
    )
    monkeypatch.setattr(
        executor, "_validate_sealed_runtime_fd",
        lambda fd, snapshot: None,
    )
    monkeypatch.setattr(executor, "_start_server", lambda spec, runtime_fd: None)
    monkeypatch.setattr(
        CodexExecutor,
        "run_execution",
        lambda self, prepared, _runtime_binary_fd=None:
            (_ for _ in ()).throw(RuntimeError("primary execution")),
    )
    monkeypatch.setattr(executor, "_stop_server", lambda: (_ for _ in ()).throw(
        RuntimeError("secondary teardown")))
    assert executor._run_lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="primary execution") as raised:
            executor.run_execution(prepared)
    finally:
        if executor._run_lock.locked(): executor._run_lock.release()
    assert any("secondary teardown" in note for note in raised.value.__notes__)


def test_scratch_root_symlink_is_not_destructive_authority(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    store = ScratchStore(target / "store")
    run = store.create("run-a")
    alias = tmp_path / "alias"
    alias.symlink_to(target / "store", target_is_directory=True)
    replaced = ScratchStore(alias)
    with pytest.raises(AtlasSandboxError):
        replaced.cleanup(alias / "runs" / "run-a")
    assert run.is_dir()


def test_scratch_run_symlink_and_plausible_foreign_dir_are_not_removed(tmp_path):
    store = ScratchStore(tmp_path / "scratch")
    run = store.create("run-a")
    (store.runs / "foreign").mkdir()
    (store.runs / "foreign" / "keep").write_text("keep")
    run.rename(store.runs / "real")
    (store.runs / "run-a").symlink_to(store.runs / "real", target_is_directory=True)
    with pytest.raises(AtlasSandboxError):
        store.cleanup(store.runs / "run-a")
    assert (store.runs / "real").is_dir()
    assert (store.runs / "foreign" / "keep").exists()


def test_launch_failure_still_cleans_scratch(
    tmp_path, monkeypatch, pinned_runtime_fd
):
    spec = _spec(tmp_path)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    monkeypatch.setattr(
        executor,
        "_mount_command",
        lambda spec, scratch, runtime_fd: ["missing"],
    )
    def fail(*args, **kwargs):
        raise OSError("launch failed")
    monkeypatch.setattr(subprocess, "Popen", fail)
    with pytest.raises(AtlasSandboxError, match="LAUNCH_FAILED"):
        executor._start_server(spec, pinned_runtime_fd)
    assert not (tmp_path / "scratch" / "runs" / "execution-test").exists()


def test_unreaped_server_still_cleans_scratch(tmp_path):
    store = ScratchStore(tmp_path / "scratch")
    run = store.create("run-a")
    class Stuck:
        pid = 1
        stdin = None
        stderr = None
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("server", timeout)
        def send_signal(self, signal):
            pass
        def kill(self):
            pass
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    executor.scratch_store = store
    executor._server, executor._scratch = Stuck(), run
    with pytest.raises(AtlasSandboxError, match="UNREAPED"):
        executor._stop_server()
    assert not run.exists()
