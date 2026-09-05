"""G16 red contract for the frozen G15 toolchain findings.

These assertions deliberately name the authority boundary rather than
accepting a compatibility fallback.  A failure in this file is a product
failure (unless the test is explicitly skipped for native sandbox support).
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.atlas_agent import toolchains

from test_agent_toolchains_p06 import _digest, _manifest, _resolve


@pytest.fixture
def toolchains_api():
    return toolchains


def _replace_root_with_same_bytes(root):
    replacement = root.parent / (root.name + "-replacement")
    os.rename(root, replacement)
    os.rename(replacement, root)


@pytest.mark.parametrize("mode", [0o602, 0o606])
def test_machine_manifest_requires_regular_private_non_writable_authority(
    tmp_path, monkeypatch, mode
):
    manifest = tmp_path / "machine.toml"
    manifest.write_text('schema = "atlas-agent-machine-capabilities/1"\n')
    manifest.chmod(mode)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(manifest))
    with pytest.raises(toolchains.CapabilityError, match="CONFIG|AUTHORITY"):
        toolchains.load_machine_capabilities()


def test_machine_manifest_authority_path_is_canonical(tmp_path, monkeypatch):
    real = tmp_path / "machine.toml"
    real.write_text('schema = "atlas-agent-machine-capabilities/1"\n')
    monkeypatch.setenv(
        "ATLAS_AGENT_CAPABILITIES_FILE", str(tmp_path / "x" / ".." / "machine.toml")
    )
    with pytest.raises(toolchains.CapabilityError, match="CONFIG|AUTHORITY"):
        toolchains.load_machine_capabilities()


def test_machine_manifest_must_not_be_a_symlink(tmp_path, monkeypatch):
    real = tmp_path / "machine.real"
    real.write_text('schema = "atlas-agent-machine-capabilities/1"\n')
    link = tmp_path / "machine.toml"
    link.symlink_to(real)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(link))
    with pytest.raises(toolchains.CapabilityError, match="CONFIG|AUTHORITY"):
        toolchains.load_machine_capabilities()


@pytest.mark.parametrize("overlap", ["repository_root", "repository_git_identity"])
def test_machine_authority_and_persistent_cache_must_be_outside_repository(
    toolchains_api, tmp_path, overlap
):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    manifest_path = repo / "machine.toml"
    manifest_path.write_text('schema = "atlas-agent-machine-capabilities/1"\n')
    manifest = _manifest(tmp_path / "qualified")
    manifest["repository_root"] = str(repo)
    manifest["repository_identity"] = str(repo / ".git")
    manifest["persistent_cache_root"] = str(
        repo if overlap == "repository_root" else repo / ".git"
    )
    with pytest.raises(toolchains_api.CapabilityError, match="AUTHORITY|OVERLAP|CONFIG"):
        _resolve(toolchains_api, manifest, {"toolchains": ["rust"], "caches": ["cargo"]})


@pytest.mark.parametrize("repository_claim", [None, "false-repository-root"])
def test_workflow_binds_machine_manifest_placement_to_actual_repository(
    tmp_path, monkeypatch, repository_claim
):
    """Manifest-supplied repository labels cannot authorize a local catalog."""
    from tools.atlas_agent.workflow import Workflow

    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\n'
        'allowed_untracked = ["corpus_miner/"]\n'
    )
    qualified = _manifest(tmp_path / "qualified")
    lines = [
        'schema = "atlas-agent-machine-capabilities/1"',
        f'persistent_cache_root = "{qualified["persistent_cache_root"]}"',
    ]
    if repository_claim:
        lines.append(f'repository_root = "{tmp_path / repository_claim}"')
    lines += [
        '[toolchains.rust]',
        f'qualification = "{qualified["toolchains"]["rust"]["qualification"]}"',
        f'source_root = "{qualified["toolchains"]["rust"]["source_root"]}"',
        '[toolchains.rust.commands.cargo]',
        f'path = "{qualified["toolchains"]["rust"]["commands"]["cargo"]["path"]}"',
        f'sha256 = "{qualified["toolchains"]["rust"]["commands"]["cargo"]["sha256"]}"',
        'probe_args = ["--version"]',
        f'probe_output_sha256 = "{qualified["toolchains"]["rust"]["commands"]["cargo"]["probe_output_sha256"]}"',
    ]
    machine = repo / "machine.toml"
    machine.write_text("\n".join(lines) + "\n")
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(machine))
    with pytest.raises(Exception, match="OVERLAP|AUTHORITY"):
        Workflow(repo).resolve_capabilities({"toolchains": ["rust"], "caches": []})


@pytest.mark.parametrize("broad", ["HOME", ".cargo", ".rustup", ".local",
                                   ".cache", ".config"])
def test_broad_home_and_user_state_sources_are_rejected(
    toolchains_api, tmp_path, monkeypatch, broad
):
    home = tmp_path / "home"
    source = home if broad == "HOME" else home / broad
    source.mkdir(parents=True)
    manifest = _manifest(source)
    monkeypatch.setenv("HOME", str(home))
    with pytest.raises(toolchains_api.CapabilityError, match="HOME|USER|SOURCE|BROAD"):
        _resolve(toolchains_api, manifest, {"toolchains": ["rust"], "caches": []})


def test_system_visible_requires_exact_host_guest_identity(toolchains_api, tmp_path):
    executable = Path("/usr/bin/true")
    manifest = {
        "schema": "atlas-agent-machine-capabilities/1",
        "persistent_cache_root": str(tmp_path / "persistent"),
        "toolchains": {"system": {
            "exposure": "system-visible", "qualification": "system:true",
            "source_root": "/usr", "guest_root": "/opt/relocated",
            "commands": {"true": {
                "path": "bin/true", "sha256": _digest(executable.read_bytes()),
                "probe_args": [], "probe_output_sha256": _digest(b"\0")}}}},
        "caches": {},
    }
    with pytest.raises(toolchains_api.CapabilityError, match="QUALIFICATION|IDENTITY"):
        _resolve(toolchains_api, manifest, {"toolchains": ["system"], "caches": []})


def test_system_visible_fallback_cannot_split_host_and_guest_command_identity(
    toolchains_api, tmp_path
):
    executable = Path("/usr/bin/true")
    manifest = {
        "schema": "atlas-agent-machine-capabilities/1",
        "persistent_cache_root": str(tmp_path / "persistent"),
        "toolchains": {"system": {
            "exposure": "system-visible", "qualification": "system:true",
            "source_root": "/usr", "guest_root": "/usr",
            "commands": {"true": {
                "path": "true", "sha256": _digest(executable.read_bytes()),
                "probe_args": [], "probe_output_sha256": _digest(b"\0")}}}},
        "caches": {},
    }
    plan = _resolve(toolchains_api, manifest, {"toolchains": ["system"], "caches": []})
    assert plan.command("true").host_path == plan.command("true").guest_path


def test_private_home_is_not_exposed_by_a_broad_manifest_root(
    toolchains_api, tmp_path, monkeypatch
):
    home = tmp_path / "home"
    (home / ".cargo").mkdir(parents=True)
    manifest = _manifest(home)
    monkeypatch.setenv("HOME", str(home))
    with pytest.raises(toolchains_api.CapabilityError, match="HOME|USER|SOURCE|BROAD"):
        _resolve(toolchains_api, manifest, {"toolchains": ["rust"], "caches": []})


def test_preparation_retains_authority_descriptor_and_proc_fd_mount(
    toolchains_api, tmp_path
):
    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"),
                    {"toolchains": ["rust"], "caches": []})
    mount = plan.mounts[0]
    assert isinstance(getattr(mount, "authority_fd"), int)
    assert getattr(mount, "authority_path") == f"/proc/self/fd/{mount.authority_fd}"
    descriptor = plan.executor_descriptor()
    assert descriptor["mounts"][0]["source"] == mount.authority_path


def test_capability_plan_hash_contains_complete_cache_authority_but_not_contents(
    toolchains_api, tmp_path
):
    manifest = _manifest(tmp_path / "root")
    plan = _resolve(toolchains_api, manifest)
    facts = plan.provenance()["caches"][0]
    assert {"guest_path", "backing", "project_scope", "toolchain_scope",
            "isolation", "lifetime", "status"} <= set(facts)
    assert "mutable_contents_sha256" not in facts
    assert plan.sha256 == _resolve(toolchains_api, manifest).sha256


def test_cache_layout_is_project_then_toolchain_definition_then_name(
    toolchains_api, tmp_path
):
    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    cache = plan.caches[0]
    assert cache.backing.parent.parent.name == cache.scope.project_key
    assert cache.backing.parent.name == cache.scope.toolchain_key
    assert cache.backing.name == cache.name


def test_cache_control_and_data_are_effective_uid_0700_and_invalid_mode_fails_closed(
    toolchains_api, tmp_path
):
    store = toolchains_api.CacheStore(tmp_path / "persistent")
    data = store.prepare("project", "rust-set", "cargo-definition")
    control = data.parent.parent / "control"
    control.mkdir(parents=True, exist_ok=True)
    data.chmod(0o755)
    with pytest.raises(Exception, match="CACHE|AUTHORITY|MODE"):
        store.validate(data)
    assert data.stat().st_uid == os.geteuid()
    assert control.stat().st_uid == os.geteuid()
    assert data.stat().st_mode & 0o777 == 0o700
    assert control.stat().st_mode & 0o777 == 0o700


def test_production_cache_preparation_rejects_invalid_backing_mode(
    toolchains_api, tmp_path, monkeypatch
):
    """Exercise AtlasBubblewrapExecutor's production cache setup boundary."""
    from tools.atlas_agent.bubblewrap import AtlasBubblewrapExecutor
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec, PreparedExecution

    plan = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    cache = plan.caches[0]
    cache.backing.mkdir(parents=True)
    cache.backing.chmod(0o755)
    spec = ExecutionSpec(
        1, "0" * 64, "implementation", tmp_path / "prompt",
        tmp_path / "repo", "cache-mode", tmp_path / "report",
        capability_plan=plan,
    )
    spec.prompt_path.write_text("prompt")
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    executor.sandbox = "workspace-write"
    envelope = {
        "sandbox_mode": "workspace-write", "approval_policy": "never",
        "approvals_reviewer": "user", "strict_config": True,
        "ignore_rules": True, "network_access": False,
    }
    monkeypatch.setattr(
        CodexExecutor, "prepare_execution",
        lambda self, value: PreparedExecution(
            value, "codex", ("codex",), "codex/1", envelope, None))
    monkeypatch.setattr(executor, "_bwrap_version", lambda: "1")
    monkeypatch.setattr(executor, "_validate_namespace", lambda: None)
    monkeypatch.setattr(executor, "_git_dir", lambda root: None)
    monkeypatch.setattr(executor.scratch_store, "ensure_root", lambda: None)
    monkeypatch.setattr(executor, "_validate_disk_scratch", lambda: None)
    monkeypatch.setattr(executor, "_prepare_scratch", lambda spec: None)
    monkeypatch.setattr(executor, "_capability_probe", lambda: None)
    monkeypatch.setattr(
        "tools.atlas_agent.bubblewrap._native_codex",
        lambda executable: Path("/bin/sh"),
    )
    with pytest.raises(Exception, match="CACHE|AUTHORITY|MODE"):
        # The production path must validate the backing it is about to expose;
        # it must not silently accept the pre-existing unsafe mode.
        executor.prepare_execution(spec)


def test_durable_cache_provenance_exposes_scope_lifecycle_and_mutable_status(
    toolchains_api, tmp_path
):
    cache = _resolve(toolchains_api, _manifest(tmp_path / "root")).provenance()["caches"][0]
    assert {"guest_path", "backing", "scope", "isolation", "lifetime",
            "status"} <= set(cache)
    assert cache["status"] == "mutable-unhashed"


def test_cache_namespace_definition_and_toolchain_identity_break_reuse(
    toolchains_api, tmp_path
):
    base = _resolve(toolchains_api, _manifest(tmp_path / "root"))
    for mutation in ("qualification", "cache-definition", "toolchain-set"):
        changed = _manifest(tmp_path / ("root-" + mutation))
        requirements = {"toolchains": ["rust"], "caches": ["cargo"]}
        if mutation == "qualification":
            changed["toolchains"]["rust"]["qualification"] = "rust:changed"
        elif mutation == "cache-definition":
            changed["caches"]["cargo"]["qualification"] = "cargo-cache:changed"
        else:
            changed["toolchains"]["other"] = changed["toolchains"].pop("rust")
            requirements["toolchains"] = ["other"]
        candidate = _resolve(toolchains_api, changed, requirements)
        assert candidate.sha256 != base.sha256
        assert candidate.caches[0].backing != base.caches[0].backing


def test_environment_tokens_are_fully_resolved_to_qualified_guest_paths(
    toolchains_api, tmp_path
):
    manifest = _manifest(tmp_path / "root")
    manifest["toolchains"]["rust"]["environment"] = {
        "TOOL_ROOT": "${ROOT}/bin",
        "TOOL_CACHE": "${CACHE:cargo}",
    }
    plan = _resolve(toolchains_api, manifest)
    assert plan.environment()["TOOL_ROOT"] == "/opt/atlas/toolchains/rust/bin"
    assert plan.environment()["TOOL_CACHE"] == "/var/cache/atlas-agent/cargo"
    assert not any("${" in value for value in plan.environment().values())


def test_unresolved_permitted_environment_token_is_rejected(
    toolchains_api, tmp_path
):
    manifest = _manifest(tmp_path / "root")
    manifest["toolchains"]["rust"]["environment"] = {"BAD": "${CACHE:missing}"}
    with pytest.raises(toolchains_api.CapabilityError, match="INTERPOL|CACHE|RESOL"):
        _resolve(toolchains_api, manifest)
def test_qualified_source_identity_is_not_stale_path_authority(toolchains_api, tmp_path):
    root = tmp_path / "root"
    manifest = _manifest(root)
    first = _resolve(toolchains_api, manifest)
    _replace_root_with_same_bytes(root)
    second = _resolve(toolchains_api, manifest)
    assert second.sha256 != first.sha256, "source dev/inode identity was not qualified"


@pytest.mark.parametrize(
    "guest_root",
    ["/home", "/home/atlas", "/tmp", "/var/tmp", "/usr",
     "/repo/.git", "/atlas-controller", "/opt/atlas/toolchains/other"],
)
def test_private_toolchain_guest_namespace_is_fixed_and_non_overlapping(
    toolchains_api, tmp_path, guest_root
):
    manifest = _manifest(tmp_path / "root")
    manifest["toolchains"]["rust"]["guest_root"] = guest_root
    with pytest.raises(toolchains.CapabilityError, match="QUALIFICATION|SOURCE|NAMESPACE"):
        _resolve(toolchains_api, manifest, {"toolchains": ["rust"], "caches": []})


def test_plan_hash_binds_probe_args_and_probe_output_identity(toolchains_api, tmp_path):
    root = tmp_path / "root"
    base_manifest = _manifest(root)
    base = _resolve(toolchains_api, base_manifest)
    changed = json.loads(json.dumps(base_manifest))
    command = changed["toolchains"]["rust"]["commands"]["cargo"]
    command["probe_args"] = ["--version", "qualification-identity"]
    assert _resolve(toolchains_api, changed).sha256 != base.sha256


def test_plan_hash_binds_observed_version_identity(toolchains_api, tmp_path):
    root = tmp_path / "root"
    manifest = _manifest(root)
    base = _resolve(toolchains_api, manifest)
    executable = root / "bin" / "cargo"
    executable.write_text("#!/bin/sh\nprintf '%b' 'cargo 2.0\\n'\n")
    executable.chmod(0o755)
    manifest["toolchains"]["rust"]["commands"]["cargo"]["sha256"] = _digest(
        executable.read_bytes()
    )
    manifest["toolchains"]["rust"]["commands"]["cargo"]["probe_output_sha256"] = _digest(
        b"cargo 2.0\n\0"
    )
    assert _resolve(toolchains_api, manifest).sha256 != base.sha256


def test_plan_hash_binds_identity_file_and_source_object_identity(toolchains_api, tmp_path):
    root = tmp_path / "root"
    manifest = _manifest(root)
    base = _resolve(toolchains_api, manifest)
    identity = root / "release"
    identity.write_text("release-1\n")
    manifest["toolchains"]["rust"]["identity_files"] = {
        "release": {"path": "release", "sha256": _digest(identity.read_bytes())}
    }
    with_identity = _resolve(toolchains_api, manifest)
    assert with_identity.sha256 != base.sha256
    _replace_root_with_same_bytes(root)
    assert _resolve(toolchains_api, manifest).sha256 != with_identity.sha256


def test_plan_hash_binds_machine_catalog_identity(toolchains_api, tmp_path):
    manifest = _manifest(tmp_path / "root")
    base = _resolve(toolchains_api, manifest)
    changed = json.loads(json.dumps(manifest))
    changed["machine_catalog_identity"] = "catalog-inode-2"
    assert _resolve(toolchains_api, changed).sha256 != base.sha256


def test_mutable_cache_content_is_not_plan_identity(toolchains_api, tmp_path):
    manifest = _manifest(tmp_path / "root")
    plan = _resolve(toolchains_api, manifest)
    cache = plan.caches[0].backing
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("mutable bytes")
    assert plan.sha256 == _resolve(toolchains_api, manifest).sha256


def test_cache_namespace_binds_repository_identity_not_literal_project(
    toolchains_api, tmp_path
):
    manifest = _manifest(tmp_path / "tool")
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    (repo_a / ".git").mkdir(parents=True)
    (repo_b / ".git").mkdir(parents=True)
    first_manifest = json.loads(json.dumps(manifest))
    second_manifest = json.loads(json.dumps(manifest))
    first_manifest["repository_identity"] = str(repo_a / ".git")
    second_manifest["repository_identity"] = str(repo_b / ".git")
    first = _resolve(toolchains_api, first_manifest)
    second = _resolve(toolchains_api, second_manifest)
    assert first.caches[0].backing != second.caches[0].backing


def test_cache_definition_and_qualification_have_distinct_authority_namespace(
    toolchains_api, tmp_path
):
    manifest = _manifest(tmp_path / "root")
    first = _resolve(toolchains_api, manifest)
    changed = json.loads(json.dumps(manifest))
    changed["caches"]["cargo"]["qualification"] = "cargo-cache/2"
    second = _resolve(toolchains_api, changed)
    assert second.caches[0].backing != first.caches[0].backing
    assert second.sha256 != first.sha256


def test_recreated_repository_git_identity_cannot_reuse_cache_authority(
    toolchains_api, tmp_path
):
    manifest = _manifest(tmp_path / "root")
    git_path = tmp_path / "repo" / ".git"
    git_path.mkdir(parents=True)
    first_manifest = json.loads(json.dumps(manifest))
    first_manifest["repository_git_identity"] = "dev-inode-1"
    second_manifest = json.loads(json.dumps(manifest))
    second_manifest["repository_git_identity"] = "dev-inode-2"
    first = _resolve(toolchains_api, first_manifest)
    second = _resolve(toolchains_api, second_manifest)
    assert first.caches[0].backing != second.caches[0].backing


def test_cache_control_lock_is_not_in_guest_writable_backing(toolchains_api, tmp_path):
    store = toolchains_api.CacheStore(tmp_path / "persistent")
    backing = store.prepare("project", "rust:1", "cargo-cache/1")
    backing.unlink()
    backing.mkdir()
    owner = store.lock_directory(backing)
    try:
        assert owner.path.parent.name == "control"
        assert not owner.path.is_relative_to(backing)
    finally:
        owner.release()
