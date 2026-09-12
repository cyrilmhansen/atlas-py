"""Reconstruct and build qualified Atlas Codex source identities."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib


RECIPE_SCHEMA = "atlas-codex-build-recipe/1"
_RECIPE_KEYS = {
    "schema",
    "name",
    "upstream_tag",
    "upstream_commit",
    "required_commits",
    "final_ref",
    "cargo_subdir",
    "cargo_package",
    "expected_version",
    "expected_rustc",
    "expected_cargo",
    "required_exec_help",
}


class CodexBuildError(RuntimeError):
    pass


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise CodexBuildError(f"command failed to start: {argv[0]}: {error}") from error
    if result.returncode != 0:
        tail = (result.stdout + "\n" + result.stderr)[-4000:].strip()
        raise CodexBuildError(
            f"command failed ({result.returncode}): {' '.join(argv)}"
            + (f"\n{tail}" if tail else "")
        )
    return result


def _git(repo: Path, *args: str) -> str:
    return _run(["git", "-C", str(repo), *args]).stdout.strip()


def _git_is_ancestor(repo: Path, older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_recipe(path: Path) -> dict:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CodexBuildError(f"Codex build recipe is unreadable: {error}") from error

    if not isinstance(data, dict) or set(data) != _RECIPE_KEYS:
        raise CodexBuildError("Codex build recipe has unexpected keys")
    if data.get("schema") != RECIPE_SCHEMA:
        raise CodexBuildError("unsupported Codex build recipe schema")

    for key in (
        "name", "upstream_tag", "upstream_commit", "final_ref",
        "cargo_subdir", "cargo_package", "expected_version",
        "expected_rustc", "expected_cargo",
    ):
        if not isinstance(data.get(key), str) or not data[key]:
            raise CodexBuildError(f"invalid recipe field: {key}")

    if not re.fullmatch(r"[0-9a-f]{40}", data["upstream_commit"]):
        raise CodexBuildError("upstream_commit must be a full 40-hex SHA")
    if not re.fullmatch(r"[0-9a-f]{7,40}", data["final_ref"]):
        raise CodexBuildError("final_ref must be a hexadecimal commit ref")

    required = data.get("required_commits")
    if (
        not isinstance(required, list)
        or not required
        or any(not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{7,40}", ref)
               for ref in required)
    ):
        raise CodexBuildError("required_commits must be a non-empty list of commit refs")

    help_tokens = data.get("required_exec_help")
    if (
        not isinstance(help_tokens, list)
        or not help_tokens
        or any(not isinstance(token, str) or not token for token in help_tokens)
    ):
        raise CodexBuildError("required_exec_help must be a non-empty string list")

    for key in ("cargo_subdir", "cargo_package"):
        value = data[key]
        if value.startswith("/") or "\\" in value or ".." in Path(value).parts:
            raise CodexBuildError(f"unsafe recipe path/name: {key}")

    return data


def resolve_recipe(source_repo: Path, recipe: dict) -> dict:
    try:
        repo = source_repo.expanduser().resolve(strict=True)
    except OSError as error:
        raise CodexBuildError(f"Codex source repository cannot be resolved: {error}") from error
    if not repo.is_dir():
        raise CodexBuildError("Codex source repository is not a directory")

    inside = _git(repo, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise CodexBuildError("Codex source is not a Git worktree")

    upstream_from_sha = _git(repo, "rev-parse", f"{recipe['upstream_commit']}^{{commit}}")
    upstream_from_tag = _git(repo, "rev-parse", f"{recipe['upstream_tag']}^{{commit}}")
    if upstream_from_sha != recipe["upstream_commit"]:
        raise CodexBuildError("upstream commit does not resolve to expected identity")
    if upstream_from_tag != recipe["upstream_commit"]:
        raise CodexBuildError(
            f"upstream tag mismatch: tag={upstream_from_tag} "
            f"expected={recipe['upstream_commit']}"
        )

    final_sha = _git(repo, "rev-parse", f"{recipe['final_ref']}^{{commit}}")
    required = [
        _git(repo, "rev-parse", f"{ref}^{{commit}}")
        for ref in recipe["required_commits"]
    ]

    chain = [recipe["upstream_commit"], *required, final_sha]
    for older, newer in zip(chain, chain[1:]):
        if not _git_is_ancestor(repo, older, newer):
            raise CodexBuildError(
                f"qualified Codex source lineage is broken: {older} !<= {newer}"
            )
    if required[-1] != final_sha:
        raise CodexBuildError(
            "final_ref must resolve to the last required qualified commit"
        )

    return {
        "source_repo": str(repo),
        "recipe": recipe["name"],
        "upstream_tag": recipe["upstream_tag"],
        "upstream_commit": recipe["upstream_commit"],
        "required_commits": required,
        "final_sha": final_sha,
    }


def reconstruct_source(*, source_repo: Path, worktree: Path, recipe_path: Path) -> dict:
    recipe = load_recipe(recipe_path)
    resolved = resolve_recipe(source_repo, recipe)
    repo = Path(resolved["source_repo"])

    target = worktree.expanduser()
    if target.exists() or target.is_symlink():
        raise CodexBuildError(f"Codex reconstruction target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    added = False
    try:
        _run([
            "git", "-C", str(repo), "worktree", "add",
            "--detach", str(target), resolved["final_sha"],
        ])
        added = True
        target = target.resolve(strict=True)
        observed = _git(target, "rev-parse", "HEAD")
        if observed != resolved["final_sha"]:
            raise CodexBuildError(
                f"reconstructed Codex HEAD mismatch: {observed}"
            )
        if _git(target, "status", "--porcelain=v2", "--untracked-files=all"):
            raise CodexBuildError("reconstructed Codex worktree is not clean")
    except BaseException:
        if added:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(target)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        raise

    return {
        "schema": "atlas-codex-reconstruction/1",
        **resolved,
        "worktree": str(target),
        "status": "PASS",
    }


def _verify_worktree(worktree: Path, recipe_path: Path) -> tuple[Path, dict, dict]:
    recipe = load_recipe(recipe_path)
    try:
        worktree = worktree.expanduser().resolve(strict=True)
    except OSError as error:
        raise CodexBuildError(f"Codex build worktree cannot be resolved: {error}") from error
    resolved = resolve_recipe(worktree, recipe)
    head = _git(worktree, "rev-parse", "HEAD")
    if head != resolved["final_sha"]:
        raise CodexBuildError(
            f"Codex build worktree HEAD mismatch: {head} != {resolved['final_sha']}"
        )
    if _git(worktree, "status", "--porcelain=v2", "--untracked-files=all"):
        raise CodexBuildError("Codex build worktree is not clean")
    return worktree, recipe, resolved


def _release_lock_refresh_only(before: bytes, after: bytes, release_version: str) -> int:
    """Accept only Cargo's release-version refresh for workspace packages."""
    try:
        old = tomllib.loads(before.decode("utf-8"))
        new = tomllib.loads(after.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise CodexBuildError(f"Cargo.lock refresh is not valid TOML: {error}") from error

    if set(old) != set(new):
        raise CodexBuildError("Cargo.lock refresh changed top-level structure")

    old_packages = old.get("package")
    new_packages = new.get("package")
    if not isinstance(old_packages, list) or not isinstance(new_packages, list):
        raise CodexBuildError("Cargo.lock refresh has no package list")
    if len(old_packages) != len(new_packages):
        raise CodexBuildError("Cargo.lock refresh changed package count")

    changed = 0
    for index, (old_pkg, new_pkg) in enumerate(zip(old_packages, new_packages)):
        if old_pkg == new_pkg:
            continue
        if not isinstance(old_pkg, dict) or not isinstance(new_pkg, dict):
            raise CodexBuildError(f"Cargo.lock package {index} has invalid structure")

        old_normalized = dict(old_pkg)
        new_normalized = dict(new_pkg)
        old_version = old_normalized.pop("version", None)
        new_version = new_normalized.pop("version", None)

        if (
            old_normalized != new_normalized
            or old_version != "0.0.0"
            or new_version != release_version
        ):
            name = old_pkg.get("name", f"index {index}")
            raise CodexBuildError(
                f"Cargo.lock refresh changed more than workspace release version: {name}"
            )
        changed += 1

    old_meta = dict(old)
    new_meta = dict(new)
    old_meta.pop("package", None)
    new_meta.pop("package", None)
    if old_meta != new_meta:
        raise CodexBuildError("Cargo.lock refresh changed non-package metadata")
    if changed == 0:
        raise CodexBuildError("Cargo.lock was modified without a release-version refresh")
    return changed


def _workspace_release_version(recipe: dict) -> str:
    prefix = "codex-cli "
    expected = recipe["expected_version"]
    if not expected.startswith(prefix):
        raise CodexBuildError("expected_version does not encode a Codex CLI version")
    version = expected[len(prefix):]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise CodexBuildError(f"invalid workspace release version: {version!r}")
    return version


def _verify_candidate(binary: Path, recipe: dict) -> dict:
    if binary.is_symlink() or not binary.is_file() or not os.access(binary, os.X_OK):
        raise CodexBuildError(f"built Codex runtime is missing/unsafe: {binary}")
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise CodexBuildError("built Codex runtime is not ELF")

    version = _run([str(binary), "--version"]).stdout.strip()
    if version != recipe["expected_version"]:
        raise CodexBuildError(
            f"built Codex version mismatch: {version!r} "
            f"!= {recipe['expected_version']!r}"
        )

    help_text = _run([str(binary), "exec", "--help"]).stdout
    missing = [token for token in recipe["required_exec_help"] if token not in help_text]
    if missing:
        raise CodexBuildError(
            f"built Codex public contract missing tokens: {missing}"
        )

    return {
        "binary": str(binary),
        "version": version,
        "sha256": _sha256(binary),
        "exec_help_contract": "PASS",
    }


def build_runtime(*, worktree: Path, recipe_path: Path, target_dir: Path,
                  min_free_gib: float = 30.0) -> dict:
    if not isinstance(min_free_gib, (int, float)) or isinstance(min_free_gib, bool) or min_free_gib < 0:
        raise CodexBuildError("min_free_gib must be a non-negative number")

    worktree, recipe, resolved = _verify_worktree(worktree, recipe_path)
    cargo_root = worktree / recipe["cargo_subdir"]
    if not cargo_root.is_dir():
        raise CodexBuildError(f"Cargo source directory is missing: {cargo_root}")

    target = target_dir.expanduser()
    if target.is_symlink():
        raise CodexBuildError(f"Cargo target directory must not be a symlink: {target}")
    target.mkdir(parents=True, exist_ok=True)
    target = target.resolve(strict=True)

    free = shutil.disk_usage(target).free
    minimum = int(min_free_gib * 1024**3)
    if free < minimum:
        raise CodexBuildError(
            f"insufficient build space: free={free} required={minimum}"
        )

    cargo = shutil.which("cargo")
    if cargo is None:
        raise CodexBuildError("cargo is not available in PATH")
    rustc = shutil.which("rustc")
    if rustc is None:
        raise CodexBuildError("rustc is not available in PATH")

    cargo_version = _run([cargo, "--version"]).stdout.strip()
    rustc_version = _run([rustc, "--version"]).stdout.strip()
    if cargo_version != recipe["expected_cargo"]:
        raise CodexBuildError(
            f"cargo identity mismatch: {cargo_version!r} != {recipe['expected_cargo']!r}"
        )
    if rustc_version != recipe["expected_rustc"]:
        raise CodexBuildError(
            f"rustc identity mismatch: {rustc_version!r} != {recipe['expected_rustc']!r}"
        )

    lockfile = cargo_root / "Cargo.lock"
    if not lockfile.is_file() or lockfile.is_symlink():
        raise CodexBuildError(f"Cargo.lock is missing/unsafe: {lockfile}")
    lock_before = lockfile.read_bytes()

    try:
        _run([
            cargo,
            "build",
            "--release",
            "-p",
            recipe["cargo_package"],
            "--target-dir",
            str(target),
        ], cwd=cargo_root)

        status_after_build = _git(
            worktree, "status", "--porcelain=v2", "--untracked-files=all"
        )
        lock_refresh_packages = 0
        if status_after_build:
            changed = _git(worktree, "diff", "--name-only").splitlines()
            untracked = _git(worktree, "ls-files", "--others", "--exclude-standard").splitlines()
            if changed != [f"{recipe['cargo_subdir']}/Cargo.lock"] or untracked:
                raise CodexBuildError(
                    "Codex source worktree changed unexpectedly during release build: "
                    f"tracked={changed} untracked={untracked}"
                )
            lock_after = lockfile.read_bytes()
            lock_refresh_packages = _release_lock_refresh_only(
                lock_before,
                lock_after,
                _workspace_release_version(recipe),
            )

        binary = target / "release" / "codex"
        verified = _verify_candidate(binary, recipe)
    finally:
        if lockfile.exists() and lockfile.read_bytes() != lock_before:
            lockfile.write_bytes(lock_before)

    if _git(worktree, "status", "--porcelain=v2", "--untracked-files=all"):
        raise CodexBuildError("Codex source worktree is not clean after lock restoration")

    return {
        "schema": "atlas-codex-build/1",
        "recipe": recipe["name"],
        "worktree": str(worktree),
        "head": resolved["final_sha"],
        "target_dir": str(target),
        "free_bytes_before_build": free,
        "cargo_path": cargo,
        "cargo_version": cargo_version,
        "rustc_path": rustc,
        "rustc_version": rustc_version,
        "cargo_lock_release_version_refresh_packages": lock_refresh_packages,
        **verified,
        "status": "PASS",
    }
