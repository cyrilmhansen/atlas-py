"""Closed W2.2.1 policy loading, semantic hashing, and resolution."""
from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path
from .assets import ASSET_VERSION, asset_set_identity, prompt_set_identity

from .model import ACTIONS, SESSIONS

POLICY_SCHEMA = "atlas-agent-policy/3"
LEGACY_POLICY_SCHEMA = "atlas-agent-policy/1"
HISTORICAL_POLICY_SCHEMA = "atlas-agent-policy/2"
LEGACY_SNAPSHOT_SCHEMA = "atlas-agent-policy-snapshot/1"
HISTORICAL_SNAPSHOT_SCHEMA = "atlas-agent-policy-snapshot/3"
HISTORICAL_SNAPSHOT_SCHEMA_V2 = "atlas-agent-policy-snapshot/2"
SNAPSHOT_SCHEMA = "atlas-agent-policy-snapshot/4"
_CAPABILITY_KEYS = {"required_toolchains", "writable_caches"}
_PROFILE_KEYS = {
    "codex": {"executor", "model", "reasoning_effort", "sandbox", "network_default", "network_override", "allowed_session_modes", "fresh_storage", "codex_profile_local", "codex_profile_web", "codex_binary_sha256", "codex_config_sha256", "codex_catalog_sha256", "codex_profile_local_sha256", "codex_profile_web_sha256"} | _CAPABILITY_KEYS,
    "manual": {"executor", "allowed_session_modes"},
}
_BASE_KEYS = {"schema", "policy_schema", "policy_config_sha256", "action", "checkpoint", "profile", "executor", "session_mode", "network_access_requested", "network_access", "web_search", "apps_enabled", "session_storage", "max_hot_reuse_hops", "max_reuse_generation_gap"}
SAFE_REUSE_FALLBACK_REASONS = frozenset({
    "incompatible_policy",
    "max_reuse_generation_gap",
    "max_hot_reuse_hops",
    "advanced_reuse_lineage",
    "incompatible_capabilities",
})


def _toml_string(value):
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\b", "\\b").replace("\t", "\\t").replace("\n", "\\n")
    escaped = escaped.replace("\f", "\\f").replace("\r", "\\r")
    return '"' + escaped + '"'


def _toml_value(value):
    if isinstance(value, str):
        return _toml_string(value)
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")


def toml_dumps(data):
    """Canonical UTF-8 TOML for semantic policy hashing."""
    lines = []
    def emit(table, path=()):
        scalars = [(key, value) for key, value in table.items() if not isinstance(value, dict)]
        for key, value in sorted(scalars):
            lines.append(f"{key} = {_toml_value(value)}")
        for key in sorted(key for key, value in table.items() if isinstance(value, dict)):
            lines.append("")
            section = ".".join((*path, key))
            lines.append(f"[{section}]")
            emit(table[key], (*path, key))
    emit(data)
    return "\n".join(lines) + "\n"


class PolicyError(ValueError):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _strict_int(value):
    return type(value) is int and value > 0 and value <= 100


def _profile(value, name, modern=True):
    if type(value) is not dict:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"profile {name}")
    executor = value.get("executor")
    if executor not in _PROFILE_KEYS:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"executor {name}")
    allowed = _PROFILE_KEYS[executor]
    if set(value) != allowed and not (
        executor == "codex" and not modern
        and set(value) == allowed - _CAPABILITY_KEYS
    ):
        raise PolicyError("POLICY_SCHEMA_INVALID", f"profile keys {name}")
    if executor == "codex":
        for key in _CAPABILITY_KEYS:
            names = value.get(key, [])
            if type(names) is not list or any(type(n) is not str or not n or "/" in n or "\\" in n
                                             or n in {".", ".."} for n in names):
                raise PolicyError("POLICY_SCHEMA_INVALID", f"{key} {name}")
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
    if any(type(value[k]) is not str or not value[k] for k in ("sandbox", "network_override", "fresh_storage", "codex_profile_local", "codex_profile_web")):
        raise PolicyError("POLICY_SCHEMA_INVALID", f"profile types {name}")
    expected_profiles = {
        "implementation": ("atlas-luna-local", "atlas-luna-web"),
        "patch_review": ("atlas-sol-local", "atlas-sol-web"),
        "state_audit": ("atlas-sol-local", "atlas-sol-web"),
    }
    if name in expected_profiles and (
        value["codex_profile_local"], value["codex_profile_web"]
    ) != expected_profiles[name]:
        raise PolicyError("POLICY_SCHEMA_INVALID", f"codex profiles {name}")
    for key in (
        "codex_binary_sha256", "codex_config_sha256", "codex_catalog_sha256",
        "codex_profile_local_sha256", "codex_profile_web_sha256",
    ):
        if type(value[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise PolicyError("POLICY_SCHEMA_INVALID", f"{key} {name}")
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
    valid_schemas = {LEGACY_POLICY_SCHEMA, HISTORICAL_POLICY_SCHEMA, POLICY_SCHEMA}
    if type(data) is not dict or data.get("schema") not in valid_schemas:
        raise PolicyError("POLICY_SCHEMA_INVALID")
    expected_keys = {"schema", "session_limits", "profiles"}
    if data["schema"] == POLICY_SCHEMA:
        expected_keys.add("compute_profiles")
    if set(data) != expected_keys:
        raise PolicyError("POLICY_SCHEMA_INVALID")
    limits = data["session_limits"]
    if type(limits) is not dict or set(limits) != {"max_hot_reuse_hops", "max_reuse_generation_gap"} or not all(_strict_int(limits[k]) for k in limits):
        raise PolicyError("POLICY_SCHEMA_INVALID", "session limits")
    profiles = data["profiles"]
    if type(profiles) is not dict or set(profiles) != ACTIONS:
        raise PolicyError("POLICY_SCHEMA_INVALID", "profiles")
    for name in ACTIONS:
        _profile(profiles[name], name, data["schema"] != LEGACY_POLICY_SCHEMA)
    if data["schema"] == POLICY_SCHEMA:
        cp = data["compute_profiles"]
        expected_compute = {
            "luna-high": ("gpt-5.6-luna", "high", ["implementation"]),
            "sol-medium": ("gpt-5.6-sol", "medium",
                           ["implementation", "patch_review", "state_audit"]),
            "astra-medium": ("gpt-6-astra", "medium",
                             ["implementation", "patch_review", "state_audit"]),
            "astra-high": ("gpt-6-astra", "high",
                           ["implementation", "patch_review", "state_audit"]),
        }
        if type(cp) is not dict or set(cp) != set(expected_compute):
            raise PolicyError("POLICY_SCHEMA_INVALID", "compute profiles")
        for name, value in cp.items():
            if (type(value) is not dict or set(value) !=
                    {"model", "reasoning_effort", "actions"}):
                raise PolicyError("POLICY_SCHEMA_INVALID", f"compute profile {name}")
            model, effort, actions = expected_compute[name]
            if (value["model"], value["reasoning_effort"], value["actions"]) != (
                    model, effort, actions):
                raise PolicyError("POLICY_SCHEMA_INVALID", f"compute profile {name}")
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
    if "_atlas_legacy_empty_manual_capabilities" in data:
        data = {key: value for key, value in data.items()
                if not key.startswith("_atlas_")}
    validate_policy(data)
    semantic = toml_dumps(data).encode("utf-8")
    return hashlib.sha256(semantic).hexdigest()


def _snapshot_base(policy, prompt, action, profile, network_access, *, historical=False):
    limits = policy["session_limits"]
    cfg = policy["profiles"][profile]
    snapshot = {
        # These are deliberately not "the snapshot schema for this
        # installation".  They are the wire-format epochs: policy 1 was
        # resolved to snapshot 2, policy 2 to snapshot 3, and only policy 3
        # produces the current snapshot 4.
        "schema": (SNAPSHOT_SCHEMA if policy["schema"] == POLICY_SCHEMA
                   else HISTORICAL_SNAPSHOT_SCHEMA if policy["schema"] == HISTORICAL_POLICY_SCHEMA
                   else HISTORICAL_SNAPSHOT_SCHEMA_V2),
        "policy_schema": policy["schema"],
        "policy_config_sha256": policy_config_sha256(policy),
        "action": action,
        "checkpoint": prompt.checkpoint,
        "profile": profile,
        "executor": cfg["executor"],
        "session_mode": prompt.session_mode,
        # session_mode is the effective authority used by the executor.
        # Keep the prompt's request alongside it so a policy rollover is
        # reconstructible without consulting presentation output.
        "session_mode_requested": prompt.session_mode,
        "session_mode_resolved": prompt.session_mode,
        "reuse_fallback_reason": None,
        "network_access_requested": prompt.network_access if prompt.prompt_schema in {"atlas-agent-prompt/2", "atlas-agent-prompt/3"} else False,
        "network_access": network_access,
        "web_search": "live" if network_access else "disabled",
        "apps_enabled": False,
        "session_storage": cfg.get("fresh_storage", "ephemeral"),
        "max_hot_reuse_hops": limits["max_hot_reuse_hops"],
        "max_reuse_generation_gap": limits["max_reuse_generation_gap"],
    }
    if cfg["executor"] == "codex" and "required_toolchains" in cfg:
        snapshot.update({
            "required_toolchains": list(cfg["required_toolchains"]),
            "writable_caches": list(cfg["writable_caches"]),
        })
    if cfg["executor"] == "codex":
        requested_compute = (
            prompt.compute_profile
            if prompt.prompt_schema == "atlas-agent-prompt/3"
            and prompt.compute_profile != "action-default"
            else None
        )
        compute = policy.get("compute_profiles", {}).get(requested_compute) if requested_compute else None
        model = compute["model"] if compute else cfg["model"]
        reasoning = compute["reasoning_effort"] if compute else cfg["reasoning_effort"]
        snapshot.update({
            "requested_model": model,
            "requested_reasoning_effort": reasoning,
            "sandbox_mode": cfg["sandbox"],
            "codex_profile": cfg["codex_profile_web"] if network_access else cfg["codex_profile_local"],
            "codex_binary_sha256": cfg["codex_binary_sha256"],
            "codex_config_sha256": cfg["codex_config_sha256"],
            "codex_catalog_sha256": cfg["codex_catalog_sha256"],
            "codex_profile_sha256": cfg["codex_profile_web_sha256"] if network_access else cfg["codex_profile_local_sha256"],
        })
        if policy["schema"] == POLICY_SCHEMA:
            snapshot.update({
                "requested_compute_profile": requested_compute or "action-default",
                "resolved_compute_profile": requested_compute or "action-default",
            })
        # Current asset discovery is admission authority only. Historical
        # reconstruction must not derive identities from this installation.
        if not historical:
            assets = Path(__file__).parents[2] / "codex-assets" / ASSET_VERSION
            try:
                snapshot.update({"asset_set_sha256": asset_set_identity(assets),
                                 "prompt_set_sha256": prompt_set_identity(assets),
                                 "asset_version": ASSET_VERSION})
            except (OSError, ValueError):
                # Release assets are optional for replay-only installs.
                pass
    if action == "state_audit":
        snapshot["cold_policy"] = "conversational"
        snapshot["freshness_verification"] = "deferred"
    return snapshot


def resolve_policy(policy, prompt, *, for_new_execution=False, historical=False):
    if for_new_execution and policy.get("schema") != POLICY_SCHEMA:
        raise PolicyError("POLICY_REPLAY_ONLY", "historical policy cannot create execution")
    action = prompt.action
    cfg = policy["profiles"].get(action)
    if cfg is None:
        raise PolicyError("POLICY_PROFILE_UNKNOWN", action)
    if prompt.session_mode not in cfg["allowed_session_modes"]:
        raise PolicyError("SESSION_MODE_FORBIDDEN", action)
    requested = prompt.network_access if prompt.prompt_schema in {"atlas-agent-prompt/2", "atlas-agent-prompt/3"} else False
    if type(requested) is not bool:
        raise PolicyError("POLICY_RESOLUTION_MISMATCH", "network access")
    if cfg["executor"] == "manual":
        if prompt.compute_profile is not None:
            raise PolicyError("COMPUTE_PROFILE_FORBIDDEN", action)
        if requested:
            raise PolicyError("NETWORK_ACCESS_FORBIDDEN", action)
        return _snapshot_base(policy, prompt, action, action, False, historical=historical)
    if requested and cfg["network_override"] == "forbidden":
        raise PolicyError("NETWORK_ACCESS_FORBIDDEN", action)
    if prompt.compute_profile is not None and prompt.compute_profile != "action-default":
        if policy.get("schema") != POLICY_SCHEMA:
            raise PolicyError("COMPUTE_PROFILE_UNAVAILABLE")
        selected = policy["compute_profiles"].get(prompt.compute_profile)
        if selected is None or action not in selected["actions"]:
            raise PolicyError("COMPUTE_PROFILE_INCOMPATIBLE", prompt.compute_profile)
    return _snapshot_base(
        policy, prompt, action, action,
        requested if cfg["network_override"] == "explicit" else cfg["network_default"],
        historical=historical,
    )


def validate_snapshot(snapshot, *, for_new_execution=False):
    if type(snapshot) is not dict or snapshot.get("schema") not in {
        LEGACY_SNAPSHOT_SCHEMA, HISTORICAL_SNAPSHOT_SCHEMA_V2,
        HISTORICAL_SNAPSHOT_SCHEMA, SNAPSHOT_SCHEMA
    }:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot schema")
    snapshot_schema = snapshot["schema"]
    if for_new_execution and snapshot_schema != SNAPSHOT_SCHEMA:
        raise PolicyError("POLICY_REPLAY_ONLY", "historical snapshot")
    is_codex = snapshot.get("executor") == "codex"
    required = (_BASE_KEYS | {"requested_model", "requested_reasoning_effort",
                              "sandbox_mode"} if is_codex else _BASE_KEYS)
    if snapshot_schema == SNAPSHOT_SCHEMA and is_codex:
        required |= {
            "required_toolchains", "writable_caches",
            "requested_compute_profile", "resolved_compute_profile",
        }
    runtime_keys = {
        "codex_binary_sha256", "codex_config_sha256",
        "codex_catalog_sha256", "codex_profile_sha256",
    }
    common_optional = {
        "reused_from_execution_id", "requested_thread_id", "reuse_depth",
        "session_mode_requested",
        "session_mode_resolved",
        "reuse_fallback_reason",
        "cold_policy", "freshness_verification", "codex_profile",
        "asset_set_sha256", "prompt_set_sha256", "asset_version",
    }
    # Keep the closed sets versioned.  In particular, do not let a field
    # introduced by /4 become an optional field of an historical snapshot.
    optional = common_optional | runtime_keys
    if snapshot_schema in {HISTORICAL_SNAPSHOT_SCHEMA, SNAPSHOT_SCHEMA}:
        optional |= {"required_toolchains", "writable_caches"}
    if snapshot_schema == SNAPSHOT_SCHEMA:
        optional |= {
            "capability_plan_sha256", "capability_archive_path",
            "capability_archive_sha256",
        }
    elif snapshot_schema == HISTORICAL_SNAPSHOT_SCHEMA:
        # /3 is the historical capability-aware format.  Its capability
        # archive fields belong to this epoch as well; they must not be
        # treated as /4-only provenance.
        optional |= {
            "capability_plan_sha256", "capability_archive_path",
            "capability_archive_sha256",
        }
    elif snapshot_schema == LEGACY_SNAPSHOT_SCHEMA:
        optional -= runtime_keys
    if not required <= set(snapshot) or set(snapshot) - (required | optional):
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot fields")
    if snapshot.get("profile") != snapshot.get("action") or snapshot.get("apps_enabled") is not False:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot invariants")

    if snapshot_schema == SNAPSHOT_SCHEMA:
        if snapshot.get("policy_schema") != POLICY_SCHEMA:
            raise PolicyError("POLICY_SCHEMA_INVALID", "current snapshot policy")
        if is_codex:
            if snapshot.get("requested_compute_profile") not in {"action-default", "luna-high", "sol-medium", "astra-medium", "astra-high"} or snapshot.get("resolved_compute_profile") != snapshot.get("requested_compute_profile"):
                raise PolicyError("POLICY_SCHEMA_INVALID", "compute provenance")
            if "codex_profile" not in snapshot or not runtime_keys <= set(snapshot):
                raise PolicyError("POLICY_SCHEMA_INVALID", "codex runtime identity")
            for key in runtime_keys:
                if type(snapshot.get(key)) is not str or not re.fullmatch(r"[0-9a-f]{64}", snapshot[key]):
                    raise PolicyError("POLICY_SCHEMA_INVALID", f"snapshot {key}")

            defaults = {"implementation": ("gpt-5.6-luna", "atlas-luna"),
                        "patch_review": ("gpt-5.6-sol", "atlas-sol"),
                        "state_audit": ("gpt-5.6-sol", "atlas-sol")}
            base = defaults.get(snapshot.get("action"))
            cp_models = {"luna-high": ("gpt-5.6-luna", "high", {"implementation"}),
                         "sol-medium": ("gpt-5.6-sol", "medium",
                                        {"implementation", "patch_review", "state_audit"}),
                         "astra-medium": ("gpt-6-astra", "medium",
                                          {"implementation", "patch_review", "state_audit"}),
                         "astra-high": ("gpt-6-astra", "high",
                                        {"implementation", "patch_review", "state_audit"})}
            selected = cp_models.get(snapshot["requested_compute_profile"])
            if selected is not None and snapshot["action"] not in selected[2]:
                raise PolicyError("POLICY_SCHEMA_INVALID", "compute profile/action mismatch")
            expected_model, expected_effort = (base[0], {"implementation": "medium", "patch_review": "high", "state_audit": "high"}[snapshot["action"]]) if snapshot["requested_compute_profile"] == "action-default" else (selected[0], selected[1]) if selected else (None, None)
            expected_profile = base[1] + ("-web" if snapshot.get("network_access") else "-local") if base else None
            if base is None or (expected_model, expected_effort, expected_profile, "live" if snapshot.get("network_access") else "disabled") != (snapshot.get("requested_model"), snapshot.get("requested_reasoning_effort"), snapshot.get("codex_profile"), snapshot.get("web_search")):
                raise PolicyError(
                    "POLICY_SCHEMA_INVALID",
                    "snapshot model/profile/network mismatch",
                )
        elif "codex_profile" in snapshot or runtime_keys & set(snapshot):
            raise PolicyError("POLICY_SCHEMA_INVALID", "unexpected codex runtime identity")
    elif snapshot_schema in {HISTORICAL_SNAPSHOT_SCHEMA_V2, HISTORICAL_SNAPSHOT_SCHEMA}:
        # Snapshots /2 and /3 retain their frozen pre-A6.1 runtime
        # identity semantics.  In particular, /3 is not reinterpreted
        # using the current /4 compute-profile rules.
        #
        # Snapshot /2 is the frozen pre-capability modern format.  Its
        # runtime identity remains meaningful for replay, but it has no
        # capability semantics.
        if snapshot_schema == HISTORICAL_SNAPSHOT_SCHEMA_V2:
            expected_policy = LEGACY_POLICY_SCHEMA
        else:
            expected_policy = HISTORICAL_POLICY_SCHEMA
        if snapshot.get("policy_schema") != expected_policy:
            raise PolicyError("POLICY_SCHEMA_INVALID",
                              "historical snapshot policy")
        if is_codex:
            if "codex_profile" not in snapshot or not runtime_keys <= set(snapshot):
                raise PolicyError("POLICY_SCHEMA_INVALID", "historical codex identity")
            for key in runtime_keys:
                if type(snapshot.get(key)) is not str or not re.fullmatch(r"[0-9a-f]{64}", snapshot[key]):
                    raise PolicyError("POLICY_SCHEMA_INVALID", f"snapshot {key}")
            if snapshot_schema == HISTORICAL_SNAPSHOT_SCHEMA:
                mapping = {
                    ("implementation", False): ("gpt-5.6-luna", "atlas-luna-local", "disabled"),
                    ("implementation", True): ("gpt-5.6-luna", "atlas-luna-web", "live"),
                    ("patch_review", False): ("gpt-5.6-sol", "atlas-sol-local", "disabled"),
                    ("state_audit", False): ("gpt-5.6-sol", "atlas-sol-local", "disabled"),
                }
                expected = mapping.get((snapshot.get("action"), snapshot.get("network_access")))
                observed = (snapshot.get("requested_model"), snapshot.get("codex_profile"),
                            snapshot.get("web_search"))
                if expected is None or observed != expected:
                    raise PolicyError("POLICY_SCHEMA_INVALID",
                                      "snapshot model/profile/network mismatch")
        elif "codex_profile" in snapshot or runtime_keys & set(snapshot):
            raise PolicyError("POLICY_SCHEMA_INVALID", "unexpected codex runtime identity")
    else:
        if snapshot.get("policy_schema") not in {LEGACY_POLICY_SCHEMA, HISTORICAL_POLICY_SCHEMA}:
            raise PolicyError("POLICY_SCHEMA_INVALID", "historical snapshot policy")
        # /1 is positively identified historical provenance, replay-only.
        if "codex_profile" in snapshot or runtime_keys & set(snapshot):
            raise PolicyError("POLICY_SCHEMA_INVALID", "legacy snapshot runtime identity")
        if snapshot.get("web_search") != "disabled":
            raise PolicyError("POLICY_SCHEMA_INVALID", "legacy snapshot invariants")
    if type(snapshot.get("policy_config_sha256")) is not str or not re.fullmatch(r"[0-9a-f]{64}", snapshot["policy_config_sha256"]):
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot hash")
    if snapshot.get("action") not in ACTIONS or snapshot.get("session_mode") not in SESSIONS or snapshot.get("executor") not in {"codex", "manual"}:
        raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot identity")
    if snapshot_schema == SNAPSHOT_SCHEMA:
        expected_executor = "manual" if snapshot["action"] == "checkpoint" else "codex"
        if snapshot["executor"] != expected_executor:
            raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot authority")
        # The compute profile is only allowed to select model and reasoning
        # effort.  All of the remaining execution controls belong to the
        # action profile and are therefore checked independently here.
        action_authority = {
            "implementation": {
                "sandbox_mode": "workspace-write",
                "network_access": None,  # explicit: disabled or enabled
                "session_modes": {"fresh", "reuse"},
                "session_storage": "persist",
                "codex_profile": ("atlas-luna-local", "atlas-luna-web"),
            },
            "patch_review": {
                "sandbox_mode": "read-only",
                "network_access": False,
                "session_modes": {"fresh", "reuse"},
                "session_storage": "persist",
                "codex_profile": ("atlas-sol-local",),
            },
            "state_audit": {
                "sandbox_mode": "read-only",
                "network_access": False,
                "session_modes": {"fresh"},
                "session_storage": "ephemeral",
                "codex_profile": ("atlas-sol-local",),
            },
            "checkpoint": {
                "network_access": False,
                "session_modes": {"fresh"},
                "session_storage": "ephemeral",
            },
        }
        authority = action_authority.get(snapshot["action"])
        if authority is None:
            raise PolicyError("POLICY_SCHEMA_INVALID", "snapshot authority")
        if snapshot["session_mode"] not in authority["session_modes"]:
            raise PolicyError("POLICY_SCHEMA_INVALID", "action session mode")
        if snapshot.get("session_storage") != authority["session_storage"]:
            raise PolicyError("POLICY_SCHEMA_INVALID", "action session storage")
        if (authority["network_access"] is not None and
                snapshot.get("network_access") !=
                authority["network_access"]):
            raise PolicyError("POLICY_SCHEMA_INVALID", "action network access")
        if snapshot.get("network_access_requested") != snapshot.get(
                "network_access"):
            raise PolicyError("POLICY_SCHEMA_INVALID",
                              "action network request")
        expected_web = "live" if snapshot["network_access"] else "disabled"
        if snapshot.get("web_search") != expected_web:
            raise PolicyError("POLICY_SCHEMA_INVALID", "action web search")
        if snapshot["executor"] == "codex":
            if snapshot.get("sandbox_mode") != authority["sandbox_mode"]:
                raise PolicyError("POLICY_SCHEMA_INVALID", "action sandbox")
            if snapshot.get("codex_profile") not in authority["codex_profile"]:
                raise PolicyError("POLICY_SCHEMA_INVALID",
                                  "action codex profile")
    if "session_mode_requested" in snapshot and snapshot["session_mode_requested"] not in SESSIONS:
        raise PolicyError("POLICY_SCHEMA_INVALID", "requested session mode")
    requested = snapshot.get("session_mode_requested", snapshot["session_mode"])
    resolved = snapshot.get("session_mode_resolved", snapshot["session_mode"])
    if requested not in SESSIONS or resolved not in SESSIONS or resolved != snapshot["session_mode"]:
        raise PolicyError("POLICY_SCHEMA_INVALID", "session mode provenance")
    if snapshot_schema == SNAPSHOT_SCHEMA and (
            requested not in authority["session_modes"] or
            resolved not in authority["session_modes"]):
        raise PolicyError("POLICY_SCHEMA_INVALID", "action session mode")
    fallback = snapshot.get("reuse_fallback_reason")
    if fallback is not None and (
        requested != "reuse" or resolved != "fresh"
        or type(fallback) is not str or fallback not in SAFE_REUSE_FALLBACK_REASONS
    ):
        raise PolicyError("POLICY_SCHEMA_INVALID", "reuse fallback")
    if requested == "fresh" and resolved != "fresh":
        raise PolicyError("POLICY_SCHEMA_INVALID", "session mode provenance")
    if requested == "reuse" and resolved == "reuse" and fallback is not None:
        raise PolicyError("POLICY_SCHEMA_INVALID", "reuse fallback")
    if requested == "reuse" and resolved == "fresh" and not fallback:
        raise PolicyError("POLICY_SCHEMA_INVALID", "reuse fallback")
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
    caps = {"required_toolchains", "writable_caches"}
    historical_caps = caps | {
        "capability_plan_sha256", "capability_archive_path",
        "capability_archive_sha256",
    }
    if snapshot_schema == HISTORICAL_SNAPSHOT_SCHEMA_V2:
        if historical_caps & set(snapshot):
            raise PolicyError("POLICY_SCHEMA_INVALID", "historical capability semantics")
    elif snapshot_schema == HISTORICAL_SNAPSHOT_SCHEMA:
        if snapshot.get("executor") == "codex" and any(
                type(snapshot.get(k)) is not list for k in caps):
            raise PolicyError("POLICY_SCHEMA_INVALID", "historical capability requirements")
        if snapshot.get("executor") == "manual" and caps & set(snapshot):
            raise PolicyError("POLICY_SCHEMA_INVALID", "manual capability semantics")
    elif snapshot_schema == SNAPSHOT_SCHEMA:
        if snapshot.get("executor") == "codex":
            if any(type(snapshot.get(k)) is not list for k in caps):
                raise PolicyError("POLICY_SCHEMA_INVALID", "current capability requirements")
            for key in caps:
                if any(type(name) is not str or not name or "/" in name or
                       "\\" in name or name in {".", ".."}
                       for name in snapshot[key]):
                    raise PolicyError("POLICY_SCHEMA_INVALID",
                                      "current capability requirements")
            for key in ("capability_plan_sha256",
                        "capability_archive_sha256"):
                if key in snapshot and (
                        type(snapshot[key]) is not str or
                        not re.fullmatch(r"[0-9a-f]{64}", snapshot[key])):
                    raise PolicyError("POLICY_SCHEMA_INVALID",
                                      f"current {key}")
            if "capability_archive_path" in snapshot and (
                    type(snapshot["capability_archive_path"]) is not str or
                    not re.fullmatch(
                        r"reports/capabilities/[A-Za-z0-9][A-Za-z0-9._-]{0,255}\.json",
                        snapshot["capability_archive_path"])):
                raise PolicyError("POLICY_SCHEMA_INVALID",
                                  "current capability archive path")
        elif historical_caps & set(snapshot):
            raise PolicyError("POLICY_SCHEMA_INVALID", "manual capability semantics")
        if (not is_codex and
                {"asset_set_sha256", "prompt_set_sha256", "asset_version"} &
                set(snapshot)):
            raise PolicyError("POLICY_SCHEMA_INVALID",
                              "manual asset identity")
        if not is_codex and {"requested_compute_profile",
                             "resolved_compute_profile"} & set(snapshot):
            raise PolicyError("POLICY_SCHEMA_INVALID",
                              "manual compute provenance")
    return snapshot
