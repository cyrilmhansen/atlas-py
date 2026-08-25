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
def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _number(value):
    return value if type(value) is int and value >= 0 else None


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
    for key in ("policy_config_sha256", "profile", "session_mode", "reused_from_execution_id", "reuse_depth", "cold_policy", "freshness_verification"):
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
        for key in ("action", "checkpoint", "policy_config_sha256", "profile", "requested_model", "requested_reasoning_effort", "session_mode", "cold_policy", "freshness_verification"):
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
