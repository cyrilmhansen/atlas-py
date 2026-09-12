"""Read-only Atlas Agent release qualification helpers.

This module deliberately separates qualification from promotion.  The
``preflight`` command proves that the current candidate controller, qualified
Codex runtime, policy, assets, and a small model matrix agree.  The
``post-cutover`` command verifies the live operator binding after promotion.

`preflight` and `post-cutover` are read-only. `prepare-runtime` installs one
new immutable runtime and updates only the policy runtime digest.
`promote-controller` advances only the guarded repository boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import tarfile
from pathlib import PurePosixPath
from typing import Iterable

MODEL_SMOKES = (
    ("luna-high", "gpt-5.6-luna", "high", "ATLAS_SMOKE_LUNA_HIGH_OK"),
    ("sol-medium", "gpt-5.6-sol", "medium", "ATLAS_SMOKE_SOL_MEDIUM_OK"),
    ("astra-medium", "gpt-6-astra", "medium", "ATLAS_SMOKE_ASTRA_MEDIUM_OK"),
)


class ReleaseCheckError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(argv: list[str], *, cwd: Path | None = None,
         env: dict[str, str] | None = None, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseCheckError(f"command failed to start/finish: {argv[0]}: {error}") from error
    if result.returncode != 0:
        tail = (result.stdout + "\n" + result.stderr)[-4000:].strip()
        raise ReleaseCheckError(
            f"command failed ({result.returncode}): {' '.join(argv)}"
            + (f"\n{tail}" if tail else "")
        )
    return result


def _git(root: Path, *args: str) -> str:
    return _run(["git", *args], cwd=root).stdout.strip()


def _repository_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    root = _run(["git", "rev-parse", "--show-toplevel"], cwd=start).stdout.strip()
    return Path(root).resolve(strict=True)


def _load_policy(root: Path) -> dict:
    path = root / "atlas-agent-policy.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ReleaseCheckError(f"cannot read Atlas policy: {error}") from error


def _codex_profiles(policy: dict) -> list[dict]:
    try:
        profiles = policy["profiles"]
    except (KeyError, TypeError) as error:
        raise ReleaseCheckError("Atlas policy has no profiles table") from error
    rows = []
    for name, profile in profiles.items():
        if isinstance(profile, dict) and profile.get("executor") == "codex":
            rows.append({"name": name, **profile})
    if not rows:
        raise ReleaseCheckError("Atlas policy contains no Codex profile")
    return rows


def _require_single(values: Iterable[str], label: str) -> str:
    distinct = sorted(set(values))
    if len(distinct) != 1:
        raise ReleaseCheckError(f"{label} is not uniform: {distinct}")
    return distinct[0]


def _runtime_from_environment() -> tuple[Path, Path]:
    executable = os.environ.get("ATLAS_CODEX_EXECUTABLE")
    codex_home = os.environ.get("ATLAS_CODEX_HOME")
    if not executable:
        raise ReleaseCheckError("ATLAS_CODEX_EXECUTABLE is not set")
    if not codex_home:
        raise ReleaseCheckError("ATLAS_CODEX_HOME is not set")
    try:
        runtime = Path(executable).expanduser().resolve(strict=True)
        home = Path(codex_home).expanduser().resolve(strict=True)
    except OSError as error:
        raise ReleaseCheckError(f"runtime/home path cannot be resolved: {error}") from error
    if runtime.name != "codex":
        raise ReleaseCheckError(f"Codex runtime basename must be 'codex': {runtime}")
    if not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise ReleaseCheckError(f"Codex runtime is not an executable regular file: {runtime}")
    if not home.is_dir():
        raise ReleaseCheckError(f"ATLAS_CODEX_HOME is not a directory: {home}")
    return runtime, home


def _latest_agent_message(stdout: str) -> str | None:
    latest = None
    for raw in stdout.splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            latest = text.strip()
    return latest


def _check_assets(home: Path, profiles: list[dict]) -> dict[str, str]:
    checks: dict[str, str] = {}

    expected_config = _require_single(
        (p["codex_config_sha256"] for p in profiles),
        "policy codex_config_sha256",
    )
    expected_catalog = _require_single(
        (p["codex_catalog_sha256"] for p in profiles),
        "policy codex_catalog_sha256",
    )

    config = home / "config.toml"
    catalog = home / "models-atlas-shell-only.json"
    if not config.is_file() or config.is_symlink():
        raise ReleaseCheckError(f"qualified config is missing/unsafe: {config}")
    if not catalog.is_file() or catalog.is_symlink():
        raise ReleaseCheckError(f"qualified catalog is missing/unsafe: {catalog}")

    observed_config = _sha256(config)
    observed_catalog = _sha256(catalog)
    if observed_config != expected_config:
        raise ReleaseCheckError(
            f"Codex config digest mismatch: policy={expected_config} observed={observed_config}"
        )
    if observed_catalog != expected_catalog:
        raise ReleaseCheckError(
            f"Codex catalog digest mismatch: policy={expected_catalog} observed={observed_catalog}"
        )
    checks["config_sha256"] = observed_config
    checks["catalog_sha256"] = observed_catalog

    for profile in profiles:
        for side in ("local", "web"):
            profile_name = profile[f"codex_profile_{side}"]
            expected = profile[f"codex_profile_{side}_sha256"]
            path = home / f"{profile_name}.config.toml"
            if not path.is_file() or path.is_symlink():
                raise ReleaseCheckError(f"qualified profile is missing/unsafe: {path}")
            observed = _sha256(path)
            if observed != expected:
                raise ReleaseCheckError(
                    f"Codex profile digest mismatch ({profile_name}): "
                    f"policy={expected} observed={observed}"
                )
            checks[f"profile:{profile_name}"] = observed
    return checks


def _check_native_resolver(runtime: Path) -> None:
    try:
        from .bubblewrap import _native_codex
    except ImportError as error:
        raise ReleaseCheckError(f"cannot import Atlas native-runtime resolver: {error}") from error
    resolved = _native_codex(str(runtime))
    if resolved is None or Path(resolved).resolve() != runtime:
        raise ReleaseCheckError(
            f"Atlas native-runtime resolver rejected/misresolved {runtime}: {resolved}"
        )


def _model_smoke(runtime: Path, home: Path, *, timeout: float) -> list[dict]:
    env = dict(os.environ)
    env["CODEX_HOME"] = str(home)
    results = []

    with tempfile.TemporaryDirectory(prefix="atlas-release-smoke-") as temp:
        cwd = Path(temp)
        for label, model, effort, marker in MODEL_SMOKES:
            prompt = (
                "Do not call any tool. Do not inspect files. "
                f"Reply with exactly this text and nothing else: {marker}"
            )
            argv = [
                str(runtime),
                "exec",
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--strict-config",
                "--ignore-rules",
                "--model",
                model,
                "-c",
                f'model_reasoning_effort="{effort}"',
                "-c",
                'approval_policy="never"',
                "-c",
                'approvals_reviewer="user"',
                prompt,
            ]
            try:
                result = subprocess.run(
                    argv,
                    cwd=cwd,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ReleaseCheckError(f"{label} smoke failed to run: {error}") from error

            final = _latest_agent_message(result.stdout)
            if result.returncode != 0 or final != marker:
                diagnostic = (result.stdout + "\n" + result.stderr)[-4000:].strip()
                raise ReleaseCheckError(
                    f"{label} smoke failed: exit={result.returncode} "
                    f"final={final!r} expected={marker!r}"
                    + (f"\n{diagnostic}" if diagnostic else "")
                )
            results.append(
                {"label": label, "model": model, "reasoning": effort, "status": "PASS"}
            )
    return results


def preflight(*, root: Path | None = None, model_smoke: bool = True,
              timeout: float = 180.0) -> dict:
    root = _repository_root(root)
    status = _git(root, "status", "--porcelain=v2", "--untracked-files=all")
    if status:
        raise ReleaseCheckError("candidate repository is not clean")

    branch = _git(root, "branch", "--show-current")
    if not branch:
        raise ReleaseCheckError("candidate repository is detached")
    head = _git(root, "rev-parse", "HEAD")

    runtime, home = _runtime_from_environment()
    runtime_digest = _sha256(runtime)
    version = _run([str(runtime), "--version"]).stdout.strip()

    policy = _load_policy(root)
    profiles = _codex_profiles(policy)
    expected_runtime = _require_single(
        (p["codex_binary_sha256"] for p in profiles),
        "policy codex_binary_sha256",
    )
    if runtime_digest != expected_runtime:
        raise ReleaseCheckError(
            f"runtime/policy digest mismatch: policy={expected_runtime} "
            f"runtime={runtime_digest}"
        )

    assets = _check_assets(home, profiles)
    _check_native_resolver(runtime)

    repo_free = shutil.disk_usage(root).free
    tmp_free = shutil.disk_usage(Path(tempfile.gettempdir())).free

    report = {
        "schema": "atlas-release-preflight/1",
        "root": str(root),
        "branch": branch,
        "head": head,
        "repository_clean": True,
        "runtime": str(runtime),
        "runtime_version": version,
        "runtime_sha256": runtime_digest,
        "policy_runtime_sha256": expected_runtime,
        "codex_home": str(home),
        "assets": assets,
        "native_runtime_resolution": "PASS",
        "free_bytes": {"repository_fs": repo_free, "tmp_fs": tmp_free},
        "model_smokes": [],
    }
    if model_smoke:
        report["model_smokes"] = _model_smoke(runtime, home, timeout=timeout)
    return report



def _atomic_write(path: Path, data: bytes) -> None:
    mode = path.stat().st_mode & 0o777
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, mode)
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def _candidate_runtime(path: Path) -> tuple[Path, str, str]:
    source = path.expanduser()
    if source.is_symlink():
        raise ReleaseCheckError(f"candidate runtime must not be a symlink: {source}")
    try:
        candidate = source.resolve(strict=True)
    except OSError as error:
        raise ReleaseCheckError(f"candidate runtime cannot be resolved: {error}") from error
    if not candidate.is_file():
        raise ReleaseCheckError(f"candidate runtime is not a regular file: {candidate}")
    if not os.access(candidate, os.X_OK):
        raise ReleaseCheckError(f"candidate runtime is not executable: {candidate}")
    try:
        with candidate.open("rb") as stream:
            magic = stream.read(4)
    except OSError as error:
        raise ReleaseCheckError(f"candidate runtime cannot be read: {error}") from error
    if magic != b"\x7fELF":
        raise ReleaseCheckError("candidate runtime is not an ELF executable")
    digest = _sha256(candidate)
    version = _run([str(candidate), "--version"]).stdout.strip()
    return candidate, digest, version


def prepare_runtime(*, candidate: Path, release_id: str,
                    root: Path | None = None,
                    releases_dir: Path | None = None) -> dict:
    root = _repository_root(root)
    status = _git(root, "status", "--porcelain=v2", "--untracked-files=all")
    if status:
        raise ReleaseCheckError("candidate repository is not clean")

    if not isinstance(release_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release_id
    ):
        raise ReleaseCheckError("invalid release id")

    current_runtime, _ = _runtime_from_environment()
    candidate, new_digest, version = _candidate_runtime(candidate)

    policy_path = root / "atlas-agent-policy.toml"
    policy = _load_policy(root)
    profiles = _codex_profiles(policy)
    old_digest = _require_single(
        (p["codex_binary_sha256"] for p in profiles),
        "policy codex_binary_sha256",
    )

    if releases_dir is None:
        if current_runtime.parent.parent.name != "releases":
            raise ReleaseCheckError(
                "cannot infer releases directory from ATLAS_CODEX_EXECUTABLE; "
                "pass --releases-dir"
            )
        release_root = current_runtime.parent.parent
    else:
        try:
            release_root = releases_dir.expanduser().resolve(strict=True)
        except OSError as error:
            raise ReleaseCheckError(f"releases directory cannot be resolved: {error}") from error

    if not release_root.is_dir() or release_root.is_symlink():
        raise ReleaseCheckError(f"unsafe releases directory: {release_root}")

    release_dir = release_root / release_id
    target = release_dir / "codex"
    if release_dir.exists() or release_dir.is_symlink():
        raise ReleaseCheckError(f"release already exists: {release_dir}")

    raw = policy_path.read_text(encoding="utf-8")
    needle = f'codex_binary_sha256 = "{old_digest}"'
    replacement = f'codex_binary_sha256 = "{new_digest}"'
    count = raw.count(needle)
    if count != len(profiles):
        raise ReleaseCheckError(
            f"policy runtime digest occurrence mismatch: "
            f"expected={len(profiles)} observed={count}"
        )

    updated_raw = raw.replace(needle, replacement)

    try:
        updated_policy = tomllib.loads(updated_raw)
    except tomllib.TOMLDecodeError as error:
        raise ReleaseCheckError(f"updated policy is invalid TOML: {error}") from error

    expected_policy = json.loads(json.dumps(policy))
    for profile in expected_policy["profiles"].values():
        if isinstance(profile, dict) and profile.get("executor") == "codex":
            profile["codex_binary_sha256"] = new_digest

    if updated_policy != expected_policy:
        raise ReleaseCheckError("policy update would modify fields other than runtime digest")

    try:
        release_dir.mkdir(mode=0o755)
        staged = release_dir / ".codex.staging"
        shutil.copyfile(candidate, staged, follow_symlinks=False)
        os.chmod(staged, 0o755)

        with staged.open("rb") as stream:
            os.fsync(stream.fileno())

        if _sha256(staged) != new_digest:
            raise ReleaseCheckError("installed runtime staging digest mismatch")

        os.replace(staged, target)

        directory_fd = os.open(release_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

        _check_native_resolver(target)
        if _sha256(target) != new_digest:
            raise ReleaseCheckError("installed runtime digest mismatch")

        _atomic_write(policy_path, updated_raw.encode("utf-8"))

        observed = _load_policy(root)
        observed_profiles = _codex_profiles(observed)
        observed_digest = _require_single(
            (p["codex_binary_sha256"] for p in observed_profiles),
            "updated policy codex_binary_sha256",
        )
        if observed_digest != new_digest:
            raise ReleaseCheckError("updated policy did not retain candidate runtime digest")

    except BaseException:
        try:
            if release_dir.exists() and not release_dir.is_symlink():
                shutil.rmtree(release_dir)
        except OSError:
            pass
        raise

    return {
        "schema": "atlas-release-runtime-preparation/1",
        "root": str(root),
        "candidate": str(candidate),
        "release_id": release_id,
        "previous_runtime": str(current_runtime),
        "previous_runtime_sha256": old_digest,
        "runtime": str(target),
        "runtime_version": version,
        "runtime_sha256": new_digest,
        "policy_profiles_updated": len(profiles),
    }



MANAGED_LAUNCHER_MARKER = "# atlas-agent-managed-launcher-v1"


def _default_data_root() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local/share") / "atlas-agent"


def _snapshot_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ReleaseCheckError(f"controller snapshot contains symlink: {rel}")
        if path.is_dir():
            digest.update(b"D\0" + rel.encode("utf-8") + b"\0")
            continue
        if not path.is_file():
            raise ReleaseCheckError(f"controller snapshot contains unsupported entry: {rel}")
        digest.update(b"F\0" + rel.encode("utf-8") + b"\0")
        digest.update(_sha256(path).encode("ascii") + b"\0")
    return digest.hexdigest()


def _extract_head(root: Path, destination: Path) -> None:
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                rel = PurePosixPath(member.name)
                if (
                    rel.is_absolute()
                    or not rel.parts
                    or any(part in {"", ".", ".."} for part in rel.parts)
                ):
                    raise ReleaseCheckError(f"unsafe git archive path: {member.name!r}")
                target = destination.joinpath(*rel.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ReleaseCheckError(
                        f"controller archive contains unsupported entry: {member.name}"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ReleaseCheckError(f"cannot read archived file: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                mode = 0o555 if member.mode & 0o111 else 0o444
                os.chmod(target, mode)
    finally:
        process.stdout.close()
    stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    returncode = process.wait()
    if returncode != 0:
        raise ReleaseCheckError(f"git archive failed ({returncode}): {stderr[-2000:]}")
    for directory in sorted(
        (path for path in destination.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        os.chmod(directory, 0o555)
    os.chmod(destination, 0o555)


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseCheckError(f"{label} is unreadable: {error}") from error
    if not isinstance(value, dict):
        raise ReleaseCheckError(f"{label} must be a JSON object")
    return value


def _write_new_json(path: Path, value: dict, mode: int = 0o444) -> None:
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_replace_bytes(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, mode)
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def _verify_controller_release(release_dir: Path) -> dict:
    if release_dir.is_symlink() or not release_dir.is_dir():
        raise ReleaseCheckError(f"controller release is missing/unsafe: {release_dir}")
    manifest = _read_json(release_dir / "release.json", "controller release manifest")
    if manifest.get("schema") != "atlas-controller-release/1":
        raise ReleaseCheckError("unsupported controller release manifest schema")
    head = manifest.get("head")
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ReleaseCheckError("controller release manifest has invalid HEAD")
    src = release_dir / "src"
    if src.is_symlink() or not src.is_dir():
        raise ReleaseCheckError("controller release source is missing/unsafe")
    observed = _snapshot_digest(src)
    if observed != manifest.get("snapshot_sha256"):
        raise ReleaseCheckError(
            f"controller snapshot digest mismatch: "
            f"expected={manifest.get('snapshot_sha256')} observed={observed}"
        )
    runtime_raw = manifest.get("codex_executable")
    runtime_digest = manifest.get("codex_sha256")
    codex_home_raw = manifest.get("codex_home")
    if not all(isinstance(value, str) and value for value in (
        runtime_raw, runtime_digest, codex_home_raw
    )):
        raise ReleaseCheckError("controller release runtime authority is incomplete")
    runtime = Path(runtime_raw)
    if not runtime.is_file() or _sha256(runtime) != runtime_digest:
        raise ReleaseCheckError("controller release Codex runtime identity mismatch")
    codex_home = Path(codex_home_raw)
    if not codex_home.is_dir():
        raise ReleaseCheckError("controller release CODEX_HOME is missing")
    return manifest


def install_controller(*, root: Path | None = None,
                       controllers_dir: Path | None = None) -> dict:
    root = _repository_root(root)
    pre = preflight(root=root, model_smoke=False)

    head = pre["head"]
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    branch = pre["branch"]
    controllers = (
        controllers_dir.expanduser()
        if controllers_dir is not None
        else _default_data_root() / "controllers"
    )
    controllers.mkdir(parents=True, exist_ok=True)
    controllers = controllers.resolve(strict=True)
    if controllers.is_symlink():
        raise ReleaseCheckError(f"unsafe controllers directory: {controllers}")

    release_dir = controllers / head
    if release_dir.exists():
        manifest = _verify_controller_release(release_dir)
        if manifest.get("head") != head or manifest.get("tree") != tree:
            raise ReleaseCheckError("existing controller release identity mismatch")
        return {
            "schema": "atlas-controller-installation/1",
            "status": "ALREADY_INSTALLED",
            "head": head,
            "tree": tree,
            "release_dir": str(release_dir),
            "controller_src": str(release_dir / "src"),
            "snapshot_sha256": manifest["snapshot_sha256"],
        }

    temp_dir = Path(tempfile.mkdtemp(prefix=".controller-", dir=controllers))
    try:
        src = temp_dir / "src"
        src.mkdir()
        _extract_head(root, src)
        snapshot = _snapshot_digest(src)

        capability_raw = os.environ.get("ATLAS_AGENT_CAPABILITIES_FILE")
        capability = None
        if capability_raw:
            try:
                capability = str(Path(capability_raw).expanduser().resolve(strict=True))
            except OSError as error:
                raise ReleaseCheckError(
                    f"ATLAS_AGENT_CAPABILITIES_FILE cannot be resolved: {error}"
                ) from error

        manifest = {
            "schema": "atlas-controller-release/1",
            "head": head,
            "tree": tree,
            "branch": branch,
            "snapshot_sha256": snapshot,
            "source_repository": str(root),
            "codex_executable": pre["runtime"],
            "codex_sha256": pre["runtime_sha256"],
            "codex_home": pre["codex_home"],
            "capabilities_file": capability,
        }
        _write_new_json(temp_dir / "release.json", manifest)
        os.chmod(temp_dir / "release.json", 0o444)
        os.chmod(temp_dir, 0o555)
        os.replace(temp_dir, release_dir)
    except BaseException:
        try:
            if temp_dir.exists():
                for directory in sorted(
                    (path for path in temp_dir.rglob("*") if path.is_dir()),
                    key=lambda path: len(path.parts),
                    reverse=True,
                ):
                    os.chmod(directory, 0o755)
                os.chmod(temp_dir, 0o755)
                shutil.rmtree(temp_dir)
        except OSError:
            pass
        raise

    verified = _verify_controller_release(release_dir)
    return {
        "schema": "atlas-controller-installation/1",
        "status": "INSTALLED",
        "head": head,
        "tree": tree,
        "release_dir": str(release_dir),
        "controller_src": str(release_dir / "src"),
        "snapshot_sha256": verified["snapshot_sha256"],
    }


def _managed_launcher(state_path: Path) -> bytes:
    body = f'''#!/usr/bin/env python3
{MANAGED_LAUNCHER_MARKER}
import json
import os
from pathlib import Path
import sys

state_path = Path({str(state_path)!r})
state = json.loads(state_path.read_text(encoding="utf-8"))
environment = state.get("environment")
if not isinstance(environment, dict):
    raise SystemExit("Atlas active controller state is invalid")

env = dict(os.environ)
for key, value in environment.items():
    if isinstance(key, str) and isinstance(value, str):
        env[key] = value

agent_src = environment.get("ATLAS_AGENT_SRC")
if not isinstance(agent_src, str) or not agent_src:
    raise SystemExit("Atlas active controller has no ATLAS_AGENT_SRC")
env["PYTHONPATH"] = agent_src
env["PYTHONDONTWRITEBYTECODE"] = "1"

os.execvpe(
    sys.executable,
    [sys.executable, "-P", "-m", "tools.atlas_agent", *sys.argv[1:]],
    env,
)
'''
    return body.encode("utf-8")


def activate_controller(*, head: str, controllers_dir: Path | None = None,
                        state_path: Path | None = None,
                        launcher_path: Path | None = None) -> dict:
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ReleaseCheckError("activate-controller requires a full 40-hex HEAD")

    data_root = _default_data_root()
    controllers = (
        controllers_dir.expanduser()
        if controllers_dir is not None
        else data_root / "controllers"
    ).resolve(strict=True)
    release_dir = controllers / head
    manifest = _verify_controller_release(release_dir)

    current = data_root / "current-controller"
    state = state_path.expanduser() if state_path else data_root / "active-controller.json"
    launcher = launcher_path.expanduser() if launcher_path else Path.home() / ".local/bin/aa"

    # Validate every replace target before changing active authority.
    if current.exists() and not current.is_symlink():
        raise ReleaseCheckError(
            f"refusing to replace non-symlink current controller: {current}"
        )
    if launcher.exists():
        try:
            existing = launcher.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ReleaseCheckError(f"existing launcher is unreadable: {error}") from error
        if MANAGED_LAUNCHER_MARKER not in existing:
            raise ReleaseCheckError(
                f"refusing to replace unmanaged launcher: {launcher}"
            )

    current.parent.mkdir(parents=True, exist_ok=True)
    staged_link = current.parent / f".current-controller.{os.getpid()}"
    try:
        if staged_link.exists() or staged_link.is_symlink():
            staged_link.unlink()
        os.symlink(release_dir, staged_link, target_is_directory=True)
        os.replace(staged_link, current)
    finally:
        if staged_link.exists() or staged_link.is_symlink():
            staged_link.unlink()

    environment = {
        "ATLAS_AGENT_SRC": str(current / "src"),
        "ATLAS_CODEX_EXECUTABLE": manifest["codex_executable"],
        "ATLAS_CODEX_HOME": manifest["codex_home"],
    }
    capability = manifest.get("capabilities_file")
    if isinstance(capability, str) and capability:
        environment["ATLAS_AGENT_CAPABILITIES_FILE"] = capability

    state_value = {
        "schema": "atlas-active-controller/1",
        "head": head,
        "release_dir": str(release_dir),
        "snapshot_sha256": manifest["snapshot_sha256"],
        "current_controller": str(current),
        "environment": environment,
    }
    _atomic_replace_bytes(
        state,
        (json.dumps(state_value, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        0o600,
    )

    launcher.parent.mkdir(parents=True, exist_ok=True)
    _atomic_replace_bytes(launcher, _managed_launcher(state), 0o755)

    return {
        "schema": "atlas-controller-activation/1",
        "head": head,
        "release_dir": str(release_dir),
        "current_controller": str(current),
        "state_path": str(state),
        "launcher": str(launcher),
        "codex_executable": manifest["codex_executable"],
    }


def verify_installation(*, start: Path | None = None,
                        state_path: Path | None = None,
                        launcher_path: Path | None = None,
                        timeout: float = 60.0) -> dict:
    root = _repository_root(start)
    data_root = _default_data_root()
    state = state_path.expanduser() if state_path else data_root / "active-controller.json"
    launcher = launcher_path.expanduser() if launcher_path else Path.home() / ".local/bin/aa"

    active = _read_json(state, "active controller state")
    if active.get("schema") != "atlas-active-controller/1":
        raise ReleaseCheckError("unsupported active controller state schema")
    head = active.get("head")
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ReleaseCheckError("active controller state has invalid HEAD")
    release_dir = Path(active.get("release_dir", ""))
    manifest = _verify_controller_release(release_dir)
    if manifest["head"] != head:
        raise ReleaseCheckError("active controller HEAD does not match release manifest")

    current = Path(active.get("current_controller", ""))
    try:
        if current.resolve(strict=True) != release_dir.resolve(strict=True):
            raise ReleaseCheckError("current-controller symlink targets the wrong release")
    except OSError as error:
        raise ReleaseCheckError(f"current-controller cannot be resolved: {error}") from error

    environment = active.get("environment")
    if not isinstance(environment, dict):
        raise ReleaseCheckError("active controller environment is invalid")
    expected_src = str(current / "src")
    if environment.get("ATLAS_AGENT_SRC") != expected_src:
        raise ReleaseCheckError("active ATLAS_AGENT_SRC does not use current-controller/src")
    if environment.get("ATLAS_CODEX_EXECUTABLE") != manifest["codex_executable"]:
        raise ReleaseCheckError("active Codex runtime differs from release manifest")
    if environment.get("ATLAS_CODEX_HOME") != manifest["codex_home"]:
        raise ReleaseCheckError("active CODEX_HOME differs from release manifest")

    installed_policy = _load_policy(current / "src")
    profiles = _codex_profiles(installed_policy)
    policy_runtime = _require_single(
        (p["codex_binary_sha256"] for p in profiles),
        "installed controller policy runtime digest",
    )
    if policy_runtime != manifest["codex_sha256"]:
        raise ReleaseCheckError("installed controller policy/runtime authority mismatch")

    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise ReleaseCheckError(f"managed aa launcher is missing/not executable: {launcher}")
    if MANAGED_LAUNCHER_MARKER not in launcher.read_text(encoding="utf-8"):
        raise ReleaseCheckError("aa launcher is not Atlas-managed")

    status = _run(
        [str(launcher), "status", "--history", "0"],
        cwd=root,
        timeout=timeout,
    ).stdout
    for expected in ("journal: OK", "state: MATCH", "repository witness: MATCH"):
        if expected not in status:
            raise ReleaseCheckError(
                f"installed-controller status missing {expected!r}\n{status}"
            )

    doctor = _run([str(launcher), "doctor"], cwd=root, timeout=timeout).stdout
    if "doctor: OK" not in doctor:
        raise ReleaseCheckError(f"installed-controller doctor failed\n{doctor}")

    return {
        "schema": "atlas-controller-installation-verification/1",
        "head": head,
        "release_dir": str(release_dir),
        "launcher": str(launcher),
        "runtime": manifest["codex_executable"],
        "status": "PASS",
        "doctor": "PASS",
    }


def post_cutover(*, root: Path | None = None, timeout: float = 60.0) -> dict:
    root = _repository_root(root)
    source_raw = os.environ.get("ATLAS_AGENT_SRC")
    if not source_raw:
        raise ReleaseCheckError("ATLAS_AGENT_SRC is not set")
    try:
        source = Path(source_raw).expanduser().resolve(strict=True)
    except OSError as error:
        raise ReleaseCheckError(f"ATLAS_AGENT_SRC cannot be resolved: {error}") from error
    if source != root:
        raise ReleaseCheckError(
            f"controller cutover mismatch: ATLAS_AGENT_SRC={source} candidate={root}"
        )

    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)

    status = _run(
        [
            sys.executable, "-P", "-m", "tools.atlas_agent",
            "status", "--history", "0",
        ],
        cwd=root,
        env=env,
        timeout=timeout,
    ).stdout
    required_status = ("journal: OK", "state: MATCH", "repository witness: MATCH")
    missing = [line for line in required_status if line not in status]
    if missing:
        raise ReleaseCheckError(f"post-cutover status failed; missing {missing}\n{status}")

    doctor = _run(
        [sys.executable, "-P", "-m", "tools.atlas_agent", "doctor"],
        cwd=root,
        env=env,
        timeout=timeout,
    ).stdout
    if "doctor: OK" not in doctor:
        raise ReleaseCheckError(f"post-cutover doctor failed\n{doctor}")

    runtime, _ = _runtime_from_environment()
    _check_native_resolver(runtime)

    return {
        "schema": "atlas-release-post-cutover/1",
        "root": str(root),
        "controller": str(source),
        "runtime": str(runtime),
        "status": "PASS",
        "doctor": "PASS",
        "native_runtime_resolution": "PASS",
    }



def promote_controller(*, root: Path | None = None, reason: str,
                       timeout: float = 60.0) -> dict:
    # Adopt the current clean candidate HEAD and verify the live cutover.
    if not isinstance(reason, str) or not reason.strip():
        raise ReleaseCheckError("promotion reason is required")

    root = _repository_root(root)

    # Cheap release invariants immediately before mutating workflow authority.
    preflight(root=root, model_smoke=False, timeout=timeout)

    source_raw = os.environ.get("ATLAS_AGENT_SRC")
    if not source_raw:
        raise ReleaseCheckError("ATLAS_AGENT_SRC is not set")
    try:
        source = Path(source_raw).expanduser().resolve(strict=True)
    except OSError as error:
        raise ReleaseCheckError(f"ATLAS_AGENT_SRC cannot be resolved: {error}") from error
    if source != root:
        raise ReleaseCheckError(
            f"controller cutover mismatch: ATLAS_AGENT_SRC={source} candidate={root}"
        )

    try:
        from .workflow import Workflow
    except ImportError as error:
        raise ReleaseCheckError(f"cannot import Atlas workflow: {error}") from error

    workflow = Workflow(root)
    try:
        _, state = workflow._preflight(require_state=True)
    except Exception as error:
        raise ReleaseCheckError(f"Atlas workflow preflight failed: {error}") from error

    previous = state.get("latest_repository_witness")
    if not isinstance(previous, dict) or not isinstance(previous.get("head"), str):
        raise ReleaseCheckError("latest repository witness has no valid HEAD")

    old_head = previous["head"]
    new_head = _git(root, "rev-parse", "HEAD")

    if old_head == new_head:
        adoption = "ALREADY_MATCHED"
    else:
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", old_head, new_head],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if ancestry.returncode != 0:
            raise ReleaseCheckError(
                f"candidate HEAD is not a descendant of journal boundary: "
                f"{old_head} -> {new_head}"
            )
        try:
            workflow.adopt_boundary(old_head, new_head, reason.strip())
        except Exception as error:
            raise ReleaseCheckError(f"repository boundary adoption failed: {error}") from error
        adoption = "ADOPTED"

    post = post_cutover(root=root, timeout=timeout)
    return {
        "schema": "atlas-release-controller-promotion/1",
        "root": str(root),
        "previous_head": old_head,
        "current_head": new_head,
        "boundary": adoption,
        "post_cutover": post,
    }

def _print_report(report: dict) -> None:
    if "root" in report:
        print(f"root: {report['root']}")
    if report.get("schema") == "atlas-codex-reconstruction/1":
        print(f"recipe: {report['recipe']}")
        print(f"upstream: {report['upstream_tag']} {report['upstream_commit']}")
        print(f"head: {report['final_sha']}")
        print(f"worktree: {report['worktree']}")
        print("ATLAS CODEX RECONSTRUCTION: PASS")
    elif report.get("schema") == "atlas-codex-build/1":
        print(f"recipe: {report['recipe']}")
        print(f"head: {report['head']}")
        print(f"binary: {report['binary']}")
        print(f"version: {report['version']}")
        print(f"sha256: {report['sha256']}")
        print("exec help contract: PASS")
        print("ATLAS CODEX BUILD: PASS")
    elif report.get("schema") == "atlas-controller-installation/1":
        print(f"head: {report['head']}")
        print(f"controller: {report['controller_src']}")
        print(f"snapshot sha256: {report['snapshot_sha256']}")
        print(f"installation: {report['status']}")
        print("ATLAS CONTROLLER INSTALLATION: PASS")
    elif report.get("schema") == "atlas-controller-activation/1":
        print(f"head: {report['head']}")
        print(f"current controller: {report['current_controller']}")
        print(f"launcher: {report['launcher']}")
        print(f"runtime: {report['codex_executable']}")
        print("ATLAS CONTROLLER ACTIVATION: PASS")
    elif report.get("schema") == "atlas-controller-installation-verification/1":
        print(f"head: {report['head']}")
        print(f"launcher: {report['launcher']}")
        print(f"runtime: {report['runtime']}")
        print("status: PASS")
        print("doctor: PASS")
        print("ATLAS CONTROLLER INSTALLATION VERIFY: PASS")
    elif report.get("schema") == "atlas-release-runtime-preparation/1":
        print(f"candidate: {report['candidate']}")
        print(f"release id: {report['release_id']}")
        print(f"previous runtime: {report['previous_runtime']}")
        print(f"runtime: {report['runtime']}")
        print(f"runtime version: {report['runtime_version']}")
        print(f"runtime sha256: {report['runtime_sha256']}")
        print(f"policy profiles updated: {report['policy_profiles_updated']}")
        print(f'export ATLAS_CODEX_EXECUTABLE="{report["runtime"]}"')
        print("ATLAS RELEASE RUNTIME PREPARATION: PASS")
    elif report.get("schema") == "atlas-release-controller-promotion/1":
        print(f"previous head: {report['previous_head']}")
        print(f"current head: {report['current_head']}")
        print(f"repository boundary: {report['boundary']}")
        print("post-cutover: PASS")
        print("ATLAS RELEASE CONTROLLER PROMOTION: PASS")
    elif "branch" in report:
        print(f"branch: {report['branch']}")
        print(f"head: {report['head']}")
        print("repository: CLEAN")
        print(f"runtime: {report['runtime']}")
        print(f"runtime version: {report['runtime_version']}")
        print(f"runtime sha256: {report['runtime_sha256']}")
        print("policy/runtime: MATCH")
        print("qualified assets: MATCH")
        print("native runtime resolution: PASS")
        gib = 1024 ** 3
        print(
            "free space: "
            f"repo-fs={report['free_bytes']['repository_fs'] / gib:.1f} GiB "
            f"tmp-fs={report['free_bytes']['tmp_fs'] / gib:.1f} GiB"
        )
        for smoke in report["model_smokes"]:
            print(
                f"{smoke['label']}: {smoke['status']} "
                f"({smoke['model']} {smoke['reasoning']})"
            )
        print("ATLAS RELEASE PREFLIGHT: PASS")
    else:
        print(f"controller: {report['controller']}")
        print(f"runtime: {report['runtime']}")
        print("status: PASS")
        print("doctor: PASS")
        print("native runtime resolution: PASS")
        print("ATLAS RELEASE POST-CUTOVER: PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.atlas_agent.release")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--skip-model-smoke", action="store_true")
    p_pre.add_argument("--timeout", type=float, default=180.0)
    p_pre.add_argument("--json", action="store_true")

    p_runtime = sub.add_parser("prepare-runtime")
    p_runtime.add_argument("--candidate", type=Path, required=True)
    p_runtime.add_argument("--release-id", required=True)
    p_runtime.add_argument("--releases-dir", type=Path)
    p_runtime.add_argument("--json", action="store_true")

    p_reconstruct = sub.add_parser("reconstruct-codex")
    p_reconstruct.add_argument("--source-repo", type=Path, required=True)
    p_reconstruct.add_argument("--worktree", type=Path, required=True)
    p_reconstruct.add_argument("--recipe", type=Path)
    p_reconstruct.add_argument("--json", action="store_true")

    p_build = sub.add_parser("build-codex")
    p_build.add_argument("--worktree", type=Path, required=True)
    p_build.add_argument("--target-dir", type=Path, required=True)
    p_build.add_argument("--recipe", type=Path)
    p_build.add_argument("--min-free-gib", type=float, default=30.0)
    p_build.add_argument("--json", action="store_true")

    p_install = sub.add_parser("install-controller")
    p_install.add_argument("--controllers-dir", type=Path)
    p_install.add_argument("--json", action="store_true")

    p_activate = sub.add_parser("activate-controller")
    p_activate.add_argument("--head", required=True)
    p_activate.add_argument("--controllers-dir", type=Path)
    p_activate.add_argument("--state", type=Path)
    p_activate.add_argument("--launcher", type=Path)
    p_activate.add_argument("--json", action="store_true")

    p_verify = sub.add_parser("verify-installation")
    p_verify.add_argument("--state", type=Path)
    p_verify.add_argument("--launcher", type=Path)
    p_verify.add_argument("--timeout", type=float, default=60.0)
    p_verify.add_argument("--json", action="store_true")

    p_post = sub.add_parser("post-cutover")
    p_post.add_argument("--timeout", type=float, default=60.0)
    p_post.add_argument("--json", action="store_true")

    p_promote = sub.add_parser("promote-controller")
    p_promote.add_argument("--reason", required=True)
    p_promote.add_argument("--timeout", type=float, default=60.0)
    p_promote.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            report = preflight(
                model_smoke=not args.skip_model_smoke,
                timeout=args.timeout,
            )
        elif args.command == "prepare-runtime":
            report = prepare_runtime(
                candidate=args.candidate,
                release_id=args.release_id,
                releases_dir=args.releases_dir,
            )
        elif args.command == "reconstruct-codex":
            from .codex_release import reconstruct_source
            root = _repository_root()
            recipe = args.recipe or root / "codex-runtime-recipes" / "atlas-codex-0.154.toml"
            report = reconstruct_source(
                source_repo=args.source_repo,
                worktree=args.worktree,
                recipe_path=recipe,
            )
        elif args.command == "build-codex":
            from .codex_release import build_runtime
            root = _repository_root()
            recipe = args.recipe or root / "codex-runtime-recipes" / "atlas-codex-0.154.toml"
            report = build_runtime(
                worktree=args.worktree,
                recipe_path=recipe,
                target_dir=args.target_dir,
                min_free_gib=args.min_free_gib,
            )
        elif args.command == "install-controller":
            report = install_controller(
                controllers_dir=args.controllers_dir,
            )
        elif args.command == "activate-controller":
            report = activate_controller(
                head=args.head,
                controllers_dir=args.controllers_dir,
                state_path=args.state,
                launcher_path=args.launcher,
            )
        elif args.command == "verify-installation":
            report = verify_installation(
                state_path=args.state,
                launcher_path=args.launcher,
                timeout=args.timeout,
            )
        elif args.command == "post-cutover":
            report = post_cutover(timeout=args.timeout)
        else:
            report = promote_controller(
                reason=args.reason,
                timeout=args.timeout,
            )
    except ReleaseCheckError as error:
        print(f"ATLAS RELEASE CHECK: FAIL: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
