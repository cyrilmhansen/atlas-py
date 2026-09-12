"""Read-only Atlas Agent release qualification helpers.

This module deliberately separates qualification from promotion.  The
``preflight`` command proves that the current candidate controller, qualified
Codex runtime, policy, assets, and a small model matrix agree.  The
``post-cutover`` command verifies the live operator binding after promotion.

Neither command mutates Git, Atlas workflow state, shell startup files, or
release directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
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
    print(f"root: {report['root']}")
    if report.get("schema") == "atlas-release-controller-promotion/1":
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
