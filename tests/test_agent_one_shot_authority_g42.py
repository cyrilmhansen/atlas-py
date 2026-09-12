"""Production-path regressions for the bounded PVC executor boundary."""
import os
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tools.atlas_agent.one_shot import OneShotExecutor
from tools.atlas_agent.pvc import PvcBundleValidationError, execute_prepare
from tools.atlas_agent.toolchains import CapabilityPlan, Mount, ResolvedCommand, Toolchain
from tools.atlas_agent.pvc import PvcPrepareRequest
import tools.atlas_agent.pvc as pvc_module
from test_agent_pvc_validation import _result as validation_result


def _namespace_available():
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return False
    return subprocess.run(
        [bwrap, "--unshare-net", "--ro-bind", "/usr", "/usr",
         "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
         "--proc", "/proc", "--dev", "/dev", "--symlink", "usr/bin", "/bin",
         "--", "/usr/bin/true"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


@pytest.fixture
def live_plan(tmp_path):
    executable = tmp_path / "qualified-command"
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    mount = Mount(tmp_path, Path("/opt/qualified"), True, tmp_path.stat().st_dev,
                  tmp_path.stat().st_ino, fd)
    command = ResolvedCommand("pvc", Path("/opt/qualified") / executable.name,
                              "qualified", "fixture", executable)
    plan = CapabilityPlan(
        [Toolchain("fixture", "test", Path("/opt/qualified"), (command,), tmp_path)],
        [], [mount], {"PATH": "/opt/qualified:/usr/bin:/bin"}, {},
    )
    try:
        yield executable, plan
    finally:
        plan.close_authority()


def _run(executable, plan, tmp_path, *, timeout=2):
    return OneShotExecutor(timeout_seconds=timeout).run(
        plan.command("pvc"), (), capability_plan=plan, cwd=tmp_path,
    )


def _discard(result):
    if result.scratch_path:
        shutil.rmtree(result.scratch_path, ignore_errors=True)


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_live_guest_cannot_replace_retained_stdout_or_stderr(live_plan, tmp_path):
    executable, plan = live_plan
    executable.write_text(
        "#!/bin/sh\n"
        "printf 'pipe stdout\\n'\n"
        "/bin/sh -c '"
        "printf \"direct stdout\\\\n\" >/var/tmp/stdout; "
        "rm -f /var/tmp/stdout; "
        "printf \"replacement stdout\\\\n\" >/var/tmp/stdout"
        "' 2>/dev/null || :\n"
        "printf 'pipe stderr\\n' >&2\n"
        "/bin/sh -c '"
        "printf \"direct stderr\\\\n\" >/var/tmp/stderr; "
        "rm -f /var/tmp/stderr; "
        "printf \"replacement stderr\\\\n\" >/var/tmp/stderr"
        "' 2>/dev/null || :\n"
        "exit 0\n"
    )
    executable.chmod(0o755)
    result = _run(executable, plan, tmp_path)
    try:
        assert result.succeeded
        assert result.timed_out is False
        assert result.output_limit_exceeded is None
        assert result.stdout_path.read_bytes() == b"pipe stdout\n"
        assert result.stderr_path.read_bytes() == b"pipe stderr\n"
        assert result.stdout_path.name == "stdout"
        assert result.stderr_path.name == "stderr"
    finally:
        _discard(result)


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_eof_before_process_exit_still_times_out_and_reaps(live_plan, tmp_path):
    executable, plan = live_plan
    # Create the marker only after both inherited pipe descriptors have been
    # closed.  This prevents slow bwrap startup from being mistaken for EOF.
    executable.write_text(
        "#!/bin/sh\n"
        "exec 1>&- 2>&-\n"
        "touch /var/tmp/eof-reached\n"
        "sleep 30\n"
    )
    executable.chmod(0o755)
    started = time.monotonic()
    result = _run(executable, plan, tmp_path, timeout=1)
    try:
        assert (result.scratch_path / "eof-reached").is_file()
        assert result.timed_out
        assert not result.succeeded
        # A non-None exit code is available only after the owned process was
        # terminated and reaped.
        assert result.exit_code is not None
        assert time.monotonic() - started < 4
    finally:
        _discard(result)


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_below_limit_is_exact_and_above_limit_is_bounded(live_plan, tmp_path,
                                                         monkeypatch):
    executable, plan = live_plan
    monkeypatch.setattr(OneShotExecutor, "MAX_STDOUT_BYTES", 1024)
    monkeypatch.setattr(OneShotExecutor, "MAX_STDERR_BYTES", 1024)

    executable.write_text("#!/bin/sh\ndd if=/dev/zero bs=1023 count=1 2>/dev/null\n")
    executable.chmod(0o755)
    below = _run(executable, plan, tmp_path)
    try:
        assert below.succeeded
        assert below.output_limit_exceeded is None
        assert below.stdout_path.read_bytes() == b"\0" * 1023
    finally:
        _discard(below)

    executable.write_text(
        "#!/bin/sh\nmkdir /var/tmp/bundle /var/tmp/work\n"
        "dd if=/dev/zero bs=2048 count=1 2>/dev/null\n"
    )
    above = _run(executable, plan, tmp_path)
    try:
        assert not above.succeeded
        assert above.output_limit_exceeded == "STDOUT"
        assert above.exit_code is not None
        assert above.stdout_path.is_file()
        assert above.stdout_path.stat().st_size <= 1024
        assert above.stderr_path.is_file()
        assert above.stderr_path.stat().st_size <= 1024
        assert above.scratch_path.is_dir()
        assert (above.scratch_path / "bundle").is_dir()
        assert (above.scratch_path / "work").is_dir()
    finally:
        _discard(above)


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_each_stream_output_limit_is_explicit(live_plan, tmp_path, monkeypatch,
                                              stream):
    executable, plan = live_plan
    monkeypatch.setattr(OneShotExecutor, "MAX_STDOUT_BYTES", 512)
    monkeypatch.setattr(OneShotExecutor, "MAX_STDERR_BYTES", 512)
    if stream == "stdout":
        emit = "dd if=/dev/zero bs=1024 count=1 2>/dev/null\n"
    else:
        # Keep dd's diagnostics out of the fixture while sending its payload
        # to the actual inherited stderr pipe.
        # Redirections are intentionally ordered: stdout is first duplicated
        # from the inherited stderr pipe, then the original stderr is quieted.
        emit = "dd if=/dev/zero bs=1024 count=1 1>&2 2>/dev/null\n"
    executable.write_text(
        "#!/bin/sh\n"
        + emit
        + "sleep 30\n"
        + "touch /var/tmp/post-limit-sentinel\n"
    )
    executable.chmod(0o755)
    started = time.monotonic()
    result = _run(executable, plan, tmp_path, timeout=2)
    try:
        assert result.output_limit_exceeded == stream.upper()
        assert result.timed_out is False
        assert result.succeeded is False
        assert result.exit_code is not None
        path = result.stdout_path if stream == "stdout" else result.stderr_path
        retained = path.read_bytes()
        assert retained
        assert len(retained) <= 512
        other_path = result.stderr_path if stream == "stdout" else result.stdout_path
        assert other_path.read_bytes() == b""
        assert not (result.scratch_path / "post-limit-sentinel").exists()
        assert time.monotonic() - started < 5
    finally:
        _discard(result)


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_concurrent_streams_are_collected_without_deadlock(live_plan, tmp_path,
                                                           monkeypatch):
    executable, plan = live_plan
    # Each stream is 128 KiB, above the usual Linux pipe capacity (64 KiB).
    # Alternating 4 KiB writes makes a serial drain of either pipe deadlock.
    payload_chunks = 32
    chunk_bytes = 4096
    payload_bytes = payload_chunks * chunk_bytes
    collector_limit = payload_bytes * 2
    monkeypatch.setattr(OneShotExecutor, "MAX_STDOUT_BYTES", collector_limit)
    monkeypatch.setattr(OneShotExecutor, "MAX_STDERR_BYTES", collector_limit)
    executable.write_text(
        "#!/bin/sh\n"
        f"i=0; while [ $i -lt {payload_chunks} ]; do "
        f"dd if=/dev/zero bs={chunk_bytes} count=1 2>/dev/null; "
        f"dd if=/dev/zero bs={chunk_bytes} count=1 1>&2 2>/dev/null; "
        "i=$((i+1)); done\n"
    )
    executable.chmod(0o755)
    result = _run(executable, plan, tmp_path, timeout=3)
    try:
        assert result.succeeded
        assert result.timed_out is False
        assert result.output_limit_exceeded is None
        stdout = result.stdout_path.read_bytes()
        stderr = result.stderr_path.read_bytes()
        assert stdout == b"\0" * payload_bytes
        assert stderr == b"\0" * payload_bytes
        assert len(stdout) <= collector_limit
        assert len(stderr) <= collector_limit
    finally:
        _discard(result)


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_validator_refuses_real_output_limit_result(live_plan, tmp_path,
                                                    monkeypatch):
    executable, plan = live_plan
    monkeypatch.setattr(OneShotExecutor, "MAX_STDOUT_BYTES", 32)
    executable.write_text(
        "#!/bin/sh\nmkdir /var/tmp/bundle\n"
        "dd if=/dev/zero bs=128 count=1 2>/dev/null\n"
    )
    executable.chmod(0o755)
    (tmp_path / "source.txt").write_text("source")
    request = PvcPrepareRequest(tmp_path, ("source.txt",))
    result = execute_prepare(request, capability_plan=plan,
                             executor=OneShotExecutor())
    try:
        assert not result.process_succeeded
        with pytest.raises(PvcBundleValidationError, match="PROCESS"):
            result.validate()
        assert not result.bundle_validated
        assert not result.output_interpreted
    finally:
        _discard(result.process)


@pytest.mark.parametrize("failure", ["mismatch", "artifact"])
def test_bundle_directory_fd_is_closed_on_validation_failures(tmp_path, monkeypatch,
                                                              failure):
    result = validation_result(tmp_path)
    if failure == "mismatch":
        result.bundle_path.joinpath("snapshot.json").write_bytes(b"{}")
    else:
        document = json.loads(result.stdout_path.read_text())
        document["artifacts"][0]["byteLength"] += 1
        encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
        result.stdout_path.write_bytes(encoded)
        result.bundle_path.joinpath("snapshot.json").write_bytes(encoded)

    real_open = pvc_module.os.open
    bundle_fds = []

    def tracking_open(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        if path == "bundle" and "dir_fd" in kwargs:
            bundle_fds.append(fd)
        return fd

    monkeypatch.setattr(pvc_module.os, "open", tracking_open)
    try:
        with pytest.raises(PvcBundleValidationError):
            pvc_module.validate_prepare_result(result)
        assert bundle_fds
        for fd in bundle_fds:
            with pytest.raises(OSError):
                os.fstat(fd)
    finally:
        _discard(result.process)
