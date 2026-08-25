"""Closed W2.2.1 policy loading, semantic hashing, and resolution."""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path

from .model import ACTIONS, SESSIONS

POLICY_SCHEMA = "atlas-agent-policy/1"
SNAPSHOT_SCHEMA = "atlas-agent-policy-snapshot/1"
_PROFILE_KEYS = {
    "codex": {"executor", "model", "reasoning_effort", "sandbox", "network_default", "network_override", "allowed_session_modes", "fresh_storage"},
    "manual": {"executor", "allowed_session_modes"},
}
_BASE_KEYS = {"schema", "policy_schema", "policy_config_sha256", "action", "checkpoint", "profile", "executor", "session_mode", "network_access_requested", "network_access", "web_search", "apps_enabled", "session_storage", "max_hot_reuse_hops", "max_reuse_generation_gap"}


class PolicyError(ValueError):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _strict_int(value):
    return type(value) is int and value > 0 and value <= 100


def _profile(value, name):
    if type(value) is not dict:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"profile {name}")
    executor = value.get("executor")
    if executor not in _PROFILE_KEYS:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"executor {name}")
    if set(value) != _PROFILE_KEYS[executor]:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"profile keys {name}")
    modes = value["allowed_session_modes"]
    if type(modes) is not list or not modes or any(type(x) is not str or x not in SESSIONS for x in modes) or len(set(modes)) != len(modes):
        raise PolicyError("POLICY_SCHEMA_INVALID", f"session modes {name}")
    if executor == "manual":
        if modes != ["fresh"]:
            raise PolicyError("POLICY_SCHEMA_INVALID", f"manual profile {name}")
        return value
    if type(value["model"]) is not str or not value["model"]:
        raise PolicyError("MODEL_CONFIG_INVALID", name)
    if type(value["reasoning_effort"]) is not str or value["reasoning_effort"] not in {"low", "medium", "high"}:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"reasoning {name}")
    if any(type(value[k]) is not str or not value[k] for k in ("sandbox", "network_override", "fresh_storage")):
        raise PolicyError("POLICY_SCHEMA_INVALID", f"profile types {name}")
    if value["sandbox"] not in {"read-only", "workspace-write"}:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"sandbox {name}")
    if type(value["network_default"]) is not bool or value["network_override"] not in {"explicit", "forbidden"} or value["fresh_storage"] not in {"persist", "ephemeral"}:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"network/session {name}")
    if name == "implementation" and value["sandbox"] != "workspace-write":
        raise PolicyError("POLICY_SCHEMA_INVALID", "implementation sandbox")
    if name in {"patch_review", "state_audit"} and (value["sandbox"] != "read-only" or value["network_default"] is not False or value["network_override"] != "forbidden"):
        raise PolicyError("POLICY_SCHEMA_INVALID", f"restricted profile {name}")
    if name == "state_audit" and (modes != ["fresh"] or value["fresh_storage"] != "ephemeral"):
        raise PolicyError("POLICY_SCHEMA_INVALID", "state audit session")
    return value


def validate_policy(data):
    if type(data) is not dict or set(data) != {"schema", "session_limits", "profiles"} or data.get("schema") != POLICY_SCHEMA:
        raise PolicyError("POLICY_SCHEMA_INVALID")
    limits = data["session_limits"]
    if type(limits) is not dict or set(limits) != {"max_hot_reuse_hops", "max_reuse_generation_gap"} or not all(_strict_int(limits[k]) for k in limits):
        raise PolicyError("POLICY_SCHEMA_INVALID", "session limits")
    profiles = data["profiles"]
    if type(profiles) is not dict or set(profiles) != ACTIONS:
        raise PolicyError("POLICY_SCHEMA_INVALID", "profiles")
    for name in ACTIONS:
        _profile(profiles[name], name)
    return data


def load_policy(path: Path):
    if not path.is_file():
        raise PolicyError("POLICY_CONFIG_REQUIRED")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise PolicyError("POLICY_SCHEMA_INVALID", str(error)) from error
    return validate_policy(data)


def policy_config_sha256(data):
    validate_policy(data)
    semantic = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(semantic).hexdigest()


def _snapshot_base(policy, prompt, action, profile, network_access):
    limits = policy["session_limits"]
    cfg = policy["profiles"][profile]
    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "policy_schema": policy["schema"],
        "policy_config_sha256": policy_config_sha256(policy),
        "action": action,
        "checkpoint": prompt.checkpoint,
        "profile": profile,
        "executor": cfg["executor"],
        "session_mode": prompt.session_mode,
        "network_access_requested": prompt.network_access if prompt.prompt_schema == "atlas-agent-prompt/2" else False,
        "network_access": network_access,
        "web_search": "disabled",
        "apps_enabled": False,
        "session_storage": cfg.get("fresh_storage", "ephemeral"),
        "max_hot_reuse_hops": limits["max_hot_reuse_hops"],
        "max_reuse_generation_gap": limits["max_reuse_generation_gap"],
    }
    if cfg["executor"] == "codex":
        snapshot.update({"requested_model": cfg["model"], "requested_reasoning_effort": cfg["reasoning_effort"], "sandbox_mode": cfg["sandbox"]})
    if action == "state_audit":
        snapshot["cold_policy"] = "conversational"
        snapshot["freshness_verification"] = "deferred"
    return snapshot


def resolve_policy(policy, prompt):
    action = prompt.action
    cfg = policy["profiles"].get(action)
    if cfg is None:
        raise PolicyError("POLICY_PROFILE_UNKNOWN", action)
    if prompt.session_mode not in cfg["allowed_session_modes"]:
        raise PolicyError("SESSION_MODE_FORBIDDEN", action)
    requested = prompt.network_access if prompt.prompt_schema == "atlas-agent-prompt/2" else False
    if type(requested) is not bool:
        raise PolicyError("POLICY_RESOLUTION_MISMATCH", "network access")
    if cfg["executor"] == "manual":
        if requested:
            raise PolicyError("NETWORK_ACCESS_FORBIDDEN", action)
        return _snapshot_base(policy, prompt, action, action, False)
    if requested and cfg["network_override"] == "forbidden":
        raise PolicyError("NETWORK_ACCESS_FORBIDDEN", action)
    return _snapshot_base(policy, prompt, action, action, requested if cfg["network_override"] == "explicit" else cfg["network_default"])


def validate_snapshot(snapshot):
    if type(snapshot) is not dict or snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot schema")
    required = _BASE_KEYS | {"requested_model", "requested_reasoning_effort", "sandbox_mode"} if snapshot.get("executor") == "codex" else _BASE_KEYS
    if not required <= set(snapshot) or set(snapshot) - (required | {"reused_from_execution_id", "requested_thread_id", "reuse_depth", "cold_policy", "freshness_verification"}):
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot fields")
    if snapshot.get("profile") != snapshot.get("action") or snapshot.get("policy_schema") != POLICY_SCHEMA or snapshot.get("web_search") != "disabled" or snapshot.get("apps_enabled") is not False:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot invariants")
    if type(snapshot.get("policy_config_sha256")) is not str or not re.fullmatch(r"[0-9a-f]{64}", snapshot["policy_config_sha256"]):
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot hash")
    if snapshot.get("action") not in ACTIONS or snapshot.get("session_mode") not in SESSIONS or snapshot.get("executor") not in {"codex", "manual"}:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot identity")
    if type(snapshot.get("network_access")) is not bool or type(snapshot.get("network_access_requested")) is not bool:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot network")
    for key in ("max_hot_reuse_hops", "max_reuse_generation_gap"):
        if not _strict_int(snapshot.get(key)):
            raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot limits")
    reuse_keys = {"reused_from_execution_id", "requested_thread_id", "reuse_depth"}
    present = reuse_keys & set(snapshot)
    if present and present != reuse_keys:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot reuse fields")
    if "reuse_depth" in snapshot and (type(snapshot["reuse_depth"]) is not int or snapshot["reuse_depth"] < 1):
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot reuse depth")
    if snapshot.get("session_mode") == "fresh" and present:
        raise PolicyError("POLICY_SCHEMA_INVALID", "fresh reuse fields")
    if snapshot.get("session_mode") == "reuse" and present != reuse_keys:
        raise PolicyError("POLICY_SCHEMA_INVALID", "reuse target fields")
    if snapshot.get("action") == "state_audit" and (snapshot.get("cold_policy") != "conversational" or snapshot.get("freshness_verification") != "deferred"):
        raise PolicyError("POLICY_SCHEMA_INVALID", "cold assurance")
    if snapshot.get("action") != "state_audit" and ({"cold_policy", "freshness_verification"} & set(snapshot)):
        raise PolicyError("POLICY_SCHEMA_INVALID", "unexpected cold assurance")
    return snapshot
