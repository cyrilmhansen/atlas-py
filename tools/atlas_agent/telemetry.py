"""Passive, non-authoritative Codex execution telemetry."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .jsonl import DEFAULT_MAX_JSONL_LINE_BYTES, iter_bounded_jsonl

USAGE_SCHEMA = "atlas-agent-codex-usage/1"
USAGE_EVENT_SCHEMA = "atlas-agent-codex-usage-event/1"
PRESENTATION_USAGE_MAX_BYTES = 1024 * 1024
TOKEN_METRICS = frozenset({"input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"})
MAX_TELEMETRY_NUMBER = (1 << 63) - 1
def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _number(value):
    return value if type(value) is int and value >= 0 else None


def _presentation_number(value, optional=True):
    return (value is None and optional) or (type(value) is int and 0 <= value <= MAX_TELEMETRY_NUMBER)


def _presentation_metrics(value):
    if type(value) is not dict or set(value) != TOKEN_METRICS:
        return False
    return all(_presentation_number(metric) for metric in value.values()) and any(type(metric) is int for metric in value.values())


def _presentation_run(value):
    if _presentation_metrics(value):
        return True
    if type(value) is not dict or set(value) != {"observations", "consistency"} or value["consistency"] != "disagree":
        return False
    observations=value["observations"]
    if type(observations) is not list or not 2 <= len(observations) <= 32:
        return False
    for observation in observations:
        if type(observation) is not dict or set(observation) != {"source", "thread_id", "metrics"}:
            return False
        if observation["source"] != "exec-jsonl" or (observation["thread_id"] is not None and type(observation["thread_id"]) is not str):
            return False
        if not _presentation_metrics(observation["metrics"]):
            return False
    return True


def _presentation_contract(record):
    """Accept only cross-field states the collector itself can emit."""
    status=record.get("status")
    sources=record.get("sources")
    run=record.get("run")
    malformed=record.get("parser_malformed_lines")
    if status=="unavailable":
        return sources==["unavailable"] and run is None
    if sources!=["exec-jsonl"] or not _presentation_run(run):
        return False
    disagreement=isinstance(run,dict) and set(run)=={"observations","consistency"}
    if status=="complete":
        return not disagreement and malformed==0
    if status=="partial":
        if disagreement:
            metrics=[observation["metrics"] for observation in run["observations"]]
            return any(item!=metrics[0] for item in metrics[1:])
        return malformed > 0
    return False


def load_presentation_usage(path: Path, generation_record, max_bytes=PRESENTATION_USAGE_MAX_BYTES):
    """Return trusted display metrics, or ``None`` for any untrusted input."""
    try:
        with Path(path).open("rb") as stream:
            raw=stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return None
        record=json.loads(raw.decode("utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError,RecursionError,MemoryError,ValueError):
        return None
    if type(record) is not dict:
        return None
    required={"schema","execution_id","generation","prompt_sha256","action","checkpoint","thread_id","codex_version","requested_model","requested_reasoning","observed_model","reasoning_effort","run","context_window","context_used","context_remaining","quota_before","quota_after","quota_status","sources","status","parser_malformed_lines","captured_at"}
    optional={"policy_config_sha256","profile","session_mode","session_mode_requested","session_mode_resolved","reuse_fallback_reason","reused_from_execution_id","reuse_depth","cold_policy","freshness_verification"}
    if not required.issubset(record) or not set(record).issubset(required | optional):
        return None
    execution=generation_record.get("execution")
    if type(execution) is not dict:
        return None
    expected={
        "schema":USAGE_SCHEMA,
        "execution_id":execution.get("execution_id"),
        "generation":generation_record.get("generation"),
        "prompt_sha256":generation_record.get("prompt_sha256"),
        "action":generation_record.get("action"),
        "checkpoint":generation_record.get("checkpoint"),
    }
    if any(record.get(key) != value for key,value in expected.items()):
        return None
    snapshot=execution.get("policy_snapshot")
    if isinstance(snapshot,dict):
        identity={"policy_config_sha256":"policy_config_sha256","profile":"profile","session_mode":"session_mode","session_mode_requested":"session_mode_requested","session_mode_resolved":"session_mode_resolved","reuse_fallback_reason":"reuse_fallback_reason","reused_from_execution_id":"reused_from_execution_id","reuse_depth":"reuse_depth"}
        if any(record.get(field) != snapshot.get(source) for field,source in identity.items() if source in snapshot):
            return None
    if not all(_presentation_number(record.get(key)) for key in ("context_window","context_used","context_remaining")):
        return None
    if not _presentation_number(record.get("parser_malformed_lines"),optional=False):
        return None
    sources=record.get("sources")
    if type(sources) is not list or not sources or len(sources) > 8 or any(source not in {"exec-jsonl","unavailable"} for source in sources) or len(set(sources)) != len(sources):
        return None
    if not _presentation_contract(record):
        return None
    if record.get("quota_before") is not None or record.get("quota_after") is not None or record.get("quota_status") != "unavailable":
        return None
    for key in ("thread_id","codex_version","requested_model","requested_reasoning","observed_model","reasoning_effort"):
        if record.get(key) is not None and type(record[key]) is not str:
            return None
    if type(record.get("captured_at")) is not str or not record["captured_at"]:
        return None
    return record.get("run") if record["status"] != "unavailable" else None


def _usage_from_event(event):
    usage = event.get("usage") if isinstance(event, dict) else None
    if not isinstance(usage, dict):
        return None
    names = {
        "input_tokens": "input_tokens",
        "cached_input_tokens": "cached_input_tokens",
        "output_tokens": "output_tokens",
        "reasoning_output_tokens": "reasoning_output_tokens",
        "total_tokens": "total_tokens",
    }
    result = {target: _number(usage.get(source)) for source, target in names.items()}
    if not any(v is not None for v in result.values()):
        return None
    return result


def _event_metadata(event):
    if not isinstance(event, dict) or event.get("type") not in {"thread.started", "turn.completed"}:
        return {}
    return {
        "observed_model": event.get("model") if isinstance(event.get("model"), str) else None,
        "reasoning_effort": event.get("reasoning_effort"),
        "context_window": _number(event.get("context_window")),
        "context_used": _number(event.get("context_used")),
        "context_remaining": _number(event.get("context_remaining")),
    }


def parse_exec_jsonl(path: Path, max_line_bytes: int = DEFAULT_MAX_JSONL_LINE_BYTES):
    """Parse only documented, non-secret telemetry fields from Codex JSONL."""
    observations = []
    metadata = {}
    malformed = 0
    current_thread = None
    if not path.is_file():
        return observations, metadata, malformed
    for line, oversized in iter_bounded_jsonl(path, max_line_bytes=max_line_bytes):
        if oversized:
            malformed += 1
            continue
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed += 1
            continue
        if not isinstance(event, dict):
            malformed += 1
            continue
        event_type=event.get("type")
        if event_type not in {"thread.started", "turn.completed"}:
            continue
        if event_type=="thread.started":
            candidate=event.get("thread_id") or event.get("session_id")
            current_thread=candidate if isinstance(candidate,str) else None
        metadata.update({k: v for k, v in _event_metadata(event).items() if v is not None})
        usage = _usage_from_event(event) if event_type=="turn.completed" else None
        if usage is not None:
            observations.append({"source": "exec-jsonl", "thread_id": current_thread, "metrics": usage})
            metadata["thread_id"] = current_thread
    return observations, metadata, malformed


def _merge_usage(observations):
    # Codex emits one turn.completed usage envelope. If a future version emits
    # several, preserve disagreement instead of silently adding estimates.
    if not observations:
        return None, "unavailable"
    metrics = [x["metrics"] for x in observations]
    if len(metrics) > 1 and any(item != metrics[0] for item in metrics[1:]):
        return {"observations": observations, "consistency": "disagree"}, "partial"
    return metrics[0], "complete"


def _append_usage_event(runtime_root, record):
    path = Path(runtime_root) / "usage" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    if path.exists():
        with path.open("rb") as stream:
            for line in stream:
                if line.strip():
                    previous = line
    event = {
        "schema": USAGE_EVENT_SCHEMA,
        "timestamp": _now(),
        "execution_id": record["execution_id"],
        "generation": record["generation"],
        "prompt_sha256": record["prompt_sha256"],
        "source": record["sources"],
        "codex_version": record.get("codex_version"),
        "action": record.get("action"),
        "checkpoint": record.get("checkpoint"),
        "requested_model": record.get("requested_model"),
        "requested_reasoning": record.get("requested_reasoning"),
        "observed_model": record.get("observed_model"),
        "thread_id": record.get("thread_id"),
        "metrics": record.get("run"),
        "status": record["status"],
    }
    for key in ("policy_config_sha256", "profile", "session_mode", "session_mode_requested", "session_mode_resolved", "reuse_fallback_reason", "reused_from_execution_id", "reuse_depth", "cold_policy", "freshness_verification"):
        if key in record:
            event[key] = record[key]
    # This journal is append-only but intentionally non-authoritative; a
    # per-record hash makes later ingestion/debugging deterministic.
    if previous:
        event["previous_sha256"] = hashlib.sha256(previous).hexdigest()
    line = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
    with path.open("ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def collect_usage(spec, result, report_dir: Path, requested_model=None, requested_reasoning=None, policy_snapshot=None):
    """Write usage.json and append a passive observation; never raises on parse errors."""
    stdout = report_dir / "stdout.log"
    try:
        observations, metadata, malformed = parse_exec_jsonl(stdout)
    except Exception:
        # Telemetry parser failures must never change a healthy lifecycle.
        observations, metadata, malformed = [], {}, 1
    run, status = _merge_usage(observations)
    if malformed and status == "complete":
        status = "partial"
    thread_id = metadata.get("thread_id") if len(observations)==1 else (getattr(result, "session_id", None) if not observations else None)
    record = {
        "schema": USAGE_SCHEMA,
        "execution_id": spec.execution_id,
        "generation": spec.generation,
        "prompt_sha256": spec.prompt_sha256,
        "action": spec.action,
        "checkpoint": spec.checkpoint,
        "thread_id": thread_id,
        "codex_version": getattr(result, "version", None),
        "requested_model": requested_model if isinstance(requested_model,str) else None,
        "requested_reasoning": requested_reasoning if isinstance(requested_reasoning,str) else None,
        "observed_model": metadata.get("observed_model") or getattr(result, "observed_model", None),
        "reasoning_effort": metadata.get("reasoning_effort") if isinstance(metadata.get("reasoning_effort"),str) else getattr(result, "observed_reasoning", None),
        "run": run,
        "context_window": metadata.get("context_window"),
        "context_used": metadata.get("context_used"),
        "context_remaining": metadata.get("context_remaining"),
        "quota_before": None,
        "quota_after": None,
        "quota_status": "unavailable",
        "sources": sorted({x["source"] for x in observations}),
        "status": status,
        "parser_malformed_lines": malformed,
        "captured_at": _now(),
    }
    if policy_snapshot:
        for key in ("action", "checkpoint", "policy_config_sha256", "profile", "requested_model", "requested_reasoning_effort", "session_mode", "session_mode_requested", "session_mode_resolved", "reuse_fallback_reason", "cold_policy", "freshness_verification"):
            if key in policy_snapshot:
                record[key if key != "requested_reasoning_effort" else "requested_reasoning"] = policy_snapshot[key]
        for key in ("reused_from_execution_id", "reuse_depth"):
            if key in policy_snapshot: record[key] = policy_snapshot[key]
    if not record["sources"]:
        record["sources"] = ["unavailable"]
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "usage.json"
    with path.open("w", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    _append_usage_event(spec.runtime_root or spec.repository_root, record)
    return record
