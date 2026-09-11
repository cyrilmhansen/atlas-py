from contextlib import contextmanager
import time
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.atlas_agent.executor import ExecutorError
from tools.atlas_agent.one_shot import OneShotExecutor
from tools.atlas_agent.pvc import PvcPrepareRequest, PvcRequestError, execute_prepare
from tools.atlas_agent.toolchains import (
    CacheScope, CapabilityPlan, Mount, ResolvedCache, ResolvedCommand, Toolchain,
)


@contextmanager
def _plan(path, root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    mount = Mount(root, Path("/opt/qualified"), True, root.stat().st_dev,
                  root.stat().st_ino, fd)
    command = ResolvedCommand("pvc", Path("/opt/qualified") / path.name,
                              "qualified", "fixture", path)
    plan = CapabilityPlan(
        [Toolchain("fixture", "test", Path("/opt/qualified"), (command,), root)],
        [], [mount], {"PATH": "/opt/qualified:/usr/bin:/bin"}, {},
    )
    try:
        yield plan
    finally:
        plan.close_authority()


def _namespace_available():
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return False
    return subprocess.run(
        [bwrap, "--unshare-net", "--ro-bind", "/usr", "/usr",
         "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
         "--proc", "/proc",
         "--dev", "/dev", "--symlink", "usr/bin", "/bin",
         "--", "/usr/bin/true"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def _fixture(tmp_path):
    script = tmp_path / "qualified-pvc.py"
    script.write_text(
        "#!/bin/sh\n"
        "if [ -e /var/tmp/bundle ]; then echo BUNDLE_PRESENT >&2; exit 8; fi\n"
        "if [ -e /var/tmp/work ]; then echo WORK_PRESENT >&2; exit 9; fi\n"
        "mkdir /var/tmp/bundle\n"
        "printf 'STDOUT %s\\n' \"$*\"\n"
        "printf 'STDERR %s\\n' \"$*\" >&2\n"
        "exit 7\n"
    )
    script.chmod(0o755)
    return script


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_qualified_argv_and_separate_output_and_exit_code(tmp_path):
    executable = _fixture(tmp_path)
    source = tmp_path / "image one.png"
    source.write_bytes(b"fixture")
    request = PvcPrepareRequest(tmp_path, ("image one.png",), "conservative")
    with _plan(executable, tmp_path) as plan:
        result = execute_prepare(
            request, capability_plan=plan, executor=OneShotExecutor(),
            stdout_path=tmp_path / "stdout", stderr_path=tmp_path / "stderr",
        )
        scratch = result.process.scratch_path
        try:
            assert result.process.exit_code == 7
            assert str(Path("/opt/qualified") / executable.name) in result.process.command
            assert result.process.command[-len((
                "prepare", "--cwd", str(tmp_path), "--output", "/var/tmp/bundle",
                "--work-root", "/var/tmp/work", "--profile", "conservative",
                "image one.png",)):] == (
                "prepare", "--cwd", str(tmp_path), "--output", "/var/tmp/bundle",
                "--work-root", "/var/tmp/work", "--profile", "conservative",
                "image one.png")
            assert (tmp_path / "stdout").read_text().startswith("STDOUT prepare")
            assert (tmp_path / "stderr").read_text().startswith("STDERR prepare")
            assert (scratch / "bundle").is_dir()
            assert not (scratch / "work").exists()
            assert not result.output_interpreted
        finally:
            shutil.rmtree(scratch)


@pytest.mark.parametrize("source", ["/etc/passwd", "../outside"])
def test_unsafe_sources_rejected_before_execution(tmp_path, source):
    with pytest.raises(PvcRequestError):
        PvcPrepareRequest(tmp_path, (source,))


@pytest.mark.parametrize("source", ["*.png", "sub/*.png"])
def test_glob_sources_rejected(tmp_path, source):
    with pytest.raises(PvcRequestError):
        PvcPrepareRequest(tmp_path, (source,))


def test_symlink_source_rejected(tmp_path):
    target = tmp_path / "real.png"
    target.write_bytes(b"fixture")
    (tmp_path / "alias.png").symlink_to(target)
    with pytest.raises(PvcRequestError, match="SYMLINK"):
        PvcPrepareRequest(tmp_path, ("alias.png",))


@pytest.mark.parametrize("source", [(), ("-help",)])
def test_empty_and_option_like_sources_rejected(tmp_path, source):
    with pytest.raises(PvcRequestError):
        PvcPrepareRequest(tmp_path, source)


def test_ambient_path_cannot_substitute_qualified_executable(tmp_path):
    executable = _fixture(tmp_path)
    with _plan(executable, tmp_path) as plan:
        with pytest.raises(ExecutorError, match="QUALIFIED_COMMAND_PLAN_MISMATCH"):
            OneShotExecutor().run(
                ResolvedCommand("pvc", Path("pvc"), "x", "x", Path("pvc")),
                (), capability_plan=plan, cwd=tmp_path,
                stdout_path=tmp_path / "o", stderr_path=tmp_path / "e",
            )


def test_relative_ambient_path_cannot_substitute_bwrap(tmp_path, monkeypatch):
    fake = tmp_path / "bwrap"
    fake.write_text("#!/bin/sh\nexit 99\n")
    fake.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", f".:/usr/bin:/bin")
    assert shutil.which("bwrap") == "./bwrap"
    resolved = OneShotExecutor._resolve_bwrap()
    assert resolved != fake
    assert resolved.is_absolute()


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_project_and_toolchain_roots_are_read_only(tmp_path):
    project = tmp_path / "project"
    toolchain = tmp_path / "toolchain"
    project.mkdir()
    toolchain.mkdir()
    executable = toolchain / "qualified-pvc.py"
    executable.write_text(
        "#!/bin/sh\n"
        f"if touch {project}/project-write 2>/dev/null; then exit 10; fi\n"
        "if touch /opt/qualified/toolchain-write 2>/dev/null; then exit 11; fi\n"
        "exit 0\n"
    )
    executable.chmod(0o755)
    with _plan(executable, toolchain) as plan:
        result = OneShotExecutor().run(
            plan.command("pvc"), (), capability_plan=plan, cwd=project,
            stdout_path=tmp_path / "o", stderr_path=tmp_path / "e",
        )
        scratch = result.scratch_path
        try:
            assert result.exit_code == 0
            assert not (project / "project-write").exists()
            assert not (toolchain / "toolchain-write").exists()
        finally:
            shutil.rmtree(scratch)


def test_writable_cache_is_rejected_before_backing_or_launch(tmp_path, monkeypatch):
    executable = _fixture(tmp_path)
    backing = tmp_path / "must-not-be-created"
    with _plan(executable, tmp_path) as base:
        plan = CapabilityPlan(
            base.toolchains,
            [ResolvedCache("cache", Path("/opt/cache"), backing,
                           CacheScope("project", "fixture"))],
            base.mounts, base.environment(), {},
        )
        launched = []
        monkeypatch.setattr(subprocess, "Popen",
                            lambda *args, **kwargs: launched.append(args))
        with pytest.raises(ExecutorError, match="ONE_SHOT_WRITABLE_CACHES_UNSUPPORTED"):
            OneShotExecutor().run(
                plan.command("pvc"), (), capability_plan=plan, cwd=tmp_path,
                stdout_path=tmp_path / "o", stderr_path=tmp_path / "e",
            )
        assert not backing.exists()
        assert not launched


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_timeout_must_be_finite_and_positive(timeout):
    with pytest.raises(ValueError):
        OneShotExecutor(timeout_seconds=timeout)


def test_output_authority_rejects_same_symlink_and_hardlink(tmp_path):
    output = tmp_path / "output"
    with pytest.raises(ExecutorError, match="DISTINCT"):
        OneShotExecutor._open_outputs(output, output)

    target = tmp_path / "target"
    target.write_bytes(b"old")
    alias = tmp_path / "symlink"
    alias.symlink_to(target)
    with pytest.raises((ExecutorError, OSError)):
        OneShotExecutor._open_outputs(target, alias)
    hardlink = tmp_path / "hardlink"
    hardlink.hardlink_to(target)
    with pytest.raises(ExecutorError, match="DISTINCT"):
        OneShotExecutor._open_outputs(target, hardlink)


@pytest.mark.skipif(not _namespace_available(), reason="bubblewrap namespace unavailable")
def test_timeout_terminates_owned_process_group(tmp_path):
    executable = tmp_path / "hang.py"
    executable.write_text(
        "#!/bin/sh\n"
        "(sleep 1; printf survived >/var/tmp/descendant-survived) &\n"
        "sleep 30\n"
    )
    executable.chmod(0o755)
    started = time.monotonic()
    with _plan(executable, tmp_path) as plan:
        result = OneShotExecutor(timeout_seconds=.15).run(
            plan.command("pvc"), (), capability_plan=plan, cwd=tmp_path,
            stdout_path=tmp_path / "o", stderr_path=tmp_path / "e",
        )
        scratch = result.scratch_path
        try:
            assert result.timed_out
            assert result.exit_code is not None
            assert time.monotonic() - started < 3
            time.sleep(1.2)
            assert not (scratch / "descendant-survived").exists()
        finally:
            shutil.rmtree(scratch)


def test_disk_class_rejection_is_direct(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    monkeypatch.setattr(
        "tools.atlas_agent.one_shot.AtlasBubblewrapExecutor._filesystem_class",
        lambda path: "tmpfs",
    )
    with pytest.raises(ExecutorError, match="DISK_SCRATCH_REQUIRED"):
        OneShotExecutor._validate_disk_scratch(scratch)


def test_failed_scratch_cleanup_is_surfaced(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    original = RuntimeError("launch failed")

    def fail_cleanup(path):
        raise OSError("cannot remove")

    monkeypatch.setattr(shutil, "rmtree", fail_cleanup)
    with pytest.raises(ExecutorError, match="SCRATCH_CLEANUP_FAILED"):
        OneShotExecutor._cleanup_failed_scratch(scratch, original)
