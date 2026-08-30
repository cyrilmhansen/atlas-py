from pathlib import Path
import os
import signal
import sys
import threading

import pytest

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionSpec, ExecutorError
from tests.codex_test_support import IOCodexExecutor, pinned_codex


def _spec(tmp_path, **changes):
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes(b"authoritative bytes")
    values = dict(
        generation=1,
        prompt_sha256="0" * 64,
        action="implementation",
        prompt_path=prompt,
        repository_root=tmp_path,
        execution_id="execution",
        report_dir=tmp_path / "reports",
    )
    values.update(changes)
    return ExecutionSpec(**values)


def test_modern_input_contract_fails_closed_without_bytes_or_digest(tmp_path):
    executor = CodexExecutor(executable="/bin/sh")
    with pytest.raises(ExecutorError, match="EXECUTION_INPUT_MISSING"):
        executor.prepare_execution(_spec(tmp_path, input_mode="bytes-v1"))


def test_legacy_input_contract_is_deliberate(tmp_path):
    executor,snapshot = pinned_codex(tmp_path,"/bin/true")
    with pytest.raises(ExecutorError, match="INVALID_EXECUTION_INPUT_MODE"):
        executor.prepare_execution(_spec(tmp_path, policy_snapshot=snapshot))
    prepared = executor.prepare_execution(
        _spec(tmp_path, input_mode="legacy", policy_snapshot=snapshot)
    )
    assert prepared.spec.input_mode == "legacy"


def test_modern_input_contract_accepts_exact_supplied_bytes(tmp_path):
    import hashlib

    data = b"authoritative bytes"
    executor,snapshot = pinned_codex(tmp_path,"/bin/true")
    prepared = executor.prepare_execution(
        _spec(
            tmp_path,
            prompt_bytes=data,
            input_mode="bytes-v1",
            expected_input_sha256=hashlib.sha256(data).hexdigest(),
            policy_snapshot=snapshot,
        )
    )
    assert prepared.spec.prompt_bytes == data


def test_process_group_is_cleaned_after_leader_already_exited(monkeypatch):
    class Proc:
        pid = 1234
        returncode = 0
        def poll(self): return self.returncode
        def wait(self, timeout=None): return self.returncode

    signals = []
    monkeypatch.setattr("os.killpg", lambda pid, sig: signals.append((pid, sig)))
    CodexExecutor()._terminate_and_reap(Proc())
    assert signals == [(1234, signal.SIGINT), (1234, signal.SIGKILL)]


def test_stdin_close_failure_is_not_silently_ignored():
    class BrokenClose:
        def close(self): raise OSError("close failed")

    state = {"close_error": None}
    CodexExecutor._close_stdin(BrokenClose(), state)
    assert isinstance(state["close_error"], OSError)


def test_popen_setup_failure_reaps_process_group(monkeypatch, tmp_path):
    stdin_fd, stdout_fd = os.pipe()

    class Stream:
        def __init__(self, fd): self.fd = fd
        def fileno(self): return self.fd
        def close(self): os.close(self.fd)

    class Proc:
        pid = 2345
        stdin = Stream(stdin_fd)
        stdout = Stream(stdout_fd)

    proc = Proc()
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: proc)
    monkeypatch.setattr("os.set_blocking", lambda *args: (_ for _ in ()).throw(OSError("setup failed")))
    executor = IOCodexExecutor()
    reaped = []
    monkeypatch.setattr(executor, "_terminate_and_reap", lambda value: reaped.append(value) or -1)
    with pytest.raises(ExecutorError, match="CODEX_STREAM_FAILED: setup failed"):
        executor.run_execution(_prepared(tmp_path))
    assert reaped == [proc]


def test_post_popen_interrupt_at_first_setup_boundary_reaps_group(monkeypatch, tmp_path):
    class Proc:
        pid=3456
        stdout=None
        @property
        def stdin(self):
            raise KeyboardInterrupt()
    proc=Proc()
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: proc)
    executor=IOCodexExecutor()
    reaped=[]
    monkeypatch.setattr(executor, "_terminate_and_reap", lambda value: reaped.append(value) or -1)
    with pytest.raises(KeyboardInterrupt):
        executor.run_execution(_prepared(tmp_path))
    assert reaped == [proc]


def _prepared(tmp_path, command=("fake-codex",)):
    from tools.atlas_agent.executor import PreparedExecution
    spec = _spec(tmp_path, input_mode="legacy")
    return PreparedExecution(spec, "codex", command, "test", {})


def test_stdin_close_failure_precedes_timeout(monkeypatch, tmp_path):
    released = threading.Event()

    def close_stdin(prompt, state):
        released.wait(timeout=1)
        try: prompt.close()
        except OSError: pass
        state["close_error"] = OSError("close failed")

    executor = IOCodexExecutor(timeout_seconds=.01, heartbeat_seconds=1)
    monkeypatch.setattr(executor, "_close_stdin", close_stdin)
    monkeypatch.setattr(executor, "_terminate_and_reap", lambda proc: released.set() or -2)
    with pytest.raises(ExecutorError, match="CODEX_INPUT_CLOSE_FAILED: close failed"):
        executor.run_execution(_prepared(tmp_path, (sys.executable, "-c", "import time; time.sleep(10)")))


def test_stdin_write_failure_precedes_timeout(monkeypatch, tmp_path):
    executor=IOCodexExecutor(timeout_seconds=.01, heartbeat_seconds=1)
    def reap(proc):
        raise AssertionError("timeout cleanup must not win over writer failure")
    monkeypatch.setattr(executor, "_terminate_and_reap", reap)
    original=os.write
    def broken_write(fd, data):
        raise OSError("pipe failed")
    monkeypatch.setattr(os, "write", broken_write)
    with pytest.raises(ExecutorError, match="CODEX_INPUT_WRITE_FAILED: pipe failed"):
        executor.run_execution(_prepared(tmp_path, (sys.executable, "-c", "import time; time.sleep(10)")))


def test_keyboard_interrupt_reaps_the_process(monkeypatch, tmp_path):
    executable = tmp_path / "fake-codex"
    executable.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "if '--version' in sys.argv: print('test'); raise SystemExit(0)\n"
        "print('{}', flush=True)\n"
    )
    executable.chmod(0o755)
    executor,snapshot = pinned_codex(
        tmp_path,
        executable,
        timeout_seconds=1,
        heartbeat_seconds=1,
    )
    spec = _spec(tmp_path, input_mode="legacy", policy_snapshot=snapshot)
    prepared = executor.prepare_execution(spec)
    cleaned = []
    def reap(proc):
        cleaned.append(proc)
        return proc.wait(timeout=1)
    monkeypatch.setattr(executor, "_terminate_and_reap", reap)
    monkeypatch.setattr(executor, "_consume_progress_line", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        executor.run_execution(prepared)
    assert cleaned


def test_supplied_modern_digest_mismatch_fails_before_launch(tmp_path):
    data = b"authoritative bytes"
    with pytest.raises(ExecutorError, match="EXECUTION_INPUT_HASH_MISMATCH"):
        CodexExecutor(executable="/bin/sh").prepare_execution(
            _spec(tmp_path, prompt_bytes=data, input_mode="bytes-v1", expected_input_sha256="0" * 64)
        )


def test_run_boundary_revalidates_modern_input_before_popen(tmp_path, monkeypatch):
    import hashlib
    from dataclasses import replace

    data = b"authoritative bytes"
    executor,snapshot = pinned_codex(tmp_path,"/bin/true")
    prepared = executor.prepare_execution(
        _spec(
            tmp_path,
            prompt_bytes=data,
            input_mode="bytes-v1",
            expected_input_sha256=hashlib.sha256(data).hexdigest(),
            policy_snapshot=snapshot,
        )
    )
    prepared = replace(prepared, spec=replace(prepared.spec, prompt_bytes=b"changed"))
    calls = []

    def forbidden_popen(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Popen must not be reached")

    monkeypatch.setattr("subprocess.Popen", forbidden_popen)
    with pytest.raises(ExecutorError, match="EXECUTION_INPUT_HASH_MISMATCH"):
        executor.run_execution(prepared)
    assert calls == []


def test_duplex_backpressure_hands_off_exact_oversized_input(tmp_path):
    import hashlib
    script = tmp_path / "duplex.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdout.buffer.write(b'x' * (128 * 1024)); sys.stdout.flush()\n"
        "sys.stdout.write(json.dumps({'type':'thread.started','thread_id':'duplex'})+'\\n'); sys.stdout.flush()\n"
        "data=sys.stdin.buffer.read()\n"
        "sys.stdout.write(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'done'}})+'\\n'); sys.stdout.flush()\n"
    )
    data = b"x" * (128 * 1024)
    from tools.atlas_agent.executor import PreparedExecution
    spec = _spec(
        tmp_path,
        prompt_bytes=data,
        input_mode="bytes-v1",
        expected_input_sha256=hashlib.sha256(data).hexdigest(),
    )
    prepared = PreparedExecution(
        spec,
        "codex",
        (sys.executable, str(script)),
        "test",
        {},
    )
    result = IOCodexExecutor(executable=sys.executable).run_execution(prepared)
    assert result.exit_code == 0 and result.execution_input_sha256 == hashlib.sha256(data).hexdigest()


def test_new_session_descendant_is_contained_after_leader_exit(tmp_path):
    descendant = tmp_path / "descendant.pid"
    script = tmp_path / "leader.py"
    script.write_text(
        "import subprocess, sys, time\n"
        f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nopen({str(descendant)!r},'w').write(str(p.pid))\n"
        "print('{\"type\":\"thread.started\",\"thread_id\":\"leader\"}', flush=True)\n"
    )
    from tools.atlas_agent.executor import PreparedExecution
    executor = IOCodexExecutor(executable=sys.executable)
    spec = _spec(
        tmp_path,
        prompt_bytes=b"",
        input_mode="bytes-v1",
        expected_input_sha256=__import__('hashlib').sha256(b"").hexdigest(),
    )
    prepared = PreparedExecution(
        spec,
        "codex",
        (sys.executable, str(script)),
        "test",
        {},
    )
    result = executor.run_execution(prepared)
    assert result.exit_code == 0
    pid = int(descendant.read_text())

    # SIGKILL has been delivered to the inherited process group, but after
    # the leader exits the descendant is no longer our child.  PID 1 may
    # therefore need a short interval to reap the dead process, especially
    # while the full test suite is under load.
    import time
    deadline = time.monotonic() + 1.0
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            pytest.fail(f"descendant {pid} still exists after bounded reap wait")
        time.sleep(0.01)
