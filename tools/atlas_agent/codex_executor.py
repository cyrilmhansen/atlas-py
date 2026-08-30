from __future__ import annotations
import fcntl, hashlib, json, os, re, select, shutil, signal, stat, subprocess, threading, time
from dataclasses import replace
from pathlib import Path
from .executor import ExecutorError, ExecutionResult, ExecutionSpec, PreparedExecution, utc_now, validate_permission_envelope
from .jsonl import DEFAULT_MAX_JSONL_LINE_BYTES, iter_bounded_jsonl
from .policy import POLICY_SCHEMA, SNAPSHOT_SCHEMA, PolicyError, validate_snapshot


def _toml_basic_string(value: str) -> str:
    """Encode one TOML basic string without escaping Unicode scalars."""
    escaped = []
    for char in value:
        code = ord(char)
        if char == "\\": escaped.append("\\\\")
        elif char == '"': escaped.append('\\"')
        elif char == "\b": escaped.append("\\b")
        elif char == "\t": escaped.append("\\t")
        elif char == "\n": escaped.append("\\n")
        elif char == "\f": escaped.append("\\f")
        elif char == "\r": escaped.append("\\r")
        elif code < 0x20 or code == 0x7f: escaped.append(f"\\u{code:04x}")
        else: escaped.append(char)
    return '"' + "".join(escaped) + '"'

class CodexExecutor:
    SHUTDOWN_GRACE_SECONDS=5
    SHUTDOWN_KILL_SECONDS=5
    def __init__(self, executable="codex", model=None, sandbox="read-only", ephemeral=True,
                 sandbox_mode=None, approval_policy="never", approvals_reviewer="user",
                 ignore_rules=True, strict_config=True, network_access=False, timeout_seconds=300,
                 progress_callback=None, heartbeat_seconds=30, codex_home=None):
        if executable == "codex":
            executable = os.environ.get("ATLAS_CODEX_EXECUTABLE", executable)
        self.codex_home = Path(
            codex_home
            or os.environ.get("ATLAS_CODEX_HOME")
            or (Path.home()/".local/share/atlas-agent/codex-home")
        ).expanduser()
        resolved=shutil.which(executable) or (executable if Path(executable).is_file() else None)
        self.executable=str(Path(resolved).resolve(strict=True)) if resolved else None
        self.model=model; self.sandbox=sandbox_mode or sandbox; self.sandbox_mode=self.sandbox; self.ephemeral=ephemeral
        self.approval_policy=approval_policy; self.approvals_reviewer=approvals_reviewer
        self.ignore_rules=ignore_rules; self.strict_config=strict_config; self.network_access=network_access
        self.timeout_seconds=timeout_seconds
        self.progress_callback=progress_callback; self.heartbeat_seconds=heartbeat_seconds
    def _envelope(self):
        return {"sandbox_mode":self.sandbox,"approval_policy":self.approval_policy,"approvals_reviewer":self.approvals_reviewer,"strict_config":self.strict_config,"ignore_rules":self.ignore_rules,"network_access":self.network_access}
    def _validate_policy(self):
        if self.sandbox not in {"read-only","workspace-write","danger-full-access"}: raise ExecutorError("UNSUPPORTED_SANDBOX")
        validate_permission_envelope(self._envelope())
        if isinstance(self.timeout_seconds,bool) or not isinstance(self.timeout_seconds,(int,float)) or self.timeout_seconds <= 0: raise ExecutorError("INVALID_TIMEOUT")
        if isinstance(self.heartbeat_seconds,bool) or not isinstance(self.heartbeat_seconds,(int,float)) or self.heartbeat_seconds <= 0: raise ExecutorError("INVALID_HEARTBEAT_INTERVAL")
    def _environment(self):
        env = dict(os.environ)
        env["CODEX_HOME"] = str(self.codex_home)
        return env
    @staticmethod
    def _trusted_directory(path):
        path=Path(path)
        if not path.is_absolute():
            raise ExecutorError("CODEX_HOME_UNTRUSTED")
        try:
            st=path.lstat()
            if path.resolve(strict=True) != path:
                raise ExecutorError("CODEX_HOME_UNTRUSTED")
        except (OSError, RuntimeError) as error:
            raise ExecutorError("CODEX_HOME_UNTRUSTED") from error
        if (
            stat.S_ISLNK(st.st_mode) or
            not stat.S_ISDIR(st.st_mode) or
            st.st_uid not in {0, os.geteuid()} or
            st.st_mode & 0o022
        ):
            raise ExecutorError("CODEX_HOME_UNTRUSTED")

    @staticmethod
    def _trusted_file_sha256(path, *, executable=False, error_code="CODEX_RUNTIME_FILE_UNTRUSTED"):
        path=Path(path)
        if not path.is_absolute():
            raise ExecutorError(error_code)
        flags=os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            if path.resolve(strict=True) != path:
                raise ExecutorError(error_code)
            fd=os.open(path, flags)
        except (OSError, RuntimeError) as error:
            raise ExecutorError(error_code) from error
        try:
            st=os.fstat(fd)
            if (
                not stat.S_ISREG(st.st_mode) or
                st.st_mode & 0o022 or
                (executable and not (st.st_mode & 0o111))
            ):
                raise ExecutorError(error_code)
            digest=hashlib.sha256()
            while True:
                chunk=os.read(fd, 1024*1024)
                if not chunk:
                    break
                digest.update(chunk)
            return digest.hexdigest()
        finally:
            os.close(fd)

    def _require_executable_snapshot(self, snapshot):
        try:
            validated=validate_snapshot(snapshot)
        except (PolicyError, TypeError, AttributeError) as error:
            raise ExecutorError("POLICY_SNAPSHOT_NOT_EXECUTABLE") from error
        if (
            validated.get("schema") != SNAPSHOT_SCHEMA
            or validated.get("policy_schema") != POLICY_SCHEMA
            or validated.get("executor") != "codex"
            or not isinstance(validated.get("codex_profile"),str)
        ):
            raise ExecutorError("POLICY_SNAPSHOT_NOT_EXECUTABLE")
        return validated

    def _validate_runtime_identity(self, snapshot):
        snapshot=self._require_executable_snapshot(snapshot)
        if not self.executable:
            raise ExecutorError("CODEX_NOT_FOUND")

        self._trusted_directory(self.codex_home)

        profile=snapshot["codex_profile"]
        paths={
            "codex_binary_sha256": Path(self.executable),
            "codex_config_sha256": self.codex_home/"config.toml",
            "codex_catalog_sha256": self.codex_home/"models-atlas-shell-only.json",
            "codex_profile_sha256": self.codex_home/f"{profile}.config.toml",
        }
        codes={
            "codex_binary_sha256": "CODEX_EXECUTABLE_DIGEST_MISMATCH",
            "codex_config_sha256": "CODEX_CONFIG_DIGEST_MISMATCH",
            "codex_catalog_sha256": "CODEX_CATALOG_DIGEST_MISMATCH",
            "codex_profile_sha256": "CODEX_PROFILE_DIGEST_MISMATCH",
        }
        for key,path in paths.items():
            actual=self._trusted_file_sha256(
                path,
                executable=(key=="codex_binary_sha256"),
                error_code=codes[key],
            )
            if actual != snapshot.get(key):
                raise ExecutorError(codes[key])

    def _sealed_runtime_fd(self, snapshot):
        """Create an immutable executable copy of the pinned Codex inode."""
        if (
            not isinstance(snapshot,dict)
            or snapshot.get("schema") != SNAPSHOT_SCHEMA
            or not self.executable
        ):
            raise ExecutorError("CODEX_PINNED_RUNTIME_REQUIRED")

        source=Path(self.executable)
        flags=os.O_RDONLY | getattr(os,"O_NOFOLLOW",0)
        try:
            if not source.is_absolute() or source.resolve(strict=True) != source:
                raise ExecutorError("CODEX_EXECUTABLE_DIGEST_MISMATCH")
            source_fd=os.open(source,flags)
        except (OSError,RuntimeError) as error:
            raise ExecutorError("CODEX_EXECUTABLE_DIGEST_MISMATCH") from error

        runtime_fd=None
        try:
            st=os.fstat(source_fd)
            if (
                not stat.S_ISREG(st.st_mode)
                or st.st_mode & 0o022
                or not (st.st_mode & 0o111)
            ):
                raise ExecutorError("CODEX_EXECUTABLE_DIGEST_MISMATCH")

            if not hasattr(os,"memfd_create") or not hasattr(os,"MFD_ALLOW_SEALING"):
                raise ExecutorError("CODEX_PINNED_RUNTIME_UNAVAILABLE")

            runtime_fd=os.memfd_create(
                "atlas-codex-runtime",
                os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
            )

            digest=hashlib.sha256()
            while True:
                chunk=os.read(source_fd,1024*1024)
                if not chunk:
                    break
                digest.update(chunk)
                offset=0
                while offset<len(chunk):
                    written=os.write(runtime_fd,chunk[offset:])
                    if written<=0:
                        raise ExecutorError("CODEX_PINNED_RUNTIME_COPY_FAILED")
                    offset+=written

            if digest.hexdigest()!=snapshot.get("codex_binary_sha256"):
                raise ExecutorError("CODEX_EXECUTABLE_DIGEST_MISMATCH")

            os.fchmod(runtime_fd,0o500)

            required_seals=(
                fcntl.F_SEAL_SEAL
                | fcntl.F_SEAL_SHRINK
                | fcntl.F_SEAL_GROW
                | fcntl.F_SEAL_WRITE
            )
            fcntl.fcntl(runtime_fd,fcntl.F_ADD_SEALS,required_seals)
            actual_seals=fcntl.fcntl(runtime_fd,fcntl.F_GET_SEALS)
            if actual_seals & required_seals != required_seals:
                raise ExecutorError("CODEX_PINNED_RUNTIME_UNSEALED")

            return runtime_fd
        except BaseException:
            if runtime_fd is not None:
                try: os.close(runtime_fd)
                except OSError: pass
            raise
        finally:
            os.close(source_fd)

    @staticmethod
    def _validate_sealed_runtime_fd(fd,snapshot):
        if type(fd) is not int or fd<0:
            raise ExecutorError("CODEX_PINNED_RUNTIME_INVALID")
        try:
            st=os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ExecutorError("CODEX_PINNED_RUNTIME_INVALID")

            required_seals=(
                fcntl.F_SEAL_SEAL
                | fcntl.F_SEAL_SHRINK
                | fcntl.F_SEAL_GROW
                | fcntl.F_SEAL_WRITE
            )
            if fcntl.fcntl(fd,fcntl.F_GET_SEALS) & required_seals != required_seals:
                raise ExecutorError("CODEX_PINNED_RUNTIME_UNSEALED")

            digest=hashlib.sha256()
            offset=0
            while True:
                chunk=os.pread(fd,1024*1024,offset)
                if not chunk:
                    break
                digest.update(chunk)
                offset+=len(chunk)
            if digest.hexdigest()!=snapshot.get("codex_binary_sha256"):
                raise ExecutorError("CODEX_EXECUTABLE_DIGEST_MISMATCH")
        except OSError as error:
            raise ExecutorError("CODEX_PINNED_RUNTIME_INVALID") from error

    def _build_command(self,spec,snapshot):
        codex_profile=snapshot.get("codex_profile") if snapshot else None
        reuse=bool(snapshot and snapshot.get("session_mode")=="reuse")
        requested_thread_id=snapshot.get("requested_thread_id") if reuse else None
        if reuse and (not isinstance(requested_thread_id,str) or not requested_thread_id):
            raise ExecutorError("REUSE_TARGET_MISSING")

        argv=[self.executable]
        if codex_profile:
            argv += ["--profile",codex_profile]
        argv += ["exec","resume"] if reuse else ["exec"]
        argv += ["--json"]
        if not reuse:
            argv += ["-C",str(spec.repository_root)]
        if reuse:
            argv += ["-c",f'sandbox_mode="{self.sandbox}"']
        else:
            argv += ["--sandbox",self.sandbox]

        if snapshot and not codex_profile:
            argv.append("--ignore-user-config")
        if self.strict_config:
            argv.append("--strict-config")
        if self.ignore_rules:
            argv.append("--ignore-rules")

        argv += [
            "-c",f'approval_policy="{self.approval_policy}"',
            "-c",f'approvals_reviewer="{self.approvals_reviewer}"',
        ]
        if snapshot:
            argv += [
                "-c","features.apps=false",
                "-c",f'web_search="{snapshot["web_search"]}"',
            ]
        if self.sandbox=="workspace-write":
            argv += [
                "-c",
                f"sandbox_workspace_write.network_access={str(self.network_access).lower()}",
            ]
        if snapshot:
            argv += [
                "-c",
                f'model_reasoning_effort="{snapshot["requested_reasoning_effort"]}"',
            ]
            if snapshot["action"] == "state_audit":
                role_path = self.codex_home / "atlas-agent-prompts" / "state_audit.md"
                try:
                    role_instructions = role_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as error:
                    raise ExecutorError("ATLAS_STATE_AUDIT_PROMPT_MISSING") from error
                argv += ["-c", f"developer_instructions={_toml_basic_string(role_instructions)}"]
        if self.ephemeral and (
            not snapshot or snapshot.get("session_storage")=="ephemeral"
        ):
            argv.append("--ephemeral")
        if self.model:
            argv += ["--model",self.model]

        argv += [requested_thread_id,"-"] if reuse else ["-"]
        return tuple(argv)

    def _validated_runtime_command(self,prepared,runtime_fd=None):
        if prepared.policy_snapshot != prepared.spec.policy_snapshot:
            raise ExecutorError("POLICY_SNAPSHOT_BINDING_MISMATCH")
        snapshot=self._require_executable_snapshot(prepared.policy_snapshot)
        self._validate_runtime_identity(snapshot)

        expected=self._build_command(prepared.spec,snapshot)
        if prepared.command!=expected:
            raise ExecutorError("PREPARED_COMMAND_MISMATCH")

        owned=False
        if runtime_fd is None:
            runtime_fd=self._sealed_runtime_fd(snapshot)
            owned=True
        else:
            self._validate_sealed_runtime_fd(runtime_fd,snapshot)

        command=list(expected)
        command[0]=f"/proc/self/fd/{runtime_fd}"
        return command,(runtime_fd,),runtime_fd if owned else None

    def _runtime_info(self, snapshot, runtime_fd):
        """Probe only the sealed, policy-bound Codex image."""
        snapshot=self._require_executable_snapshot(snapshot)
        self._validate_sealed_runtime_fd(runtime_fd,snapshot)
        try:
            p=subprocess.run(
                [f"/proc/self/fd/{runtime_fd}","--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=5,
                pass_fds=(runtime_fd,),
            )
        except (OSError,subprocess.TimeoutExpired) as error:
            raise ExecutorError("CODEX_VERSION_FAILED") from error
        version=(p.stdout or p.stderr).decode("utf-8","replace").strip()
        if p.returncode != 0 or not version:
            raise ExecutorError("CODEX_VERSION_FAILED")
        return {
            "executor":"codex",
            "executable":self.executable,
            "available":True,
            "version":version,
            "capabilities":["exec","jsonl","stdin-prompt","model","sandbox","ephemeral","resume"],
        }

    def info(self):
        """Diagnostic metadata only; never execute an unpinned pathname."""
        available=False
        if self.executable:
            try:
                available=Path(self.executable).is_file()
            except OSError:
                available=False
        return {
            "executor":"codex",
            "executable":self.executable,
            "available":available,
            "version":None,
            "capabilities":["exec","jsonl","stdin-prompt","model","sandbox","ephemeral","resume"],
        }
    def prepare_execution(self,spec):
        self._validate_policy()
        if not self.executable: raise ExecutorError("CODEX_NOT_FOUND")
        if spec.input_mode not in {"legacy", "bytes-v1"}: raise ExecutorError("INVALID_EXECUTION_INPUT_MODE")
        if spec.input_mode == "bytes-v1" and (not isinstance(spec.prompt_bytes, bytes) or not isinstance(spec.expected_input_sha256, str)):
            raise ExecutorError("EXECUTION_INPUT_MISSING")
        if spec.input_mode == "bytes-v1" and hashlib.sha256(spec.prompt_bytes).hexdigest() != spec.expected_input_sha256:
            raise ExecutorError("EXECUTION_INPUT_HASH_MISMATCH")
        if not spec.prompt_path.is_file(): raise ExecutorError("PROMPT_MISSING")
        snapshot=self._require_executable_snapshot(spec.policy_snapshot)
        codex_profile=snapshot["codex_profile"]
        if (
            self.model != snapshot.get("requested_model")
            or self.approval_policy != "never"
            or self.approvals_reviewer != "user"
            or self.sandbox != snapshot.get("sandbox_mode")
            or self.network_access != snapshot.get("network_access")
        ):
            raise ExecutorError("POLICY_RESOLUTION_MISMATCH")
        if not re.fullmatch(r"atlas-[a-z0-9-]+-(?:local|web)",codex_profile):
            raise ExecutorError("CODEX_PROFILE_INVALID")
        self._validate_runtime_identity(snapshot)

        # Version identification is part of the pre-RUN_STARTED trust
        # boundary.  Execute only bytes copied into a sealed memfd whose
        # digest was already authenticated against the policy snapshot.
        runtime_fd=self._sealed_runtime_fd(snapshot)
        try:
            info=self._runtime_info(snapshot,runtime_fd)
        finally:
            os.close(runtime_fd)

        command=self._build_command(spec,snapshot)
        return PreparedExecution(
            spec,"codex",command,info["version"],
            self._envelope(),snapshot,
        )

    def post_start_prepare(self, prepared):
        # No subprocess or fallible runtime probing is permitted after the
        # durable RUN_STARTED boundary.
        return prepared
    @staticmethod
    def _permission_observations(out_path, err_path, max_line_bytes=DEFAULT_MAX_JSONL_LINE_BYTES):
        failures=[]
        patterns=(r"permission denied",r"sandbox",r"approval required",r"outside.*workspace",r"not allowed",r"forbidden")
        for source, path in (("stdout",out_path),("stderr",err_path)):
            if isinstance(path,(bytes,bytearray)):
                lines=bytes(path).splitlines()
                iterator=((line, False) for line in lines)
            else:
                iterator=iter_bounded_jsonl(Path(path), max_line_bytes=max_line_bytes)
            for raw, oversized in iterator:
                if oversized:
                    continue
                line=raw.decode("utf-8","replace").rstrip("\r\n")
                low=line.lower()
                if any(re.search(pattern,low) for pattern in patterns): failures.append({"source":source,"message":line[:1000]})
        return ("observed",failures) if failures else ("unavailable",None)
    @staticmethod
    def _session_id_from_stdout(path, max_line_bytes=DEFAULT_MAX_JSONL_LINE_BYTES):
        for line, oversized in iter_bounded_jsonl(Path(path), max_line_bytes=max_line_bytes):
            if oversized:
                continue
            try: event=json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(event, dict) and event.get("type") in {"thread.started", "session.started"}:
                return event.get("thread_id") or event.get("session_id") or event.get("id")
        return None
    @staticmethod
    def _agent_message(event):
        """Return text only for Codex's completed agent-message event."""
        if not isinstance(event,dict) or event.get("type")!="item.completed": return None
        item=event.get("item")
        if not isinstance(item,dict) or item.get("type")!="agent_message": return None
        text=item.get("text")
        return text if isinstance(text,str) and text.strip() else None
    @classmethod
    def latest_agent_report(cls,path,max_line_bytes=DEFAULT_MAX_JSONL_LINE_BYTES,max_file_bytes=64*1024*1024):
        """Extract the final Codex report with explicit input bounds."""
        path=Path(path)
        if not path.is_file(): raise ExecutorError("EXECUTOR_OUTPUT_MISSING")
        try: size=path.stat().st_size
        except OSError as error: raise ExecutorError(f"EXECUTOR_OUTPUT_UNREADABLE: {error}") from error
        if size>max_file_bytes: raise ExecutorError("EXECUTOR_OUTPUT_TOO_LARGE")
        latest=None
        ambiguous=False
        try:
            for line,oversized in iter_bounded_jsonl(path,max_line_bytes=max_line_bytes):
                if oversized:
                    # The record has deliberately not been retained, so it
                    # may be a later agent message.  Keep scanning for a
                    # completed message that proves it was not the report.
                    ambiguous=True
                    continue
                try: event=json.loads(line)
                except (UnicodeDecodeError,json.JSONDecodeError) as error:
                    raise ExecutorError(f"EXECUTOR_OUTPUT_MALFORMED: {error}") from error
                if not isinstance(event,dict): raise ExecutorError("EXECUTOR_OUTPUT_MALFORMED: JSONL record is not an object")
                message=cls._agent_message(event)
                if message is not None:
                    latest=message
                    ambiguous=False
        except OSError as error: raise ExecutorError(f"EXECUTOR_OUTPUT_UNREADABLE: {error}") from error
        if ambiguous:
            raise ExecutorError("EXECUTOR_OUTPUT_MALFORMED: oversized JSONL record")
        if latest is None: raise ExecutorError("EXECUTION_REPORT_MISSING")
        return latest
    def _progress(self,kind,elapsed,text=None):
        if self.progress_callback is None: return
        self.progress_callback({"kind":kind,"elapsed_seconds":elapsed,"message":text})
    def _consume_progress_line(self,line,elapsed):
        try: event=json.loads(line)
        except (UnicodeDecodeError,json.JSONDecodeError): return False
        message=self._agent_message(event)
        if message is None: return False
        self._progress("agent_message",elapsed,message)
        return True
    def _terminate_and_reap(self,proc):
        """Bounded shutdown shared by timeout and stream-failure paths."""
        try: os.killpg(proc.pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError): pass
        try: exit_code=proc.wait(timeout=self.SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired: exit_code=None
        try: os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass
        try:
            final=proc.wait(timeout=self.SHUTDOWN_KILL_SECONDS)
            return final if exit_code is None else exit_code
        except subprocess.TimeoutExpired as error:
            raise ExecutorError("CODEX_PROCESS_UNREAPED") from error

    @staticmethod
    def _close_stdin(prompt, state):
        try: prompt.close()
        except Exception as error: state["close_error"] = error
    def run_execution(self,prepared,_runtime_binary_fd=None):
        command,pass_fds,owned_fd=self._validated_runtime_command(
            prepared,_runtime_binary_fd
        )
        try:
            return self._run_execution_inner(
                prepared,command,pass_fds
            )
        finally:
            if owned_fd is not None:
                try: os.close(owned_fd)
                except OSError: pass

    def _run_execution_inner(self,prepared,launch_command,pass_fds):
        spec=prepared.spec; spec.report_dir.mkdir(parents=True,exist_ok=True)
        out=spec.report_dir/"stdout.log"; err=spec.report_dir/"stderr.log"; started=utc_now()
        try:
            with out.open("wb") as stdout, err.open("wb") as stderr:
                prompt_bytes=spec.prompt_bytes
                if spec.input_mode == "bytes-v1" and (not isinstance(prompt_bytes, bytes) or not isinstance(spec.expected_input_sha256, str)):
                    raise ExecutorError("EXECUTION_INPUT_MISSING")
                if prompt_bytes is None:
                    try: prompt_bytes=spec.prompt_path.read_bytes()
                    except OSError as error: raise ExecutorError("EXECUTION_INPUT_MISSING") from error
                # prepare_execution validates the original request, but the
                # run boundary is the final trust boundary before handoff.
                # Recheck the exact bytes that the writer will send so a
                # mutated PreparedExecution cannot launch an unverified child.
                if spec.input_mode == "bytes-v1" and hashlib.sha256(prompt_bytes).hexdigest() != spec.expected_input_sha256:
                    raise ExecutorError("EXECUTION_INPUT_HASH_MISMATCH")
                begun=time.monotonic(); deadline=begun+self.timeout_seconds
                # Keep the ownership guard adjacent to Popen: once it returns,
                # the new session belongs to Atlas even if setup is interrupted
                # before any stream has been configured.
                try:
                    # Final trust-boundary revalidation: configuration or the
                    # pinned fork may not change between prepare and exec.
                    self._validate_runtime_identity(prepared.policy_snapshot)
                    proc=subprocess.Popen(
                        launch_command,
                        cwd=spec.repository_root,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=stderr,
                        start_new_session=True,
                        env=self._environment(),
                        pass_fds=pass_fds,
                    )
                except OSError as error:
                    raise ExecutorError(f"CODEX_LAUNCH_FAILED: {error}") from error
                try:
                    # This is the first instruction after a successful Popen;
                    # every subsequent setup operation is covered by the
                    # ownership cleanup handler.
                    prompt=None; stdin_fd=None; writer=None
                    prompt=proc.stdin
                    stdin_fd=prompt.fileno(); os.set_blocking(stdin_fd,False)
                    writer_done=threading.Event(); writer_state={"error":None,"close_error":None,"hash":hashlib.sha256(),"written":0}
                    def write_stdin():
                        try:
                            offset=0
                            while offset<len(prompt_bytes):
                                try: count=os.write(stdin_fd,prompt_bytes[offset:])
                                except BlockingIOError: time.sleep(0.005); continue
                                if count<=0: raise OSError("stdin write returned no progress")
                                writer_state["hash"].update(prompt_bytes[offset:offset+count]); writer_state["written"]+=count; offset+=count
                        except Exception as error:
                            writer_state["error"]=error
                        finally:
                            # The parent owns this stream too. Closing it after
                            # the last write is what delivers EOF to the child.
                            self._close_stdin(prompt, writer_state)
                            writer_done.set()
                    writer=threading.Thread(target=write_stdin,daemon=True); writer.start()
                    stdout_fd=proc.stdout.fileno(); os.set_blocking(stdout_fd,False)
                except BaseException as error:
                    # Popen transfers process-group ownership immediately;
                    # setup failures must use the same bounded cleanup path.
                    try: self._terminate_and_reap(proc)
                    except Exception as shutdown_error: error.add_note(f"bounded executor shutdown also failed: {shutdown_error}")
                    if stdin_fd is not None and (writer is None or not writer_done.is_set()):
                        try: os.close(stdin_fd)
                        except OSError: pass
                    if writer is not None:
                        writer.join(timeout=self.SHUTDOWN_GRACE_SECONDS+self.SHUTDOWN_KILL_SECONDS)
                    if proc.stdout is not None:
                        try: proc.stdout.close()
                        except OSError: pass
                    raise
                last_useful=begun
                line=bytearray(); oversized=False; timed_out=False; shutdown_attempted=False; stdout_eof=False
                try:
                    while True:
                        now=time.monotonic(); remaining=deadline-now
                        if remaining<=0:
                            timed_out=True; shutdown_attempted=True; exit_code=self._terminate_and_reap(proc); break
                        heartbeat_due=last_useful+self.heartbeat_seconds
                        wait_for=max(0,min(1,remaining,max(0,heartbeat_due-now)))
                        if stdout_eof:
                            try: exit_code=proc.wait(timeout=wait_for); break
                            except subprocess.TimeoutExpired:
                                now=time.monotonic()
                                if now>=heartbeat_due:
                                    self._progress("heartbeat",now-begun); last_useful=now
                                continue
                        if writer_state["error"] is not None:
                            raise ExecutorError(f"CODEX_INPUT_WRITE_FAILED: {writer_state['error']}") from writer_state["error"]
                        if writer_state["close_error"] is not None:
                            raise ExecutorError(f"CODEX_INPUT_CLOSE_FAILED: {writer_state['close_error']}") from writer_state["close_error"]
                        readable=select.select([] if stdout_eof else [stdout_fd],[],[],wait_for)[0]
                        if readable:
                            try: value=os.read(stdout_fd,8192)
                            except OSError as error: raise ExecutorError(f"CODEX_STDOUT_READ_FAILED: {error}") from error
                            if not value:
                                if line and not oversized: self._consume_progress_line(bytes(line),time.monotonic()-begun)
                                stdout_eof=True
                            else:
                                stdout.write(value); stdout.flush()
                                for byte in value:
                                    if byte==10:
                                        if not oversized and self._consume_progress_line(bytes(line),time.monotonic()-begun): last_useful=time.monotonic()
                                        line.clear(); oversized=False
                                    elif not oversized:
                                        if len(line)<DEFAULT_MAX_JSONL_LINE_BYTES: line.append(byte)
                                        else: oversized=True
                        if proc.poll() is not None and stdout_eof and writer_done.is_set(): exit_code=proc.returncode; break
                        now=time.monotonic()
                        if now>=heartbeat_due:
                            self._progress("heartbeat",now-begun); last_useful=now
                except BaseException as error:
                    if not shutdown_attempted:
                        shutdown_attempted=True
                        try: self._terminate_and_reap(proc)
                        except Exception as shutdown_error: error.add_note(f"bounded executor shutdown also failed: {shutdown_error}")
                    if isinstance(error,ExecutorError): raise
                    if isinstance(error,KeyboardInterrupt): raise
                    raise ExecutorError(f"CODEX_STREAM_FAILED: {error}") from error
                finally:
                    if not writer_done.is_set():
                        try: os.close(stdin_fd)
                        except OSError: pass
                    writer.join(timeout=self.SHUTDOWN_GRACE_SECONDS+self.SHUTDOWN_KILL_SECONDS)
                    if writer.is_alive(): raise ExecutorError("CODEX_INPUT_WRITER_UNREAPED")
                    if not shutdown_attempted:
                        shutdown_attempted=True; exit_code=self._terminate_and_reap(proc)
                    if proc.stdout is not None:
                        try: proc.stdout.close()
                        except OSError: pass
                if writer_state["error"] is not None:
                    raise ExecutorError(f"CODEX_INPUT_WRITE_FAILED: {writer_state['error']}") from writer_state["error"]
                if writer_state["close_error"] is not None:
                    raise ExecutorError(f"CODEX_INPUT_CLOSE_FAILED: {writer_state['close_error']}") from writer_state["close_error"]
        except ExecutorError: raise
        except OSError as error: raise ExecutorError(f"CODEX_STREAM_FAILED: {error}") from error
        session_id=None
        try:
            session_id=self._session_id_from_stdout(out)
        except OSError: pass
        timed_out=locals().get("timed_out",False)
        try: status, failures=self._permission_observations(out,err)
        except OSError: status, failures="partial",None
        finished=utc_now(); outcome="timeout" if timed_out else ("success" if exit_code==0 else "failed"); root=spec.runtime_root or spec.repository_root
        supplied_hash=writer_state["hash"].hexdigest()
        if writer_state["written"] != len(prompt_bytes): raise ExecutorError("EXECUTION_INPUT_HANDOFF_INCOMPLETE")
        if spec.input_mode == "bytes-v1" and supplied_hash != spec.expected_input_sha256: raise ExecutorError("EXECUTION_INPUT_HASH_MISMATCH")
        return ExecutionResult(str(spec.execution_id),prepared.executor,list(prepared.command),prepared.version,started,finished,exit_code,str(out.relative_to(root)),str(err.relative_to(root)),session_id,outcome,str((spec.report_dir/"result.json").relative_to(root)),prepared.permission_envelope,status,failures,timed_out,prepared.policy_snapshot,None,None,supplied_hash)
