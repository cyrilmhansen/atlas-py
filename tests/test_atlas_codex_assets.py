import json
import hashlib
import os
import shutil
import tomllib
import pytest
from types import SimpleNamespace
from pathlib import Path

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.assets import asset_set_identity, provision_codex_assets, prompt_set_identity
from tools.atlas_agent.policy import toml_dumps

ROOT = Path(__file__).parents[1]
ASSETS = ROOT / "codex-assets"
V010 = ASSETS / "v0.1.0"
V011 = ASSETS / "v0.1.1"

V010_HASHES = {
    "config.toml": "8680ff2454a4e2b954797d59308267e443a2565f1e8754c69a6707cc30c313ce",
    "models-atlas-shell-only.json": "757d35035ef92b7318dbfd4eb43fe2602bbc61cb32c1aad1398125d16058b439",
    "atlas-luna-local.config.toml": "95b431fe9acfd4e5bc733798215a5bf587e77d5502d97514687dd7fe54e92c98",
    "atlas-luna-web.config.toml": "6d1d9ab0ad4875eff3f4e928549890fe7baf35fbfff6236ee319ebd3f80b5d02",
    "atlas-sol-local.config.toml": "857854d85b6987f59de6dc7cc68dc7376390c8fcd1cdec2f5c5cbcafb7150fb7",
    "atlas-sol-web.config.toml": "d01699afd71ed9d6e85a44b70d6e0ead3240add0cab61d04a2b61d1d793b61fa",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_v010_assets_are_imported_without_byte_changes():
    assert {name: sha256(V010 / name) for name in V010_HASHES} == V010_HASHES


def test_prompt_asset_selection_is_deterministic_and_role_specific():
    expected = {
        "implementation": {"atlas-luna-local", "atlas-luna-web"},
        "patch_review": {"atlas-sol-local"},
        "state_audit": {"atlas-sol-local"},
    }
    selected = {}
    for role, profiles in expected.items():
        selected[role] = {
            profile
            for profile in profiles
            if (V011 / f"{profile}.config.toml").is_file()
        }
    assert selected == expected

    for profile in (V011 / "atlas-luna-local.config.toml", V011 / "atlas-luna-web.config.toml"):
        assert tomllib.loads(profile.read_text())["model_instructions_file"] == "atlas-agent-prompts/common.md"

    assert "implementation scope" in tomllib.loads(
        (V011 / "atlas-luna-local.config.toml").read_text()
    )["developer_instructions"]
    assert "Read-only review" in tomllib.loads(
        (V011 / "atlas-sol-local.config.toml").read_text()
    )["developer_instructions"]
    assert "factual audit" in (
        V011 / "atlas-agent-prompts" / "state_audit.md"
    ).read_text()


def test_prompt_path_is_codex_home_relative_not_target_repository_relative():
    common = V011 / "atlas-agent-prompts" / "common.md"
    assert common.is_file()
    assert all(
        tomllib.loads((V011 / profile).read_text())["model_instructions_file"]
        == "atlas-agent-prompts/common.md"
        for profile in (
            "atlas-luna-local.config.toml",
            "atlas-luna-web.config.toml",
            "atlas-sol-local.config.toml",
            "atlas-sol-web.config.toml",
        )
    )
    assert "/" not in tomllib.loads(
        (V011 / "atlas-luna-local.config.toml").read_text()
    )["model_catalog_json"]


def test_atlas_common_prompt_is_compact_and_excludes_interactive_scaffolding():
    common = (V011 / "atlas-agent-prompts" / "common.md").read_text()
    assert len(common.encode()) < 2_000
    assert len(common.split()) < 300
    for phrase in ("old friend", "commentary", "visualizations", "conversation compaction", "skills machinery"):
        assert phrase not in common


def test_state_audit_role_is_selected_by_atlas_executor(tmp_path):
    home = tmp_path / "codex-home"
    role_dir = home / "atlas-agent-prompts"
    role_dir.mkdir(parents=True)
    role_text = (V011 / "atlas-agent-prompts" / "state_audit.md").read_text()
    (role_dir / "state_audit.md").write_text(role_text)
    executor = CodexExecutor(executable="/bin/true", codex_home=home)
    command = executor._build_command(
        SimpleNamespace(repository_root=tmp_path),
        {
            "action": "state_audit",
            "codex_profile": "atlas-sol-local",
            "web_search": "disabled",
            "requested_reasoning_effort": "high",
            "session_mode": "fresh",
        },
    )
    role_override = next(value for value in command if value.startswith("developer_instructions="))
    parsed = tomllib.loads(role_override)
    assert parsed["developer_instructions"] == role_text


def test_state_audit_override_is_toml_for_controls_and_unicode(tmp_path):
    home = tmp_path / "codex-home"; (home / "atlas-agent-prompts").mkdir(parents=True)
    values = ["ASCII", "two words", "apostrophe's", 'a "quote"', r"a\b", "line\nnext",
              "tab\there", "back\bspace\fform", "é漢", "emoji 😀"]
    executor = CodexExecutor(executable="/bin/true", codex_home=home)
    for value in values:
        (home / "atlas-agent-prompts" / "state_audit.md").write_text(value, encoding="utf-8")
        command = executor._build_command(SimpleNamespace(repository_root=tmp_path), {
            "action": "state_audit", "codex_profile": "atlas-sol-local",
            "web_search": "disabled", "requested_reasoning_effort": "high",
            "session_mode": "fresh",
        })
        override = next(item for item in command if item.startswith("developer_instructions="))
        assert tomllib.loads(override)["developer_instructions"] == value


def test_asset_identities_and_provisioning_are_complete(tmp_path):
    destination = tmp_path / "codex-home"
    identities = provision_codex_assets(V011, destination)
    assert identities == {"asset_set_sha256": asset_set_identity(V011),
                          "prompt_set_sha256": prompt_set_identity(V011)}
    assert all((destination / name).is_file() for name in (
        "config.toml", "models-atlas-shell-only.json",
        "atlas-luna-local.config.toml", "atlas-luna-web.config.toml",
        "atlas-sol-local.config.toml", "atlas-sol-web.config.toml",
        "atlas-agent-prompts/common.md", "atlas-agent-prompts/state_audit.md"))


def _asset_copy(tmp_path):
    source = tmp_path / "assets"
    shutil.copytree(V011, source)
    return source


def test_asset_identities_match_authoritative_release(tmp_path):
    release = tomllib.loads((ROOT / "atlas-release.toml").read_text())
    assert release["asset_version"] == "v0.1.1"
    assert release["asset_set_sha256"] == asset_set_identity(V011)
    assert release["prompt_set_sha256"] == prompt_set_identity(V011)
    assert {name: item["sha256"] for name, item in release["codex"]["profiles"].items()} == {
        name.removesuffix(".config.toml"): sha256(V011 / name)
        for name in ("atlas-luna-local.config.toml", "atlas-luna-web.config.toml",
                     "atlas-sol-local.config.toml", "atlas-sol-web.config.toml")
    }


@pytest.mark.parametrize("mutation", ["missing", "corrupt", "source_symlink", "extra"])
def test_invalid_source_fails_before_destination_mutation(tmp_path, mutation):
    source = _asset_copy(tmp_path)
    target_name = "config.toml"
    if mutation == "missing": (source / target_name).unlink()
    elif mutation == "corrupt":
        os.chmod(source / target_name, 0o600); (source / target_name).write_text("corrupt\n")
    elif mutation == "source_symlink":
        (source / target_name).unlink(); (source / target_name).symlink_to(V011 / target_name)
    else: (source / "unexpected.txt").write_text("invalid")
    destination = tmp_path / "codex-home"
    with pytest.raises(ValueError): provision_codex_assets(source, destination)
    assert not destination.exists()


def test_symlinked_destination_topology_is_rejected(tmp_path):
    source = _asset_copy(tmp_path); real = tmp_path / "real"; real.mkdir()
    destination = tmp_path / "link"; destination.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="CODEX_HOME_ALREADY_EXISTS"):
        provision_codex_assets(source, destination)
    parent_link = tmp_path / "parent-link"; parent_link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="CODEX_HOME_PARENT_UNSAFE"):
        provision_codex_assets(source, parent_link / "home")


def test_publication_failure_leaves_no_accepted_or_mixed_home(tmp_path, monkeypatch):
    source = _asset_copy(tmp_path); destination = tmp_path / "codex-home"
    def fail(*args, **kwargs): raise OSError("injected publication failure")
    monkeypatch.setattr("tools.atlas_agent.assets.os.replace", fail)
    with pytest.raises(OSError, match="injected publication failure"):
        provision_codex_assets(source, destination)
    assert not destination.exists()
    assert not destination.with_name("codex-home.staging").exists()


def test_existing_home_is_explicitly_refused_without_partial_update(tmp_path):
    source = _asset_copy(tmp_path); destination = tmp_path / "codex-home"
    destination.mkdir(); sentinel = destination / "sentinel"; sentinel.write_text("keep")
    with pytest.raises(ValueError, match="CODEX_HOME_ALREADY_EXISTS"):
        provision_codex_assets(source, destination)
    assert sentinel.read_text() == "keep"


def test_policy_hash_is_toml_and_preserves_non_bmp_unicode():
    data = {"schema": "atlas-agent-policy/1", "label": "Atlas 🛰️ 𝄞"}
    encoded = toml_dumps(data).encode("utf-8")
    assert tomllib.loads(encoded.decode("utf-8")) == data
