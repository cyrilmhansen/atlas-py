import hashlib
from pathlib import Path

from tools.atlas_agent.codex_executor import CodexExecutor


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_codex(tmp_path, executable, **executor_kwargs):
    """Return a CodexExecutor and executable current snapshot for tests."""
    executable = Path(executable).resolve()

    home = tmp_path / "codex-home-test"
    home.mkdir(mode=0o700, exist_ok=True)

    config = home / "config.toml"
    config.write_text("suppress_unstable_features_warning = true\n")

    catalog = home / "models-atlas-shell-only.json"
    catalog.write_text('{"models":[]}\n')

    profile = home / "atlas-luna-local.config.toml"
    profile.write_text(
        'model = "gpt-5.6-luna"\n'
        '[features.tool_registry]\n'
        'allowed_tools = ["exec_command","write_stdin","apply_patch"]\n'
    )

    snapshot = {
        "schema": "atlas-agent-policy-snapshot/3",
        "policy_schema": "atlas-agent-policy/2",
        "policy_config_sha256": "a" * 64,
        "action": "implementation",
        "checkpoint": "test",
        "profile": "implementation",
        "executor": "codex",
        "requested_model": "gpt-5.6-luna",
        "requested_reasoning_effort": "medium",
        "session_mode": "fresh",
        "sandbox_mode": "workspace-write",
        "network_access_requested": False,
        "network_access": False,
        "web_search": "disabled",
        "apps_enabled": False,
        "session_storage": "persist",
        "max_hot_reuse_hops": 3,
        "max_reuse_generation_gap": 2,
        "codex_profile": "atlas-luna-local",
        "codex_binary_sha256": _sha(executable),
        "codex_config_sha256": _sha(config),
        "codex_catalog_sha256": _sha(catalog),
        "codex_profile_sha256": _sha(profile),
        "required_toolchains": [],
        "writable_caches": [],
    }

    kwargs = {
        "model": "gpt-5.6-luna",
        "sandbox": "workspace-write",
        "network_access": False,
        "codex_home": home,
        **executor_kwargs,
    }
    return CodexExecutor(executable=str(executable), **kwargs), snapshot


class IOCodexExecutor(CodexExecutor):
    """Unit-test executor for code strictly below the authenticated runtime boundary.

    Snapshot/runtime/command authentication is tested separately. Streaming
    and process-lifecycle tests deliberately inject arbitrary child commands
    and Popen doubles.
    """

    # This test double supplies its own command boundary; it is not testing
    # the native Codex isolation decision.
    native_isolation_guaranteed = True

    def _validated_runtime_command(self, prepared, runtime_fd=None):
        return list(prepared.command), (), None

    def _validate_runtime_identity(self, snapshot):
        return None
