"""Versioned executor boundary for W2.1.

The workflow owns lifecycle moves. Executors only validate a launch request,
run a process, and return bounded metadata whose large streams live on disk.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib, json, os, signal, subprocess, time, uuid
from pathlib import Path
from typing import Protocol

EXECUTOR_API = "atlas-agent-executor/1"
PERMISSION_ENVELOPE_KEYS = frozenset({"sandbox_mode", "approval_policy", "approvals_reviewer", "strict_config", "ignore_rules", "network_access"})
PERMISSION_SANDBOXES = frozenset({"read-only", "workspace-write", "danger-full-access"})

def validate_permission_envelope(value):
    if type(value) is not dict or set(value) != PERMISSION_ENVELOPE_KEYS:
        raise ExecutorError("INVALID_PERMISSION_ENVELOPE_SCHEMA")
    if value["sandbox_mode"] not in PERMISSION_SANDBOXES:
        raise ExecutorError("INVALID_PERMISSION_ENVELOPE_SANDBOX")
    if value["approval_policy"] != "never" or value["approvals_reviewer"] != "user":
        raise ExecutorError("NONINTERACTIVE_PERMISSION_POLICY_REQUIRED")
    if value["strict_config"] is not True or value["ignore_rules"] is not True:
        raise ExecutorError("NONINTERACTIVE_PERMISSION_POLICY_REQUIRED")
    if type(value["network_access"]) is not bool:
        raise ExecutorError("INVALID_PERMISSION_ENVELOPE_NETWORK")
    return value

class ExecutorError(RuntimeError): pass

def utc_now(): return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

@dataclass(frozen=True)
class ExecutionSpec:
    generation: int
    prompt_sha256: str
    action: str
    prompt_path: Path
    repository_root: Path
    execution_id: str
    report_dir: Path
    runtime_root: Path | None = None
    checkpoint: str | None = None
    policy_snapshot: dict | None = None
    prompt_bytes: bytes | None = None
    input_mode: str | None = None
    expected_input_sha256: str | None = None
    capability_plan: object | None = None

@dataclass(frozen=True)
class PreparedExecution:
    spec: ExecutionSpec
    executor: str
    command: tuple[str, ...]
    version: str
    permission_envelope: dict
    policy_snapshot: dict | None = None
    # Executor-owned preparation state.  This is intentionally opaque to the
    # workflow; concrete executors may use it to bind a run to its resources.
    runtime_handle: object | None = None

@dataclass(frozen=True)
class ExecutionResult:
    execution_id: str
    executor: str
    command: list[str]
    version: str
    started_at: str
    finished_at: str
    exit_code: int
    stdout_path: str
    stderr_path: str
    session_id: str | None
    outcome: str
    report_path: str
    permission_envelope: dict | None = None
    permission_observation_status: str = "unavailable"
    permission_failures: list | None = None
    timed_out: bool = False
    policy_snapshot: dict | None = None
    observed_model: str | None = None
    observed_reasoning: str | None = None
    execution_input_sha256: str | None = None

class Executor(Protocol):
    def prepare_execution(self, spec: ExecutionSpec) -> PreparedExecution: ...
    def post_start_prepare(self, prepared: PreparedExecution) -> PreparedExecution: ...
    def run_execution(self, prepared: PreparedExecution) -> ExecutionResult: ...

def new_execution_id(): return str(uuid.uuid4())

def _write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, sort_keys=True, indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())

class FakeExecutor:
    """Deterministic test executor; it never launches a subprocess."""
    def __init__(self, exit_code=0, stdout=b"", stderr=b"", delay=0.0, crash=False,
                 permission_envelope=None, permission_observation_status="unavailable",
                 permission_failures=None, timed_out=False, observed_thread_id=None,
                 observed_model=None, observed_reasoning=None):
        self.exit_code=exit_code; self.stdout=stdout; self.stderr=stderr; self.delay=delay; self.crash=crash; self.launched=0
        self.permission_envelope=permission_envelope or {"sandbox_mode":"read-only","approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":False}
        self.permission_observation_status=permission_observation_status; self.permission_failures=permission_failures; self.timed_out=timed_out
        self.observed_thread_id=observed_thread_id; self.observed_model=observed_model; self.observed_reasoning=observed_reasoning
    def prepare_execution(self, spec):
        if not spec.prompt_path.exists(): raise ExecutorError("PROMPT_MISSING")
        if spec.prompt_path.read_bytes().__class__ is not bytes: raise ExecutorError("PROMPT_READ_FAILED")
        envelope=self.permission_envelope
        if spec.policy_snapshot and spec.policy_snapshot.get("executor")=="codex":
            envelope={"sandbox_mode":spec.policy_snapshot["sandbox_mode"],"approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":spec.policy_snapshot["network_access"]}
        validate_permission_envelope(envelope)
        return PreparedExecution(spec, "fake", ("fake-executor",), "fake/1", envelope, spec.policy_snapshot)
    def post_start_prepare(self, prepared):
        return prepared
    def run_execution(self, prepared):
        self.launched += 1
        if self.delay: time.sleep(self.delay)
        if self.crash: raise RuntimeError("fake executor crash")
        spec=prepared.spec; spec.report_dir.mkdir(parents=True, exist_ok=True)
        out=spec.report_dir/"stdout.log"; err=spec.report_dir/"stderr.log"
        out.write_bytes(self.stdout); err.write_bytes(self.stderr)
        supplied=spec.prompt_bytes if spec.prompt_bytes is not None else spec.prompt_path.read_bytes()
        finished=utc_now(); root=spec.runtime_root or spec.repository_root; result=ExecutionResult(str(spec.execution_id),prepared.executor,list(prepared.command),prepared.version,utc_now(),finished,self.exit_code,str(out.relative_to(root)),str(err.relative_to(root)),self.observed_thread_id,"timeout" if self.timed_out else ("success" if self.exit_code==0 else "failed"),str((spec.report_dir/"result.json").relative_to(root)),prepared.permission_envelope,self.permission_observation_status,self.permission_failures,self.timed_out,prepared.policy_snapshot,self.observed_model,self.observed_reasoning,hashlib.sha256(supplied).hexdigest())
        _write_json(spec.report_dir/"result.json",{**result.__dict__,"generation":spec.generation,"prompt_sha256":spec.prompt_sha256,"action":spec.action}); return result
