"""Versioned Codex asset identities and complete provisioning."""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tomllib
from pathlib import Path

ASSET_VERSION = "v0.1.1"
_REQUIRED = ("config.toml", "models-atlas-shell-only.json", "atlas-luna-local.config.toml", "atlas-luna-web.config.toml", "atlas-sol-local.config.toml", "atlas-sol-web.config.toml", "atlas-agent-prompts/common.md", "atlas-agent-prompts/state_audit.md")
_ALLOWED_METADATA = {"README.md"}
_RELEASE = Path(__file__).parents[2] / "atlas-release.toml"

def _identity(root: Path, names: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for name in names:
        data = (root / name).read_bytes(); encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big")); digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()

def _require_complete(root: Path) -> None:
    root = Path(root)
    if not root.is_dir() or root.is_symlink(): raise ValueError("INCOMPLETE_CODEX_ASSET_SET")
    names = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink(): raise ValueError("INVALID_CODEX_ASSET: " + relative)
        if path.is_dir(): continue
        if not path.is_file(): raise ValueError("INVALID_CODEX_ASSET: " + relative)
        names.add(relative)
    invalid = sorted(names - (set(_REQUIRED) | _ALLOWED_METADATA))
    if invalid: raise ValueError("INVALID_CODEX_ASSET: " + ", ".join(invalid))
    missing = [name for name in _REQUIRED if not (root / name).is_file() or (root / name).is_symlink()]
    if missing: raise ValueError("INCOMPLETE_CODEX_ASSET_SET: " + ", ".join(missing))
    for name in _REQUIRED:
        if not stat.S_ISREG((root / name).lstat().st_mode): raise ValueError("INVALID_CODEX_ASSET: " + name)

def asset_set_identity(root: Path) -> str:
    root = Path(root); _require_complete(root); return _identity(root, _REQUIRED)

def prompt_set_identity(root: Path) -> str:
    root = Path(root); _require_complete(root)
    return _identity(root, ("atlas-agent-prompts/common.md", "atlas-agent-prompts/state_audit.md"))

def _authoritative_identities():
    try:
        release = tomllib.loads(_RELEASE.read_text(encoding="utf-8")); codex = release["codex"]
        profiles = {name: item["sha256"] for name, item in codex["profiles"].items()}
        return release["asset_version"], release["asset_set_sha256"], release["prompt_set_sha256"], profiles
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise ValueError("CODEX_RELEASE_METADATA_INVALID") from error

def _validate_release_source(root: Path):
    version, expected_asset, expected_prompt, profiles = _authoritative_identities()
    if version != ASSET_VERSION: raise ValueError("CODEX_ASSET_VERSION_MISMATCH")
    asset, prompt = asset_set_identity(root), prompt_set_identity(root)
    if (asset, prompt) != (expected_asset, expected_prompt): raise ValueError("CODEX_ASSET_IDENTITY_MISMATCH")
    for name, expected in profiles.items():
        if hashlib.sha256((Path(root) / (name + ".config.toml")).read_bytes()).hexdigest() != expected:
            raise ValueError("CODEX_ASSET_IDENTITY_MISMATCH: " + name)
    return asset, prompt

def _safe_destination(codex_home: Path) -> None:
    if codex_home.exists() or codex_home.is_symlink(): raise ValueError("CODEX_HOME_ALREADY_EXISTS")
    parent = codex_home.parent
    if not parent.is_dir() or parent.is_symlink(): raise ValueError("CODEX_HOME_PARENT_UNSAFE")
    current = parent
    while current.parent != current:
        if current.is_symlink(): raise ValueError("CODEX_HOME_PARENT_UNSAFE")
        current = current.parent

def provision_codex_assets(source: Path, codex_home: Path) -> dict[str, str]:
    """Atomically publish one complete, authoritative v0.1.1 asset home."""
    source, codex_home = Path(source), Path(codex_home)
    asset, prompt = _validate_release_source(source); _safe_destination(codex_home)
    stage = codex_home.with_name(codex_home.name + ".staging")
    if stage.exists() or stage.is_symlink(): raise ValueError("CODEX_ASSET_STAGING_COLLISION")
    try:
        stage.mkdir(mode=0o700)
        for name in _REQUIRED:
            destination = stage / name; destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination, follow_symlinks=False); os.chmod(destination, 0o600, follow_symlinks=False)
        if _validate_release_source(stage) != (asset, prompt): raise ValueError("CODEX_ASSET_STAGING_IDENTITY_MISMATCH")
        os.replace(stage, codex_home)
    except BaseException:
        if stage.exists() and not stage.is_symlink(): shutil.rmtree(stage)
        raise
    return {"asset_set_sha256": asset, "prompt_set_sha256": prompt}
