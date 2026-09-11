"""Bounded execution of an already-qualified command.

This is deliberately not a provider or workflow abstraction.  It is the
small process boundary used by qualified, non-durable tool operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
import time

from .executor import ExecutorError
from .bubblewrap import AtlasBubblewrapExecutor
from .toolchains import CapabilityError, ResolvedCommand


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ProcessResult:
    """Process facts only; this intentionally says nothing about tool output."""

    command: tuple[str, ...]
    started_at: str
    finished_at: str
    exit_code: int | None
    stdout_path: Path
    stderr_path: Path
    timed_out: bool = False
    scratch_path: Path | None = None

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class OneShotExecutor:
    """Launch an explicit argv in an owned process session.

    Output is written to separate files, as with the existing Atlas executor.
    The command is a ResolvedCommand rather than a name, so this class never
    performs PATH lookup or qualification.
    """

    SHUTDOWN_GRACE_SECONDS = 1.0
    SHUTDOWN_KILL_SECONDS = 1.0

    def __init__(self, *, timeout_seconds: float = 300):
        if isinstance(timeout_seconds, bool):
            raise ValueError("timeout_seconds must be positive")
        try:
            normalized_timeout = float(timeout_seconds)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("timeout_seconds must be positive") from error
        if not math.isfinite(normalized_timeout) or normalized_timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = normalized_timeout

    def run(
        self,
        command: ResolvedCommand,
        args: tuple[str, ...] | list[str],
        *,
        capability_plan,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
    ) -> ProcessResult:
        if not isinstance(command, ResolvedCommand):
            raise TypeError("one-shot execution requires a ResolvedCommand")
        try:
            if capability_plan.command(command.name) != command:
                raise ExecutorError("QUALIFIED_COMMAND_PLAN_MISMATCH")
        except (AttributeError, KeyError, CapabilityError):
            raise ExecutorError("QUALIFIED_COMMAND_PLAN_MISMATCH")
        if not hasattr(capability_plan, "caches"):
            raise ExecutorError("ONE_SHOT_CAPABILITY_PLAN_REQUIRED")
        if capability_plan.caches:
            # CacheStore preparation and locking is deliberately not part of
            # this operation slice.  Never turn a plan cache into an
            # unaccounted-for writable bind.
            raise ExecutorError("ONE_SHOT_WRITABLE_CACHES_UNSUPPORTED")
        executable = Path(command.host_path)
        if not executable.is_absolute() or not executable.is_file():
            raise ExecutorError("QUALIFIED_EXECUTABLE_UNAVAILABLE")
        if not os.access(executable, os.X_OK):
            raise ExecutorError("QUALIFIED_EXECUTABLE_UNAVAILABLE")
        root = Path(cwd)
        if not root.is_dir():
            raise ExecutorError("ONE_SHOT_CWD_UNAVAILABLE")
        bwrap = self._resolve_bwrap()
        guest = Path(command.guest_path)
        if not guest.is_absolute():
            raise ExecutorError("QUALIFIED_GUEST_IDENTITY_INVALID")
        # Request paths are deliberately not accepted here.  The only
        # writable filesystem presented to a PVC child is this
        # controller-owned, operation-scoped directory.
        try:
            scratch = Path(tempfile.mkdtemp(prefix="atlas-pvc-", dir="/var/tmp"))
        except OSError as error:
            raise ExecutorError(f"ONE_SHOT_SCRATCH_FAILED: {error}") from error
        try:
            self._validate_disk_scratch(scratch)
            argv = (str(guest), *(str(value) for value in args))
            launch = self._namespace_command(
                bwrap, capability_plan, root, scratch, argv,
            )
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stdout, stderr = self._open_outputs(stdout_path, stderr_path)
            # The supplied environment is an explicit capability-plan result.
            started = _now()
            began = time.monotonic()
            timed_out = False
            with stdout, stderr:
                try:
                    process = subprocess.Popen(
                        launch, env={}, stdout=stdout, stderr=stderr,
                        start_new_session=True,
                        pass_fds=tuple(m.authority_fd for m in capability_plan.mounts),
                    )
                except OSError as error:
                    raise ExecutorError(f"ONE_SHOT_LAUNCH_FAILED: {error}") from error
                try:
                    while True:
                        remaining = self.timeout_seconds - (time.monotonic() - began)
                        if remaining <= 0:
                            timed_out = True
                            exit_code = self._terminate_and_reap(process)
                            break
                        try:
                            exit_code = process.wait(timeout=min(remaining, 0.2))
                            break
                        except subprocess.TimeoutExpired:
                            continue
                except BaseException:
                    self._terminate_and_reap(process)
                    raise
        except OSError as error:
            failure = ExecutorError(f"ONE_SHOT_OUTPUT_FAILED: {error}")
            self._cleanup_failed_scratch(scratch, failure)
            raise failure from error
        except BaseException as error:
            # No result exists yet, so this scratch cannot be useful to a
            # later validation layer.
            self._cleanup_failed_scratch(scratch, error)
            raise
        return ProcessResult(
            argv, started, _now(), exit_code, stdout_path, stderr_path, timed_out,
            scratch,
        )

    @staticmethod
    def _resolve_bwrap() -> Path:
        """Resolve only a controller-owned system Bubblewrap executable."""
        candidate = shutil.which("bwrap", path="/usr/bin:/bin")
        if not candidate:
            raise ExecutorError("ONE_SHOT_BWRAP_UNAVAILABLE")
        path = Path(candidate)
        if not path.is_absolute():
            raise ExecutorError("ONE_SHOT_BWRAP_UNAVAILABLE")
        try:
            path = path.resolve(strict=True)
        except OSError as error:
            raise ExecutorError("ONE_SHOT_BWRAP_UNAVAILABLE") from error
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ExecutorError("ONE_SHOT_BWRAP_UNAVAILABLE")
        return path

    @staticmethod
    def _namespace_command(bwrap, plan, root, scratch, argv):
        """Construct the narrow PVC namespace from retained plan authority."""
        if plan is None or not hasattr(plan, "mounts") or not hasattr(plan, "environment"):
            raise ExecutorError("ONE_SHOT_CAPABILITY_PLAN_REQUIRED")
        if plan.caches:
            raise ExecutorError("ONE_SHOT_WRITABLE_CACHES_UNSUPPORTED")
        command = [
            bwrap, "--die-with-parent", "--new-session", "--unshare-pid",
            "--unshare-ipc", "--unshare-net",
            "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/sbin", "/sbin", "--ro-bind", "/etc", "/etc",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--tmpfs", "/dev/shm", "--dir", "/var", "--dir", "/var/tmp",
            "--bind", str(scratch), "/var/tmp", "--dir", "/opt", "--clearenv",
            "--ro-bind", str(root), str(root),
        ]
        for mount in plan.mounts:
            if mount.authority_fd < 0:
                raise ExecutorError("ATLAS_TOOLCHAIN_AUTHORITY_INVALID")
            command += ["--ro-bind", mount.authority_path, str(mount.guest_root)]
        for key, value in plan.environment().items():
            command += ["--setenv", str(key), str(value)]
        command += ["--chdir", str(root), "--", *argv]
        return command

    @staticmethod
    def _validate_disk_scratch(scratch: Path) -> None:
        """Check the backing filesystem and exercise this exact directory."""
        if AtlasBubblewrapExecutor._filesystem_class(scratch) != "disk":
            raise ExecutorError("ONE_SHOT_DISK_SCRATCH_REQUIRED")
        probe = scratch / ".atlas-pvc-probe"
        try:
            fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600)
            os.close(fd)
            probe.unlink()
        except OSError as error:
            try:
                probe.unlink()
            except OSError:
                pass
            raise ExecutorError("ONE_SHOT_DISK_SCRATCH_PROBE_FAILED") from error

    @staticmethod
    def _open_outputs(stdout_path: Path, stderr_path: Path):
        """Open distinct regular output files without following final links."""
        stdout_path = Path(stdout_path)
        stderr_path = Path(stderr_path)
        try:
            if stdout_path.resolve() == stderr_path.resolve():
                raise ExecutorError("ONE_SHOT_OUTPUTS_MUST_BE_DISTINCT")
        except OSError as error:
            raise ExecutorError("ONE_SHOT_OUTPUT_PREPARATION_FAILED") from error
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
        fds = []
        try:
            fds.append(os.open(stdout_path, flags, 0o600))
            fds.append(os.open(stderr_path, flags, 0o600))
            first, second = os.fstat(fds[0]), os.fstat(fds[1])
            if (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino):
                raise ExecutorError("ONE_SHOT_OUTPUTS_MUST_BE_DISTINCT")
            os.ftruncate(fds[0], 0)
            os.ftruncate(fds[1], 0)
            return (os.fdopen(fds[0], "wb"), os.fdopen(fds[1], "wb"))
        except BaseException:
            for fd in fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise

    @staticmethod
    def _cleanup_failed_scratch(scratch: Path, original: BaseException) -> None:
        try:
            shutil.rmtree(scratch)
        except BaseException as cleanup_error:
            raise ExecutorError(
                f"ONE_SHOT_SCRATCH_CLEANUP_FAILED: {scratch}: {cleanup_error}"
            ) from original

    def _terminate_and_reap(self, process: subprocess.Popen) -> int:
        """Interrupt, force-kill if needed, and always reap the owned group."""
        try:
            os.killpg(process.pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            exit_code = process.wait(timeout=self.SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            exit_code = None
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            final = process.wait(timeout=self.SHUTDOWN_KILL_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise ExecutorError("ONE_SHOT_PROCESS_UNREAPED") from error
        return final if exit_code is None else exit_code
