from __future__ import annotations
import json, os, re, shutil, signal, subprocess
from dataclasses import replace
from pathlib import Path
from .executor import ExecutorError, ExecutionResult, ExecutionSpec, PreparedExecution, utc_now, validate_permission_envelope
from .jsonl import DEFAULT_MAX_JSONL_LINE_BYTES, iter_bounded_jsonl

class CodexExecutor:
    def __init__(self, executable="codex", model=None, sandbox="read-only", ephemeral=True,
                 sandbox_mode=None, approval_policy="never", approvals_reviewer="user",
                 ignore_rules=True, strict_config=True, network_access=False, timeout_seconds=300):
        self.executable=shutil.which(executable) or (executable if Path(executable).is_file() else None)
        self.model=model; self.sandbox=sandbox_mode or sandbox; self.sandbox_mode=self.sandbox; self.ephemeral=ephemeral
        self.approval_policy=approval_policy; self.approvals_reviewer=approvals_reviewer
        self.ignore_rules=ignore_rules; self.strict_config=strict_config; self.network_access=network_access
        self.timeout_seconds=timeout_seconds
    def _envelope(self):
        return {"sandbox_mode":self.sandbox,"approval_policy":self.approval_policy,"approvals_reviewer":self.approvals_reviewer,"strict_config":self.strict_config,"ignore_rules":self.ignore_rules,"network_access":self.network_access}
    def _validate_policy(self):
        if self.sandbox not in {"read-only","workspace-write","danger-full-access"}: raise ExecutorError("UNSUPPORTED_SANDBOX")
        validate_permission_envelope(self._envelope())
        if isinstance(self.timeout_seconds,bool) or not isinstance(self.timeout_seconds,(int,float)) or self.timeout_seconds <= 0: raise ExecutorError("INVALID_TIMEOUT")
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
    def run_execution(self,prepared):
        spec=prepared.spec; spec.report_dir.mkdir(parents=True,exist_ok=True)
        out=spec.report_dir/"stdout.log"; err=spec.report_dir/"stderr.log"; started=utc_now()
        try:
            with spec.prompt_path.open("rb") as prompt, out.open("wb") as stdout, err.open("wb") as stderr:
                proc=subprocess.Popen(list(prepared.command),cwd=spec.repository_root,stdin=prompt,stdout=stdout,stderr=stderr)
                try: exit_code=proc.wait(timeout=self.timeout_seconds); timed_out=False
                except subprocess.TimeoutExpired:
                    timed_out=True; proc.send_signal(signal.SIGINT)
                    try: exit_code=proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: proc.kill(); exit_code=proc.wait()
        except OSError as e: raise ExecutorError(f"CODEX_LAUNCH_FAILED: {e}") from e
        session_id=None
        try:
            session_id=self._session_id_from_stdout(out)
        except OSError: pass
        timed_out=locals().get("timed_out",False)
        try: status, failures=self._permission_observations(out,err)
        except OSError: status, failures="partial",None
        finished=utc_now(); outcome="timeout" if timed_out else ("success" if exit_code==0 else "failed"); root=spec.runtime_root or spec.repository_root
        return ExecutionResult(str(spec.execution_id),prepared.executor,list(prepared.command),prepared.version,started,finished,exit_code,str(out.relative_to(root)),str(err.relative_to(root)),session_id,outcome,str((spec.report_dir/"result.json").relative_to(root)),prepared.permission_envelope,status,failures,timed_out,prepared.policy_snapshot)
