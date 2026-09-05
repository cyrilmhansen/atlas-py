"""Executable P0.6 contract (test materialization only).

The API exercised here is intentionally the API described by the frozen P0.6
design.  This file is expected to be red until P0.6 is implemented; in
particular, it must not grow compatibility shims in production code merely
to make these tests green.
"""
import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def toolchains_api():
    try:
        return importlib.import_module("tools.atlas_agent.toolchains")
    except ImportError as error:
        pytest.fail("P0.6 toolchain API is not implemented: " + str(error))


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _command(root, name="cargo", text="cargo 1.0\n"):
    path = root / "bin" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``%b`` makes the fixture's escaped newline deterministic without
    # depending on a host-specific version of printf.
    path.write_text("#!/bin/sh\nprintf '%b' " + repr(text) + "\n")
    path.chmod(0o755)
    return path


def _manifest(root, *, name="rust", command="cargo", qualification="rust:1"):
    executable = _command(root, command, f"{command} 1.0\n")
    probe = (f"{command} 1.0\n".encode() + b"\0")
    return {
        "schema": "atlas-agent-machine-capabilities/1",
        "persistent_cache_root": str(root.parent / "persistent-caches"),
        "toolchains": {name: {
            "qualification": qualification,
            "source_root": str(root),
            "commands": {command: {
                "path": str(executable.relative_to(root)),
                "sha256": _digest(executable.read_bytes()),
                "probe_args": ["--version"],
                "probe_output_sha256": _digest(probe),
            }},
        }},
        "caches": {"cargo": {"qualification": "cargo-cache/1",
                             "environment": {"CARGO_HOME": "${CACHE}"}}},
    }


def _resolve(api, manifest, requirements=None):
    resolver = api.CapabilityResolver(manifest)
    return resolver.resolve(requirements or {"toolchains": ["rust"], "caches": ["cargo"]})


def test_project_policy_is_portable_names_only_and_machine_authority_is_explicit(
    toolchains_api, tmp_path, monkeypatch
):
    project = tmp_path / "project.toml"
    project.write_text(
        'required_toolchains = ["rust"]\nwritable_caches = ["cargo"]\n'
    )
    assert toolchains_api.load_project_requirements(project) == {
        "toolchains": ["rust"], "caches": ["cargo"]
    }
    project.write_text('required_toolchains = ["/home/me/.rustup/toolchains/x"]\n')
    with pytest.raises(toolchains_api.CapabilityError, match="PROJECT"):
        toolchains_api.load_project_requirements(project)
    authority = tmp_path / "machine.toml"
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(authority))
    assert toolchains_api.machine_capabilities_path() == authority
    monkeypatch.delenv("ATLAS_AGENT_CAPABILITIES_FILE")
    assert toolchains_api.machine_capabilities_path() is None


def test_machine_manifest_is_not_discovered_from_repository_or_cwd(
    toolchains_api, tmp_path, monkeypatch
):
    (tmp_path / "capabilities.toml").write_text("not authority")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATLAS_AGENT_CAPABILITIES_FILE", raising=False)
    with pytest.raises(toolchains_api.CapabilityError, match="UNAVAILABLE"):
        toolchains_api.load_machine_capabilities()


@pytest.mark.parametrize("name", ["rust", "python", "node", "go", "jdk", "clang"])
def test_one_generic_model_represents_all_supported_toolchain_names(
    toolchains_api, tmp_path, name
):
    root = tmp_path / name
    manifest = _manifest(root, name=name, command="tool")
    plan = _resolve(toolchains_api, manifest,
                    {"toolchains": [name], "caches": []})
    assert plan.toolchains[0].name == name
    assert plan.toolchains[0].guest_root == f"/opt/atlas/toolchains/{name}"


def test_private_root_mount_and_command_paths_are_narrow_read_only_and_isolated(
    toolchains_api, tmp_path
):
    home = tmp_path / "operator-home"
    root = home / ".rustup" / "toolchains" / "exact"
    sentinel = home / ".ssh" / "credentials"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("secret")
    manifest = _manifest(root)
    plan = _resolve(toolchains_api, manifest, {"toolchains": ["rust"], "caches": []})
    mount = plan.mounts[0]
    assert mount.host_root == root.resolve()
    assert mount.guest_root == Path("/opt/atlas/toolchains/rust")
    assert mount.read_only is True
    assert plan.command("cargo").guest_path == Path(
        "/opt/atlas/toolchains/rust/bin/cargo"
    )
    assert plan.command("cargo").execute() == "cargo 1.0\n"
    assert plan.visible_host_paths == (root.resolve(),)
    assert sentinel not in plan.visible_host_paths


def test_system_visible_root_retains_existing_guest_path_without_broad_usr_rebind(
    toolchains_api, tmp_path
):
    root = Path("/usr")
    executable = Path("/usr/bin/true")
    manifest = {
        "schema": "atlas-agent-machine-capabilities/1",
        "persistent_cache_root": str(tmp_path / "persistent-caches"),
        "toolchains": {"clang": {
            "exposure": "system-visible", "qualification": "system:true",
            "source_root": "/usr", "guest_root": "/usr",
            "commands": {"true": {
                "path": "bin/true", "sha256": _digest(executable.read_bytes()),
                "probe_args": [], "probe_output_sha256": _digest(b"\0")}}}},
        "caches": {},
    }
    plan = _resolve(toolchains_api, manifest, {"toolchains": ["clang"], "caches": []})
    assert plan.command("true").guest_path == Path("/usr/bin/true")
    assert not any(m.guest_root == Path("/opt/atlas/toolchains/clang")
                   for m in plan.mounts)
    assert plan.command("true").executable_sha256 == _digest(executable.read_bytes())
    assert plan.command("true").observed_version == ""


@pytest.mark.parametrize("case", [
    "missing-capability", "executable-digest", "identity-file-digest",
    "version-probe", "unsafe-source", "escaping-command", "symlink-command",
    "authority-overlap", "command-conflict", "environment-conflict",
])
def test_qualification_failures_are_fail_closed(toolchains_api, tmp_path, case):
    root = tmp_path / "root"
    manifest = _manifest(root)
    if case == "missing-capability":
        requirements = {"toolchains": ["python"], "caches": []}
    elif case == "executable-digest":
        manifest["toolchains"]["rust"]["commands"]["cargo"]["sha256"] = "0" * 64
        requirements = {"toolchains": ["rust"], "caches": []}
    elif case == "identity-file-digest":
        manifest["toolchains"]["rust"]["identity_files"] = {
            "release": {"path": "missing", "sha256": "0" * 64}}
        requirements = {"toolchains": ["rust"], "caches": []}
    elif case == "version-probe":
        manifest["toolchains"]["rust"]["commands"]["cargo"]["probe_output_sha256"] = "0" * 64
        requirements = {"toolchains": ["rust"], "caches": []}
    elif case == "unsafe-source":
        manifest["toolchains"]["rust"]["source_root"] = str(tmp_path / "..")
        requirements = {"toolchains": ["rust"], "caches": []}
    elif case in {"escaping-command", "symlink-command"}:
        manifest["toolchains"]["rust"]["commands"]["cargo"]["path"] = "../cargo"
        requirements = {"toolchains": ["rust"], "caches": []}
    elif case == "authority-overlap":
        manifest["toolchains"]["rust"]["source_root"] = str(tmp_path)
        requirements = {"toolchains": ["rust"], "caches": []}
    elif case == "command-conflict":
        manifest["toolchains"]["python"] = manifest["toolchains"]["rust"].copy()
        manifest["toolchains"]["python"]["commands"] = manifest["toolchains"]["rust"]["commands"]
        requirements = {"toolchains": ["rust", "python"], "caches": []}
    else:
        manifest["toolchains"]["rust"]["environment"] = {"PATH": "/host"}
        requirements = {"toolchains": ["rust"], "caches": []}
    with pytest.raises(toolchains_api.CapabilityError):
        _resolve(toolchains_api, manifest, requirements)


def test_environment_is_controller_generated_and_restricted(toolchains_api, tmp_path):
    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    environment = plan.environment()
    assert environment["PATH"].startswith("/opt/atlas/toolchains/rust/bin:")
    assert environment["HOME"] == "/home/atlas"
    assert "HOST_PATH" not in environment
    for value in environment:
        assert not value.startswith("ATLAS_")
    with pytest.raises(toolchains_api.CapabilityError):
        toolchains_api.interpolate("${HOST_PATH}")
    assert toolchains_api.interpolate("${ROOT}/bin") == "${ROOT}/bin"
    assert toolchains_api.interpolate("${CACHE:cargo}") == "${CACHE:cargo}"


def test_cache_has_atlas_guest_path_derived_backing_and_mutable_unhashed_status(
    toolchains_api, tmp_path
):
    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    cache = plan.caches[0]
    assert cache.guest_path == Path("/var/cache/atlas-agent/cargo")
    assert cache.backing.is_relative_to(tmp_path / "persistent-caches")
    assert cache.scope.project_key and cache.scope.toolchain_key
    assert cache.lifetime == "persistent"
    assert cache.status == "mutable-unhashed"
    assert cache.backing != Path.home() / ".cargo"


def test_cache_persists_only_for_same_project_and_effective_toolchain(
    toolchains_api, tmp_path
):
    store = toolchains_api.CacheStore(tmp_path / "persistent")
    first = store.prepare("project-a", "rust:1", "cargo-cache/1")
    first.write_text("populated")
    assert store.prepare("project-a", "rust:1", "cargo-cache/1").read_text() == "populated"
    assert not store.visible_to("project-b", "rust:1", "cargo-cache/1")
    assert not store.visible_to("project-a", "rust:2", "cargo-cache/1")
    assert not store.visible_to("project-a", "rust:1", None)
    assert store.scratch("project-a") != first
    assert store.import_user_cache(Path.home() / ".cargo") is False


def test_same_cache_concurrent_ownership_is_rejected_before_run_started(
    toolchains_api, tmp_path
):
    store = toolchains_api.CacheStore(tmp_path / "persistent")
    owner = store.lock("project-a", "rust:1", "cargo-cache/1")
    try:
        with pytest.raises(toolchains_api.CapabilityError, match="CONCURRENT"):
            store.lock("project-a", "rust:1", "cargo-cache/1")
    finally:
        owner.release()


@pytest.mark.parametrize("failure", [
    "missing-capability", "qualification-mismatch", "cache-setup",
    "sandbox-probe",
])
def test_preflight_failures_leave_accepted_generation_without_model_start(
    toolchains_api, tmp_path, failure
):
    workflow = toolchains_api.ToolchainWorkflow(tmp_path)
    outcome = workflow.preflight(failure)
    assert outcome.generation_status == "ACCEPTED"
    assert outcome.run_started is False
    assert outcome.model_processes_launched == 0
    assert outcome.resources_released is True
    assert workflow.can_prepare_next_execution() is True


def test_preflight_resource_preparation_preserves_single_owner_cleanup(
    toolchains_api, tmp_path
):
    lifecycle = toolchains_api.ToolchainWorkflow(tmp_path).preflight_ownership()
    assert lifecycle.owner == "preparation"
    assert lifecycle.transfers_only_after("RUN_STARTED")
    assert lifecycle.releases_scratch_and_cache_on_failure()


def test_resolved_plan_provenance_is_canonical_and_complete(toolchains_api, tmp_path):
    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    presentation = plan.provenance()
    assert list(presentation) == sorted(presentation)
    assert presentation["capability_plan_sha256"] == plan.sha256
    assert presentation["toolchains"][0]["qualification"] == "rust:1"
    command = presentation["toolchains"][0]["commands"][0]
    assert command["guest_path"] == "/opt/atlas/toolchains/rust/bin/cargo"
    assert len(command["executable_sha256"]) == 64
    assert command["observed_version"] == "cargo 1.0\n"
    assert presentation["caches"][0]["guest_path"] == "/var/cache/atlas-agent/cargo"
    assert presentation["caches"][0]["status"] == "mutable-unhashed"
    assert {"executor", "sandbox", "durable_owner"} <= presentation


def test_plan_hash_changes_for_qualification_root_command_env_or_cache_definition(
    toolchains_api, tmp_path
):
    root = tmp_path / "root"
    manifest = _manifest(root)
    base = _resolve(toolchains_api, manifest)
    for mutate in (
        lambda m: m["toolchains"]["rust"].update(qualification="rust:2"),
        lambda m: m["toolchains"]["rust"].update(source_root=str(tmp_path / "other")),
        lambda m: m["toolchains"]["rust"]["environment"].update(RUSTFLAGS="-O"),
        lambda m: m["caches"]["cargo"].update(qualification="cargo-cache/2"),
    ):
        changed = json.loads(json.dumps(manifest))
        mutate(changed)
        assert _resolve(toolchains_api, changed).sha256 != base.sha256


def test_mutating_cache_contents_does_not_change_capability_plan_hash(
    toolchains_api, tmp_path
):
    store = toolchains_api.CacheStore(tmp_path / "persistent")
    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    cache = store.prepare("project-a", "rust:1", "cargo-cache/1")
    before = plan.sha256
    cache.write_text("new package bytes")
    assert plan.sha256 == before
    assert plan.provenance()["caches"][0]["status"] == "mutable-unhashed"


def test_changed_effective_plan_turns_requested_reuse_into_safe_fresh_fallback(
    toolchains_api, tmp_path
):
    old = _resolve(toolchains_api, _manifest(tmp_path / "old"))
    new_manifest = _manifest(tmp_path / "new", qualification="rust:2")
    new = _resolve(toolchains_api, new_manifest)
    assert toolchains_api.resolve_session_reuse(old, new, requested="reuse") == {
        "session_mode": "fresh", "reason": "incompatible_capabilities"
    }
    assert toolchains_api.resolve_session_reuse(old, old, requested="reuse")["session_mode"] == "reuse"


def test_historical_replay_uses_archived_plan_not_current_machine_authority(
    toolchains_api, tmp_path
):
    archive = tmp_path / "archived-plan.json"
    archive.write_text(json.dumps({"capability_plan_sha256": "a" * 64,
                                   "source_root": "/old/operator/path"}))
    current = {"toolchains": {}}
    result = toolchains_api.validate_historical_plan(archive, current)
    assert result is True
    assert toolchains_api.mounts_for_historical_plan(archive) == []


def test_executor_and_sandbox_descriptors_agree_on_owner_and_capability_plan(
    toolchains_api, tmp_path
):
    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    descriptor = plan.executor_descriptor()
    assert descriptor["capability_plan_sha256"] == plan.sha256
    assert descriptor["executor"] == descriptor["durable_owner"]
    assert descriptor["sandbox"] == "bubblewrap"
