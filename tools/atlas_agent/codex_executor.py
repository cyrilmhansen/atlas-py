from __future__ import annotations
import json, os, queue, re, shutil, signal, subprocess, threading, time
from dataclasses import replace
from pathlib import Path
from .executor import ExecutorError, ExecutionResult, ExecutionSpec, PreparedExecution, utc_now, validate_permission_envelope
from .jsonl import DEFAULT_MAX_JSONL_LINE_BYTES, iter_bounded_jsonl

class CodexExecutor:
    SHUTDOWN_GRACE_SECONDS=5
    SHUTDOWN_KILL_SECONDS=5
    def __init__(self, executable="codex", model=None, sandbox="read-only", ephemeral=True,
                 sandbox_mode=None, approval_policy="never", approvals_reviewer="user",
                 ignore_rules=True, strict_config=True, network_access=False, timeout_seconds=300,
                 progress_callback=None, heartbeat_seconds=30):
        self.executable=shutil.which(executable) or (executable if Path(executable).is_file() else None)
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
    def info(self):
        if not self.executable: return {"executor":"codex","executable":None,"available":False,"version":None,"capabilities":[]}
        p=subprocess.run([self.executable,"--version"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        version=(p.stdout or p.stderr).decode("utf-8","replace").strip()
        return {"executor":"codex","executable":self.executable,"available":p.returncode==0,"version":version,"capabilities":["exec","jsonl","stdin-prompt","model","sandbox","ephemeral","resume"]}
    def prepare_execution(self,spec):
        self._validate_policy()
        if not self.executable: raise ExecutorError("CODEX_NOT_FOUND")
        if not spec.prompt_path.is_file(): raise ExecutorError("PROMPT_MISSING")
        snapshot=spec.policy_snapshot
        if snapshot:
            if snapshot.get("executor")!="codex" or self.model != snapshot.get("requested_model") or self.approval_policy != "never" or self.approvals_reviewer != "user" or self.sandbox != snapshot.get("sandbox_mode") or self.network_access != snapshot.get("network_access"):
                raise ExecutorError("POLICY_RESOLUTION_MISMATCH")
        reuse=bool(snapshot and snapshot.get("session_mode")=="reuse")
        requested_thread_id=snapshot.get("requested_thread_id") if reuse else None
        if reuse and (not isinstance(requested_thread_id,str) or not requested_thread_id):
            raise ExecutorError("REUSE_TARGET_MISSING")
        argv=[self.executable,"exec","resume"] if reuse else [self.executable,"exec"]
        argv += ["--json"]
        if not reuse: argv += ["-C",str(spec.repository_root)]
        if reuse: argv += ["-c",f'sandbox_mode="{self.sandbox}"']
        else: argv += ["--sandbox",self.sandbox]
        if snapshot: argv.append("--ignore-user-config")
        if self.strict_config: argv.append("--strict-config")
        if self.ignore_rules: argv.append("--ignore-rules")
        argv += ["-c",f'approval_policy="{self.approval_policy}"',"-c",f'approvals_reviewer="{self.approvals_reviewer}"']
        if snapshot:
            argv += ["-c","features.apps=false","-c","web_search=\"disabled\""]
        if self.sandbox == "workspace-write": argv += ["-c",f"sandbox_workspace_write.network_access={str(self.network_access).lower()}"]
        if snapshot:
            argv += ["-c",f'model_reasoning_effort="{snapshot["requested_reasoning_effort"]}"']
        if self.ephemeral and (not snapshot or snapshot.get("session_storage")=="ephemeral"): argv.append("--ephemeral")
        if self.model: argv += ["--model",self.model]
        argv += [requested_thread_id,"-"] if reuse else ["-"]
        return PreparedExecution(spec,"codex",tuple(argv),"unresolved",self._envelope(),snapshot)
    def post_start_prepare(self, prepared):
        info=self.info()
        if not info["available"]: raise ExecutorError("CODEX_VERSION_FAILED")
        return replace(prepared, version=info["version"])
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
        try:
            for line,oversized in iter_bounded_jsonl(path,max_line_bytes=max_line_bytes):
                if oversized: raise ExecutorError("EXECUTOR_OUTPUT_MALFORMED: oversized JSONL record")
                try: event=json.loads(line)
                except (UnicodeDecodeError,json.JSONDecodeError) as error:
                    raise ExecutorError(f"EXECUTOR_OUTPUT_MALFORMED: {error}") from error
                if not isinstance(event,dict): raise ExecutorError("EXECUTOR_OUTPUT_MALFORMED: JSONL record is not an object")
                message=cls._agent_message(event)
                if message is not None: latest=message
        except OSError as error: raise ExecutorError(f"EXECUTOR_OUTPUT_UNREADABLE: {error}") from error
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
        if proc.poll() is None:
            try: proc.send_signal(signal.SIGINT)
            except ProcessLookupError: pass
        try: return proc.wait(timeout=self.SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired: pass
        if proc.poll() is None:
            try: proc.kill()
            except ProcessLookupError: pass
        try: return proc.wait(timeout=self.SHUTDOWN_KILL_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise ExecutorError("CODEX_PROCESS_UNREAPED") from error
    def run_execution(self,prepared):
        spec=prepared.spec; spec.report_dir.mkdir(parents=True,exist_ok=True)
        out=spec.report_dir/"stdout.log"; err=spec.report_dir/"stderr.log"; started=utc_now()
        try:
            with spec.prompt_path.open("rb") as prompt, out.open("wb") as stdout, err.open("wb") as stderr:
                try: proc=subprocess.Popen(list(prepared.command),cwd=spec.repository_root,stdin=prompt,stdout=subprocess.PIPE,stderr=stderr)
                except OSError as error: raise ExecutorError(f"CODEX_LAUNCH_FAILED: {error}") from error
                begun=time.monotonic(); deadline=begun+self.timeout_seconds
                chunks=queue.Queue(maxsize=32)
                def read_stdout():
                    try:
                        while True:
                            chunk=os.read(proc.stdout.fileno(),8192)
                            if not chunk: break
                            chunks.put(("data",chunk))
                    except Exception as error: chunks.put(("error",error))
                    finally: chunks.put(("eof",None))
                reader=threading.Thread(target=read_stdout,daemon=True); reader.start()
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
                        try: kind,value=chunks.get(timeout=wait_for)
                        except queue.Empty:
                            now=time.monotonic()
                            if now>=heartbeat_due:
                                self._progress("heartbeat",now-begun); last_useful=now
                            continue
                        if kind=="error": raise ExecutorError(f"CODEX_STDOUT_READ_FAILED: {value}") from value
                        if kind=="eof":
                            if line and not oversized: self._consume_progress_line(bytes(line),time.monotonic()-begun)
                            stdout_eof=True
                            if proc.poll() is not None: exit_code=proc.returncode; break
                            continue
                        stdout.write(value); stdout.flush()
                        for byte in value:
                            if byte==10:
                                if not oversized and self._consume_progress_line(bytes(line),time.monotonic()-begun): last_useful=time.monotonic()
                                line.clear(); oversized=False
                            elif not oversized:
                                if len(line)<DEFAULT_MAX_JSONL_LINE_BYTES: line.append(byte)
                                else: oversized=True
                except Exception as error:
                    if not shutdown_attempted:
                        try: self._terminate_and_reap(proc)
                        except Exception as shutdown_error: error.add_note(f"bounded executor shutdown also failed: {shutdown_error}")
                    if isinstance(error,ExecutorError): raise
                    raise ExecutorError(f"CODEX_STREAM_FAILED: {error}") from error
                finally:
                    if proc.stdout is not None:
                        try: proc.stdout.close()
                        except OSError: pass
                    reader.join(timeout=1)
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
        return ExecutionResult(str(spec.execution_id),prepared.executor,list(prepared.command),prepared.version,started,finished,exit_code,str(out.relative_to(root)),str(err.relative_to(root)),session_id,outcome,str((spec.report_dir/"result.json").relative_to(root)),prepared.permission_envelope,status,failures,timed_out,prepared.policy_snapshot)
