import os
from pathlib import Path
import subprocess

import pytest

from tools.atlas_agent.codex_release import (
    CodexBuildError,
    build_runtime,
    load_recipe,
    reconstruct_source,
)


def _git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
    ).strip()


def _commit(repo, message, content):
    path = repo / "file.txt"
    path.write_text(content, encoding="utf-8")
    subprocess.check_call(["git", "-C", str(repo), "add", "file.txt"])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-qm", message])
    return _git(repo, "rev-parse", "HEAD")


def _recipe(path, upstream, required, final):
    path.write_text(
        'schema = "atlas-codex-build-recipe/1"\n'
        'name = "test"\n'
        'upstream_tag = "rust-v0.test"\n'
        f'upstream_commit = "{upstream}"\n'
        'required_commits = [' + ", ".join(f'"{item}"' for item in required) + ']\n'
        f'final_ref = "{final}"\n'
        'cargo_subdir = "codex-rs"\n'
        'cargo_package = "codex-cli"\n'
        'expected_version = "codex-cli test"\n'
        'required_exec_help = ["--image-detail", "original"]\n',
        encoding="utf-8",
    )


def test_recipe_rejects_extra_key(tmp_path):
    path = tmp_path / "recipe.toml"
    path.write_text(
        'schema = "atlas-codex-build-recipe/1"\n'
        'name = "x"\n'
        'upstream_tag = "x"\n'
        'upstream_commit = "' + "a" * 40 + '"\n'
        'required_commits = ["abcdef0"]\n'
        'final_ref = "abcdef0"\n'
        'cargo_subdir = "codex-rs"\n'
        'cargo_package = "codex-cli"\n'
        'expected_version = "x"\n'
        'required_exec_help = ["x"]\n'
        'unexpected = true\n',
        encoding="utf-8",
    )
    with pytest.raises(CodexBuildError, match="unexpected keys"):
        load_recipe(path)


def test_reconstruct_source_uses_exact_qualified_head(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@e"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)

    upstream = _commit(repo, "upstream", "upstream")
    subprocess.check_call(["git", "-C", str(repo), "tag", "rust-v0.test", upstream])
    patch1 = _commit(repo, "patch1", "patch1")
    final = _commit(repo, "patch2", "patch2")

    recipe = tmp_path / "recipe.toml"
    _recipe(recipe, upstream, [patch1, final], final)

    worktree = tmp_path / "reconstructed"
    result = reconstruct_source(
        source_repo=repo,
        worktree=worktree,
        recipe_path=recipe,
    )

    assert result["final_sha"] == final
    assert _git(worktree, "rev-parse", "HEAD") == final
    assert _git(worktree, "status", "--porcelain=v2", "--untracked-files=all") == ""


def test_reconstruct_rejects_tag_mismatch(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@e"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)

    upstream = _commit(repo, "upstream", "upstream")
    patch1 = _commit(repo, "patch1", "patch1")
    final = _commit(repo, "patch2", "patch2")
    subprocess.check_call(["git", "-C", str(repo), "tag", "rust-v0.test", patch1])

    recipe = tmp_path / "recipe.toml"
    _recipe(recipe, upstream, [patch1, final], final)

    with pytest.raises(CodexBuildError, match="upstream tag mismatch"):
        reconstruct_source(
            source_repo=repo,
            worktree=tmp_path / "reconstructed",
            recipe_path=recipe,
        )


def test_build_runtime_invokes_cargo_on_clean_qualified_worktree(tmp_path, monkeypatch):
    import tools.atlas_agent.codex_release as codex_release

    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@e"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)
    (repo / "codex-rs").mkdir()
    (repo / "codex-rs" / "Cargo.lock").write_text(
        'version = 4\n\n'
        '[[package]]\n'
        'name = "fixture"\n'
        'version = "1.0.0"\n',
        encoding="utf-8",
    )
    (repo / "file.txt").write_text("upstream", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(repo), "add", "."])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-qm", "upstream"])
    upstream = _git(repo, "rev-parse", "HEAD")
    subprocess.check_call(["git", "-C", str(repo), "tag", "rust-v0.test", upstream])
    patch1 = _commit(repo, "patch1", "patch1")
    final = _commit(repo, "patch2", "patch2")

    recipe = tmp_path / "recipe.toml"
    _recipe(recipe, upstream, [patch1, final], final)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    cargo = fake_bin / "cargo"
    cargo.write_text(
        "#!/bin/sh\n"
        "target=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = '--target-dir' ]; then shift; target=\"$1\"; fi\n"
        "  shift\n"
        "done\n"
        "mkdir -p \"$target/release\"\n"
        "printf fake > \"$target/release/codex\"\n"
        "chmod +x \"$target/release/codex\"\n",
        encoding="utf-8",
    )
    cargo.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(
        codex_release,
        "_verify_candidate",
        lambda binary, recipe: {
            "binary": str(binary),
            "version": "codex-cli test",
            "sha256": "f" * 64,
            "exec_help_contract": "PASS",
        },
    )

    result = build_runtime(
        worktree=repo,
        recipe_path=recipe,
        target_dir=tmp_path / "target",
        min_free_gib=0,
    )

    assert result["head"] == final
    assert result["version"] == "codex-cli test"
    assert result["status"] == "PASS"


def test_production_recipe_encodes_qualified_0154_lineage():
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    recipe = tomllib.loads(
        (root / "codex-runtime-recipes" / "atlas-codex-0.154.toml").read_text(
            encoding="utf-8"
        )
    )

    assert recipe["upstream_commit"] == "6b9826e3aa83b1a5947db50f4332cb9c65f1b340"
    assert recipe["required_commits"] == ["513e4a57eb", "123825e5d3"]
    assert recipe["final_ref"] == "123825e5d3"


def test_release_lock_refresh_accepts_only_workspace_version_changes():
    from tools.atlas_agent.codex_release import _release_lock_refresh_only

    before = b"""
version = 4
[[package]]
name = "codex-cli"
version = "0.0.0"
dependencies = ["x"]
[[package]]
name = "x"
version = "1.2.3"
source = "registry+https://example.invalid"
checksum = "abc"
"""
    after = b"""
version = 4
[[package]]
name = "codex-cli"
version = "0.154.0"
dependencies = ["x"]
[[package]]
name = "x"
version = "1.2.3"
source = "registry+https://example.invalid"
checksum = "abc"
"""
    assert _release_lock_refresh_only(before, after, "0.154.0") == 1


def test_release_lock_refresh_rejects_dependency_change():
    from tools.atlas_agent.codex_release import _release_lock_refresh_only

    before = b"""
version = 4
[[package]]
name = "codex-cli"
version = "0.0.0"
dependencies = ["x"]
"""
    after = b"""
version = 4
[[package]]
name = "codex-cli"
version = "0.154.0"
dependencies = ["y"]
"""
    with pytest.raises(CodexBuildError, match="more than workspace release version"):
        _release_lock_refresh_only(before, after, "0.154.0")
