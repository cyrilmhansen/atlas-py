"""The Linux Atlas/bubblewrap execution boundary.

This module deliberately keeps the Codex control process outside bwrap.  The
short-lived exec-server, and therefore all model-generated process execution,
is the process launched inside the namespace.
"""
from __future__ import annotations

import os
import hashlib
import re
import shutil
import stat
import subprocess
import sys
import time
import signal
import threading
import select
from dataclasses import replace
from pathlib import Path

from .codex_executor import CodexExecutor
from .executor import ExecutorError, ExecutionResult, PreparedExecution


class AtlasSandboxError(ExecutorError):
    """A fail-closed operator error from sandbox preparation."""


def _native_codex(executable: str | None) -> Path | None:
    """Resolve the native Codex binary without mounting the user's home."""
    if not executable:
        return None
    candidate = Path(executable).resolve()
    if candidate.name == "codex" and os.access(candidate, os.X_OK):
        # The npm launcher is JavaScript; only accept a native executable.
        try:
            if candidate.read_bytes()[:4] == b"\x7fELF":
                return candidate
        except OSError:
            pass
    # The installed npm launcher keeps the platform binary beside itself.
    for parent in [candidate.parent, *candidate.parents]:
        matches = list(parent.glob("node_modules/@openai/codex-linux-x64/vendor/*/bin/codex"))
        if matches and os.access(matches[0], os.X_OK):
            return matches[0].resolve()
    return None


class ScratchStore:
    """Controller-owned scratch control, with child-visible run directories."""

    MARKER = ".atlas-scratch-owner"

    def __init__(self, root: Path = Path("/var/tmp/atlas-agent")):
        self.root = Path(root)
        self.control = self.root / "control"
        self.runs = self.root / "runs"
        self._authorities = {}
        self._runtime_authorities = {}

    @staticmethod
    def _open_dir_at(parent_fd, name, create=False):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
        return os.open(name, flags, dir_fd=parent_fd)

    def _open_root(self, create=False):
        parent = self.root.parent
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            root_fd = self._open_dir_at(parent_fd, self.root.name, create=create)
        except BaseException:
            os.close(parent_fd)
            raise
        os.close(parent_fd)
        return root_fd

    def ensure_root(self):
        """Establish the root inode without following its configured name."""
        try:
            fd = self._open_root(create=True)
            try:
                os.fchmod(fd, 0o700)
            finally:
                os.close(fd)
        except OSError as error:
            raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_PREPARE_FAILED") from error

    @staticmethod
    def _remove_tree(parent_fd, name):
        """Remove one directory using only already trusted descriptors."""
        child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                           dir_fd=parent_fd)
        try:
            for entry in os.scandir(child_fd):
                child = entry.name
                if entry.is_dir(follow_symlinks=False):
                    ScratchStore._remove_tree(child_fd, child)
                    os.rmdir(child, dir_fd=child_fd)
                else:
                    os.unlink(child, dir_fd=child_fd)
        finally:
            os.close(child_fd)

    def create(self, execution_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9-]{1,128}", execution_id):
            raise AtlasSandboxError("ATLAS_SANDBOX_BAD_EXECUTION_ID")
        try:
            root_fd = self._open_root(create=True)
            os.fchmod(root_fd, 0o700)
            control_fd = self._open_dir_at(root_fd, "control", create=True)
            runs_fd = self._open_dir_at(root_fd, "runs", create=True)
            os.fchmod(control_fd, 0o700); os.fchmod(runs_fd, 0o700)
        except OSError as error:
            for fd in locals().get("control_fd", None), locals().get("runs_fd", None), locals().get("root_fd", None):
                if fd is not None:
                    try: os.close(fd)
                    except OSError: pass
            raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_CREATE_FAILED") from error
        path = self.runs / execution_id; marker = self.control / execution_id
        created = False
        run_fd = None
        try:
            try:
                os.mkdir(execution_id, 0o700, dir_fd=runs_fd)
            except FileExistsError as error:
                # An execution id is unique.  In particular, do not treat an
                # existing directory as recoverable scratch: it may contain
                # stale or foreign data and must remain byte-for-byte intact.
                raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_COLLISION") from error
            created = True
            run_fd = os.open(execution_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=runs_fd)
            marker_fd = os.open(execution_id, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o600, dir_fd=control_fd)
            try:
                os.write(marker_fd, f"atlas-agent-scratch-v1\n{execution_id}\n{os.getuid()}\n".encode("ascii"))
            finally:
                os.close(marker_fd)
            self._authorities[str(path)] = (root_fd, runs_fd, control_fd, run_fd,
                                            os.fstat(run_fd))
            return path
        except (OSError, UnicodeError, AtlasSandboxError) as error:
            # Construction is transactional from the caller's perspective.
            # Remove only the exact newly-created entry, never a resolved
            # child-supplied path.
            if created:
                try:
                    if run_fd is not None:
                        self._remove_tree(run_fd, ".")
                    else:
                        self._remove_tree(runs_fd, execution_id)
                except OSError: pass
                try: os.rmdir(execution_id, dir_fd=runs_fd)
                except OSError: pass
            if created:
                try: os.unlink(execution_id, dir_fd=control_fd)
                except OSError: pass
            if run_fd is not None:
                try: os.close(run_fd)
                except OSError: pass
            os.close(root_fd); os.close(runs_fd); os.close(control_fd)
            if isinstance(error, AtlasSandboxError):
                raise
            raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_CREATE_FAILED") from error

    def owned(self, path: Path) -> bool:
        path = Path(path)
        try:
            runs_fd = os.open(self.runs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                name = path.name
                if path.parent != self.runs or not name:
                    return False
                child = os.stat(name, dir_fd=runs_fd, follow_symlinks=False)
                if not stat.S_ISDIR(child.st_mode):
                    return False
                control_fd = os.open(self.control, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    marker_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=control_fd)
                    try:
                        marker_stat = os.fstat(marker_fd)
                        text = os.read(marker_fd, 4096).decode("ascii").splitlines()
                    finally:
                        os.close(marker_fd)
                finally:
                    os.close(control_fd)
                return (len(text) == 3 and text[0] == "atlas-agent-scratch-v1" and
                        text[1] == name and text[2] == str(os.getuid()) and
                        marker_stat.st_uid == os.getuid() and stat.S_ISREG(marker_stat.st_mode))
            finally:
                os.close(runs_fd)
        except (OSError, UnicodeError):
            return False

    def cleanup(self, path: Path) -> None:
        path = Path(path)
        authority = self._authorities.get(str(path))
        if path.parent != self.runs:
            raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_NOT_OWNED")
        try:
            # Cleanup is only authorized by the exact directory fd retained
            # by create().  Reopening path.name would let a replacement inode
            # become the destructive target after a rename/substitution.
            if authority is None:
                raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_NOT_OWNED")
            root_fd, runs_fd, control_fd, run_fd, identity = authority
            runtime_path = self.control / f"{path.name}.runtime"
            self.remove_runtime(runtime_path)
            current = os.stat(path.name, dir_fd=runs_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_CHANGED")
            self._remove_tree(run_fd, ".")
            # Recheck the name after emptying the held inode.  A substituted
            # entry is left untouched; the renamed original may remain.
            current = os.stat(path.name, dir_fd=runs_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_CHANGED")
            os.rmdir(path.name, dir_fd=runs_fd)
            os.unlink(path.name, dir_fd=control_fd)
            os.fsync(runs_fd); os.fsync(control_fd)
            self._authorities.pop(str(path), None)
        except (OSError, ValueError) as error:
            raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_CLEANUP_FAILED") from error
        finally:
            if authority is not None or 'close_authority' in locals():
                for fd in (locals().get("run_fd"), locals().get("control_fd"), locals().get("runs_fd"), locals().get("root_fd")):
                    if fd is not None:
                        try: os.close(fd)
                        except OSError: pass

    def materialize_runtime(self, scratch: Path, execution_id: str, sealed_fd: int,
                            expected_sha256: str) -> Path:
        """Materialize an authenticated sealed runtime in controller control."""
        scratch = Path(scratch)
        authority = self._authorities.get(str(scratch))
        if authority is None or scratch.parent != self.runs:
            raise AtlasSandboxError("ATLAS_SANDBOX_SCRATCH_NOT_OWNED")
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_DIGEST_REQUIRED")
        _, _, control_fd, _, _ = authority
        name = f"{execution_id}.runtime"
        if not re.fullmatch(r"[A-Za-z0-9-]{1,128}\.runtime", name):
            raise AtlasSandboxError("ATLAS_SANDBOX_BAD_EXECUTION_ID")
        runtime_fd = None
        created = False
        try:
            runtime_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW, 0o500, dir_fd=control_fd)
            created = True
            os.fchmod(runtime_fd, 0o500)
            if os.fstat(runtime_fd).st_uid != os.getuid():
                raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_OWNER_MISMATCH")
            digest = hashlib.sha256()
            offset = 0
            while True:
                chunk = os.pread(sealed_fd, 1024 * 1024, offset)
                if not chunk:
                    break
                digest.update(chunk)
                written = 0
                while written < len(chunk):
                    count = os.write(runtime_fd, chunk[written:])
                    if count <= 0:
                        raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_COPY_FAILED")
                    written += count
                offset += len(chunk)
            if digest.hexdigest() != expected_sha256:
                raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_DIGEST_MISMATCH")
            os.fsync(runtime_fd)
            identity = os.fstat(runtime_fd)
            if (identity.st_uid != os.getuid() or
                    identity.st_mode & 0o777 != 0o500):
                raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_PERMISSIONS")
            os.fsync(control_fd)
            path = self.control / name
            self._runtime_authorities[str(path)] = (control_fd, identity)
            return path
        except (OSError, ValueError) as error:
            if isinstance(error, AtlasSandboxError):
                raise
            raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_MATERIALIZE_FAILED") from error
        finally:
            if runtime_fd is not None:
                try: os.close(runtime_fd)
                except OSError: pass
            if created and str(self.control / name) not in self._runtime_authorities:
                try: os.unlink(name, dir_fd=control_fd)
                except OSError: pass
                try: os.fsync(control_fd)
                except OSError: pass

    def remove_runtime(self, path: Path) -> None:
        """Unlink only the exact runtime inode created by materialize_runtime."""
        path = Path(path)
        if path.parent != self.control:
            raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_NOT_OWNED")
        record = self._runtime_authorities.get(str(path))
        if record is None:
            return
        control_fd, identity = record
        try:
            current = os.stat(path.name, dir_fd=control_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_CHANGED")
            os.unlink(path.name, dir_fd=control_fd)
            os.fsync(control_fd)
            self._runtime_authorities.pop(str(path), None)
        except OSError as error:
            raise AtlasSandboxError("ATLAS_SANDBOX_RUNTIME_REMOVE_FAILED") from error

class AtlasBubblewrapExecutor(CodexExecutor):
    """Codex executor whose remote execution environment is Atlas/bwrap."""

    SANDBOX_VERSION = "atlas-bwrap/1"
    STARTUP_TIMEOUT_SECONDS = 5

    def __init__(self, *args, bwrap="bwrap", scratch_root=Path("/var/tmp/atlas-agent"), **kwargs):
        super().__init__(*args, **kwargs)
        # The npm entrypoint is a dispatcher, not an executable that can be
        # mounted as the Linux Codex runtime.  Resolve it once and make every
        # subsequent identity check and sealed copy refer to the native image.
        native = _native_codex(self.executable)
        if native is not None:
            self.executable = str(native)
        self.bwrap = shutil.which(bwrap) or (bwrap if Path(bwrap).is_file() else None)
        self.scratch_store = ScratchStore(Path(scratch_root))
        self._server = None; self._server_stdin = None; self._server_url = None; self._scratch = None
        self._descriptor = None
        self._run_lock = threading.Lock()

    def _validate_policy(self):
        super()._validate_policy()
        if self.sandbox not in {"read-only", "workspace-write"}:
            raise AtlasSandboxError("ATLAS_SANDBOX_MODE_UNSUPPORTED")
        if not sys.platform.startswith("linux"):
            raise AtlasSandboxError("ATLAS_SANDBOX_LINUX_REQUIRED")
        if not self.bwrap:
            raise AtlasSandboxError("ATLAS_SANDBOX_BWRAP_NOT_FOUND")
        if not _native_codex(self.executable):
            raise AtlasSandboxError("ATLAS_SANDBOX_CODEX_NATIVE_NOT_FOUND")

    @staticmethod
    def _filesystem_class(path: Path) -> str:
        """Classify the mount actually backing path (Linux mountinfo)."""
        target = str(path.resolve())
        best = ("", "unknown")
        try:
            for line in Path("/proc/self/mountinfo").read_text().splitlines():
                left, right = line.split(" - ", 1); fields=left.split(); mount="/" + fields[4].lstrip("/")
                mount=mount.replace("\\040", " ").replace("\\011", "\t")
                fstype=right.split()[0]
                if target == mount or target.startswith(mount.rstrip("/") + "/"):
                    if len(mount) > len(best[0]): best=(mount,fstype)
        except (OSError, ValueError, IndexError):
            return "unknown"
        return "tmpfs" if best[1] in {"tmpfs","ramfs"} else ("disk" if best[1] != "unknown" else "unknown")

    def _validate_disk_scratch(self):
        if self._filesystem_class(self.scratch_store.root) != "disk":
            raise AtlasSandboxError("ATLAS_SANDBOX_DISK_SCRATCH_REQUIRED")

    def _validate_namespace(self) -> None:
        command = [self.bwrap, "--die-with-parent", "--unshare-pid", "--unshare-ipc",
                   "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                   "--ro-bind", "/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
                   "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--", "/bin/true"]
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AtlasSandboxError("ATLAS_SANDBOX_NAMESPACE_UNAVAILABLE") from error
        if result.returncode != 0:
            raise AtlasSandboxError("ATLAS_SANDBOX_NAMESPACE_UNAVAILABLE")

    def _git_dir(self, root: Path) -> Path:
        try:
            raw = subprocess.check_output(["git", "rev-parse", "--git-dir"], cwd=root, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError) as error:
            raise AtlasSandboxError("ATLAS_SANDBOX_GIT_TOPOLOGY_UNSUPPORTED") from error
        git_dir = Path(os.fsdecode(raw.rstrip(b"\r\n")))
        if not git_dir.is_absolute():
            git_dir = root / git_dir
        git_dir = git_dir.resolve()
        if git_dir != (root / ".git").resolve() or not git_dir.is_dir():
            raise AtlasSandboxError("ATLAS_SANDBOX_GIT_TOPOLOGY_UNSUPPORTED")
        return git_dir

    def _mount_command(self, spec, scratch: Path, runtime_path: Path | int, listen="ws://127.0.0.1:0") -> list[str]:
        root = spec.repository_root.resolve()
        git_dir = self._git_dir(root)
        mode = "read-only" if self.sandbox == "read-only" else "read-write"
        if isinstance(listen, int): listen=f"ws://127.0.0.1:{listen}"
        # Keep the small unit-test helper API source-compatible.  Production
        # startup always passes the controller-private materialized Path.
        if isinstance(runtime_path, int):
            runtime_path = Path(f"/proc/self/fd/{runtime_path}")
        args = [self.bwrap, "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc",
                "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                "--ro-bind", "/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
                "--symlink", "usr/sbin", "/sbin", "--ro-bind", "/etc", "/etc",
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/dev/shm",
                "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/home",
                "--dir", "/home/atlas", "--dir", "/home/atlas/.codex", "--dir", "/var", "--dir", "/var/tmp",
                "--bind", str(scratch), "/var/tmp",
                # The controller-private runtime is never mounted as scratch;
                # only its read-only bind is exposed at the Codex pathname.
                "--dir", "/opt",
                "--ro-bind", str(runtime_path), "/opt/atlas-codex",
                "--clearenv", "--setenv", "HOME", "/home/atlas", "--setenv", "CODEX_HOME", "/home/atlas/.codex",
                "--setenv", "TMPDIR", "/tmp", "--setenv", "PATH", "/usr/bin:/bin",
                "--chdir", str(root)]
        args += ["--ro-bind" if mode == "read-only" else "--bind", str(root), str(root)]
        # This nested readonly bind is the important implementation guard.
        if mode == "read-write":
            args += ["--ro-bind", str(git_dir), str(root / ".git")]
        args += ["--", "/opt/atlas-codex", "exec-server", "--listen", listen,
                 "--environment-id", f"atlas-{spec.execution_id}", "--exit-on-stdin-close"]
        return args

    def _start_server(self, spec, runtime_fd: int) -> None:
        self._scratch = self.scratch_store.create(str(spec.execution_id))
        try:
            snapshot = spec.policy_snapshot or {}
            runtime_path = self.scratch_store.materialize_runtime(
                self._scratch, str(spec.execution_id), runtime_fd,
                snapshot.get("codex_binary_sha256"),
            )
            command = self._mount_command(spec, self._scratch, runtime_path)
            self._server = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                pass_fds=(runtime_fd,),
            )
            self._server_stdin = self._server.stdin
            if self._server.stdout is None:
                raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_URL_UNAVAILABLE")
            fd = self._server.stdout.fileno()
            os.set_blocking(fd, False)
            deadline = time.monotonic() + self.STARTUP_TIMEOUT_SECONDS
            settle_deadline = None
            buffer = bytearray()
            endpoint = None
            while time.monotonic() < deadline:
                now = time.monotonic()
                wait = min(.05, deadline - now)
                if settle_deadline is not None:
                    wait = min(wait, max(0, settle_deadline - now))
                if self._server.poll() is not None and settle_deadline is None:
                    detail = (self._server.stderr.read() if self._server.stderr else b"").decode("utf-8", "replace")
                    raise AtlasSandboxError(f"ATLAS_SANDBOX_EXEC_SERVER_FAILED: {detail[:300]}")
                if select.select([fd], [], [], wait)[0]:
                    try: chunk = os.read(fd, 8192)
                    except BlockingIOError: continue
                    if not chunk:
                        if endpoint is None:
                            detail = (self._server.stderr.read() if self._server.stderr and
                                      self._server.poll() is not None else b"").decode("utf-8", "replace")
                            raise AtlasSandboxError(
                                f"ATLAS_SANDBOX_EXEC_SERVER_URL_UNAVAILABLE: {detail[:300]}"
                            )
                        if buffer:
                            raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_URL_MULTIPLE")
                        self._server_url = endpoint
                        return
                    buffer.extend(chunk)
                    if len(buffer) > 4096:
                        raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_URL_MALFORMED")
                    while b"\n" in buffer:
                        raw, _, remainder = buffer.partition(b"\n")
                        buffer = bytearray(remainder)
                        line = raw.decode("utf-8", "replace") + "\n"
                        match = re.fullmatch(r"ws://127\.0\.0\.1:([0-9]+)\n", line)
                        if endpoint is not None:
                            raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_URL_MULTIPLE")
                        if not match or not 1 <= int(match.group(1)) <= 65535:
                            raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_URL_MALFORMED")
                        endpoint = f"ws://127.0.0.1:{match.group(1)}"
                        # A short, non-zero protocol settling interval lets us
                        # detect competing declarations without readline or an
                        # unbounded wait.  The endpoint itself must be newline
                        # terminated; a partial second declaration is rejected.
                        settle_deadline = time.monotonic() + .1
                    if endpoint is not None and buffer and b"\n" not in buffer:
                        # Continue through the settling interval so a partial
                        # competing declaration cannot be silently ignored.
                        pass
                if settle_deadline is not None and time.monotonic() >= settle_deadline:
                    if buffer:
                        raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_URL_MULTIPLE")
                    self._server_url = endpoint
                    return
            raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_URL_UNAVAILABLE")
        except (OSError, AtlasSandboxError) as error:
            try:
                self._stop_server()
            except BaseException as cleanup_error:
                error.add_note(f"teardown: {type(cleanup_error).__name__}: {cleanup_error}")
                for note in getattr(cleanup_error, "__notes__", ()):
                    error.add_note(note)
            if isinstance(error, AtlasSandboxError):
                raise
            raise AtlasSandboxError(f"ATLAS_SANDBOX_EXEC_SERVER_LAUNCH_FAILED: {error}") from error

    def _stop_server(self) -> None:
        server, stdin, scratch = self._server, self._server_stdin, self._scratch
        errors = []
        def record(label, error):
            if error is not None:
                errors.append((label, error))
        if stdin is not None:
            try: stdin.close()
            except BaseException as error: record("teardown", error)
        reaped = server is None
        if server is not None:
            try:
                server.wait(timeout=2)
                reaped = True
            except subprocess.TimeoutExpired:
                try: server.send_signal(signal.SIGTERM)
                except BaseException as signal_error: record("teardown", signal_error)
                try:
                    server.wait(timeout=2)
                    reaped = True
                except subprocess.TimeoutExpired:
                    try: server.kill()
                    except BaseException as kill_error: record("teardown", kill_error)
                    try: server.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        record("teardown", AtlasSandboxError("ATLAS_SANDBOX_SERVER_UNREAPED"))
                    except BaseException as reap_error:
                        record("teardown", reap_error)
                        record("teardown", AtlasSandboxError("ATLAS_SANDBOX_SERVER_UNREAPED"))
                    else:
                        reaped = True
            except BaseException as error:
                record("teardown", error)
                try: server.send_signal(signal.SIGTERM)
                except BaseException as signal_error: record("teardown", signal_error)
                try:
                    server.wait(timeout=2)
                    reaped = True
                except subprocess.TimeoutExpired:
                    try: server.kill()
                    except BaseException as kill_error: record("teardown", kill_error)
                    try: server.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        record("teardown", AtlasSandboxError("ATLAS_SANDBOX_SERVER_UNREAPED"))
                    except BaseException as reap_error:
                        record("teardown", reap_error)
                        record("teardown", AtlasSandboxError("ATLAS_SANDBOX_SERVER_UNREAPED"))
                    else:
                        reaped = True
                except BaseException as term_error:
                    record("teardown", term_error)
                    try: server.kill()
                    except BaseException as kill_error: record("teardown", kill_error)
                    try: server.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        record("teardown", AtlasSandboxError("ATLAS_SANDBOX_SERVER_UNREAPED"))
                    except BaseException as reap_error:
                        record("teardown", reap_error)
                        record("teardown", AtlasSandboxError("ATLAS_SANDBOX_SERVER_UNREAPED"))
                    else:
                        reaped = True
            if server.stderr is not None:
                try: server.stderr.close()
                except BaseException as error: record("teardown", error)
        if reaped and scratch is not None:
            try:
                self.scratch_store.cleanup(scratch)
            except BaseException as error:
                record("cleanup", error)
        if reaped and not errors:
            self._server = self._server_stdin = self._scratch = self._server_url = None
        elif reaped and not any(isinstance(error, AtlasSandboxError) and
                                str(error) == "ATLAS_SANDBOX_SERVER_UNREAPED"
                                for _, error in errors):
            # Cleanup failures retain the handles so a later teardown can
            # retry; the child itself was nevertheless positively reaped.
            pass
        elif not reaped and not any(isinstance(error, AtlasSandboxError) and
                                    str(error) == "ATLAS_SANDBOX_SERVER_UNREAPED"
                                    for _, error in errors):
            record("teardown", AtlasSandboxError("ATLAS_SANDBOX_SERVER_UNREAPED"))
        if errors:
            _, primary = errors[0]
            for label, secondary in errors[1:]:
                primary.add_note(f"{label}: {type(secondary).__name__}: {secondary}")
            raise primary

    def _environment(self):
        if not isinstance(self._server_url, str) or not re.fullmatch(r"ws://127\.0\.0\.1:[1-9][0-9]{0,4}", self._server_url):
            raise AtlasSandboxError("ATLAS_SANDBOX_EXEC_SERVER_UNAVAILABLE")
        env = super()._environment()
        env["CODEX_EXEC_SERVER_URL"] = self._server_url
        return env

    def prepare_execution(self, spec):
        if not self._run_lock.acquire(blocking=False):
            raise AtlasSandboxError("ATLAS_SANDBOX_CONCURRENT_PREPARATION_UNSUPPORTED")
        keep_lock = False
        try:
            return self._prepare_execution_locked(spec)
        except BaseException:
            self._run_lock.release()
            raise

    def _prepare_execution_locked(self, spec):
        prepared = super().prepare_execution(spec)
        if spec.action in {"patch_review", "state_audit"} and self.network_access:
            raise AtlasSandboxError("ATLAS_SANDBOX_ACTION_NETWORK_MISMATCH")
        native = _native_codex(self.executable)
        if native is None:
            raise AtlasSandboxError("ATLAS_SANDBOX_CODEX_IDENTITY_MISMATCH")
        # super().prepare_execution() already authenticated and executed
        # the sealed Codex image for its version before RUN_STARTED.
        if not isinstance(prepared.version,str) or not prepared.version:
            raise AtlasSandboxError("ATLAS_SANDBOX_CODEX_VERSION_FAILED")
        bwrap_version = self._bwrap_version()
        self._validate_namespace()
        # Validate all host-side topology and scratch policy before RUN_STARTED.
        self._git_dir(spec.repository_root.resolve())
        expected={"patch_review":"read-only","state_audit":"read-only","implementation":"workspace-write"}
        if spec.action in expected and self.sandbox != expected[spec.action]:
            raise AtlasSandboxError("ATLAS_SANDBOX_ACTION_MODE_MISMATCH")
        self.scratch_store.ensure_root()
        self._validate_disk_scratch()
        self._descriptor = {
            "schema": self.SANDBOX_VERSION, "provider": "atlas", "backend": "bubblewrap",
            "filesystem_mode": self.sandbox, "filesystem_enforcement": "atlas-bwrap",
            "process_enforcement": "atlas-bwrap", "network_enforcement": "codex",
            "requested_network_access": self.network_access, "resolved_network_access": self.network_access,
            "user_namespace": "bwrap-default", "pid_namespace": True, "ipc_namespace": True,
            "mount_roles": ["usr-ro", "system-layout-ro", "etc-ro", "proc-new", "dev-new",
                            "tmp-private-tmpfs", "shm-private-tmpfs", "var-tmp-private-disk-scratch",
                            "home-private-ephemeral", "repository", "git-metadata-ro", "codex-native-ro"],
            "temporary_storage": {"tmp": "private-tmpfs", "shm": "private-tmpfs", "var_tmp": "private-disk-scratch"},
            "bwrap": self.bwrap, "bwrap_version": bwrap_version,
            "codex_executable": str(_native_codex(self.executable)), "codex_version": prepared.version,
            "scratch_backing_class": self._filesystem_class(self.scratch_store.root),
            "exec_server_transport": "CODEX_EXEC_SERVER_URL/websocket-loopback",
            "inner_codex_sandbox": self.sandbox, "inner_codex_network": "enabled" if self.network_access else "restricted",
        }
        return replace(prepared, runtime_handle=self._descriptor)

    def sandbox_descriptor(self):
        return dict(self._descriptor or {})

    def _bwrap_version(self):
        if not self.bwrap:
            return None
        try:
            result=subprocess.run(
                [self.bwrap,"--version"],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (OSError,subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    def info(self):
        info=super().info()
        info["atlas_bwrap"]=self._bwrap_version()
        return info

    def run_execution(self, prepared):
        if prepared.runtime_handle is not self._descriptor or not self._run_lock.locked():
            raise AtlasSandboxError("ATLAS_SANDBOX_PREPARATION_REQUIRED")

        primary=teardown=None
        result=None
        runtime_fd=None
        try:
            # Configuration is revalidated at the final boundary.  The
            # sealed memfd remains the controller-side execution source;
            # startup separately authenticates identical bytes for bwrap.
            self._validate_runtime_identity(prepared.policy_snapshot)
            runtime_fd=self._sealed_runtime_fd(prepared.policy_snapshot)
            self._validate_sealed_runtime_fd(
                runtime_fd,prepared.policy_snapshot
            )

            self._start_server(prepared.spec,runtime_fd)
            result=super().run_execution(
                prepared,
                _runtime_binary_fd=runtime_fd,
            )
        except BaseException as error:
            primary=error

        try:
            self._stop_server()
        except BaseException as error:
            teardown=error
        finally:
            if runtime_fd is not None:
                try: os.close(runtime_fd)
                except OSError: pass
            self._run_lock.release()

        if primary is not None:
            if teardown is not None:
                primary.add_note(
                    f"teardown: {type(teardown).__name__}: {teardown}"
                )
                for note in getattr(teardown,"__notes__",()):
                    primary.add_note(note)
            raise primary
        if teardown is not None:
            raise teardown
        return result
