import json
from pathlib import Path

import pytest

from tools.atlas_agent.release import (
    ReleaseCheckError,
    _latest_agent_message,
    _require_single,
)


def test_latest_agent_message_uses_completed_agent_message_only():
    lines = [
        {"type": "item.completed", "item": {"type": "reasoning", "text": "wrong"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "final"}},
    ]
    payload = "\n".join(json.dumps(line) for line in lines)
    assert _latest_agent_message(payload) == "final"


def test_latest_agent_message_does_not_accept_prompt_echo_or_non_json():
    payload = (
        "ATLAS_SMOKE_SOL_MEDIUM_OK\n"
        + json.dumps({"type": "item.started", "item": {"type": "agent_message",
                                                       "text": "ATLAS_SMOKE_SOL_MEDIUM_OK"}})
    )
    assert _latest_agent_message(payload) is None


def test_require_single_accepts_repeated_identity():
    assert _require_single(["abc", "abc", "abc"], "digest") == "abc"


def test_require_single_rejects_split_authority():
    with pytest.raises(ReleaseCheckError, match="not uniform"):
        _require_single(["abc", "def"], "digest")


def test_promote_controller_infers_boundary_and_adopts(tmp_path, monkeypatch):
    import subprocess
    import tools.atlas_agent.release as release
    from tools.atlas_agent.workflow import Workflow

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@e"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)
    (repo / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\nallowed_untracked = []\n',
        encoding="utf-8",
    )
    (repo / "a").write_text("a", encoding="utf-8")
    subprocess.check_call(["git", "add", "."], cwd=repo)
    subprocess.check_call(["git", "commit", "-qm", "genesis"], cwd=repo)

    workflow = Workflow(repo)
    workflow.init()
    old_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()

    (repo / "a").write_text("b", encoding="utf-8")
    subprocess.check_call(["git", "add", "a"], cwd=repo)
    subprocess.check_call(["git", "commit", "-qm", "candidate"], cwd=repo)
    new_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()

    monkeypatch.setenv("ATLAS_AGENT_SRC", str(repo))
    monkeypatch.setattr(
        release, "preflight",
        lambda **kwargs: {"schema": "test-preflight"},
    )
    monkeypatch.setattr(
        release, "post_cutover",
        lambda **kwargs: {"schema": "test-post", "status": "PASS"},
    )

    result = release.promote_controller(
        root=repo,
        reason="qualified controller promotion",
    )

    assert result["previous_head"] == old_head
    assert result["current_head"] == new_head
    assert result["boundary"] == "ADOPTED"
    assert Workflow(repo)._state()["latest_repository_witness"]["head"] == new_head


def test_promote_controller_is_idempotent_when_boundary_matches(tmp_path, monkeypatch):
    import subprocess
    import tools.atlas_agent.release as release
    from tools.atlas_agent.workflow import Workflow

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@e"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)
    (repo / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\nallowed_untracked = []\n',
        encoding="utf-8",
    )
    (repo / "a").write_text("a", encoding="utf-8")
    subprocess.check_call(["git", "add", "."], cwd=repo)
    subprocess.check_call(["git", "commit", "-qm", "genesis"], cwd=repo)

    Workflow(repo).init()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()

    monkeypatch.setenv("ATLAS_AGENT_SRC", str(repo))
    monkeypatch.setattr(
        release, "preflight",
        lambda **kwargs: {"schema": "test-preflight"},
    )
    monkeypatch.setattr(
        release, "post_cutover",
        lambda **kwargs: {"schema": "test-post", "status": "PASS"},
    )

    result = release.promote_controller(root=repo, reason="repeat verification")
    assert result["previous_head"] == head
    assert result["current_head"] == head
    assert result["boundary"] == "ALREADY_MATCHED"


def test_candidate_runtime_rejects_non_elf(tmp_path):
    from tools.atlas_agent.release import ReleaseCheckError, _candidate_runtime

    candidate = tmp_path / "codex"
    candidate.write_text("not elf", encoding="utf-8")
    candidate.chmod(0o755)

    with pytest.raises(ReleaseCheckError, match="not an ELF"):
        _candidate_runtime(candidate)


def test_atomic_write_preserves_file_mode(tmp_path):
    from tools.atlas_agent.release import _atomic_write

    path = tmp_path / "policy.toml"
    path.write_bytes(b"old\n")
    path.chmod(0o640)

    _atomic_write(path, b"new\n")

    assert path.read_bytes() == b"new\n"
    assert (path.stat().st_mode & 0o777) == 0o640


def test_prepare_runtime_installs_and_updates_only_policy_digest(tmp_path, monkeypatch):
    import hashlib
    import subprocess
    import tomllib
    import tools.atlas_agent.release as release

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@e"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)

    releases = tmp_path / "releases"
    current_dir = releases / "old-release"
    current_dir.mkdir(parents=True)
    current = current_dir / "codex"
    current.write_bytes(b"old-runtime")

    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"new-runtime")
    new_digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    old_digest = hashlib.sha256(current.read_bytes()).hexdigest()

    policy = (
        'schema = "test"\n'
        '[profiles.implementation]\n'
        'executor = "codex"\n'
        f'codex_binary_sha256 = "{old_digest}"\n'
        'other = "keep-me"\n'
        '[profiles.patch_review]\n'
        'executor = "codex"\n'
        f'codex_binary_sha256 = "{old_digest}"\n'
        'other = "keep-me-too"\n'
    )
    (repo / "atlas-agent-policy.toml").write_text(policy, encoding="utf-8")
    subprocess.check_call(["git", "add", "."], cwd=repo)
    subprocess.check_call(["git", "commit", "-qm", "genesis"], cwd=repo)

    monkeypatch.setattr(release, "_runtime_from_environment", lambda: (current, tmp_path))
    monkeypatch.setattr(
        release,
        "_candidate_runtime",
        lambda path: (candidate, new_digest, "codex-cli test"),
    )
    monkeypatch.setattr(release, "_check_native_resolver", lambda path: None)

    result = release.prepare_runtime(
        candidate=candidate,
        release_id="new-release",
        root=repo,
        releases_dir=releases,
    )

    target = releases / "new-release" / "codex"
    assert target.read_bytes() == candidate.read_bytes()
    assert result["runtime"] == str(target)
    assert result["policy_profiles_updated"] == 2

    parsed = tomllib.loads((repo / "atlas-agent-policy.toml").read_text())
    assert parsed["profiles"]["implementation"]["codex_binary_sha256"] == new_digest
    assert parsed["profiles"]["patch_review"]["codex_binary_sha256"] == new_digest
    assert parsed["profiles"]["implementation"]["other"] == "keep-me"
    assert parsed["profiles"]["patch_review"]["other"] == "keep-me-too"
    assert current.read_bytes() == b"old-runtime"


def test_prepare_runtime_rejects_split_policy_authority(tmp_path, monkeypatch):
    import subprocess
    import tools.atlas_agent.release as release

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@e"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)

    releases = tmp_path / "releases"
    current_dir = releases / "old-release"
    current_dir.mkdir(parents=True)
    current = current_dir / "codex"
    current.write_bytes(b"old-runtime")

    (repo / "atlas-agent-policy.toml").write_text(
        'schema = "test"\n'
        '[profiles.a]\nexecutor = "codex"\ncodex_binary_sha256 = "' + "a" * 64 + '"\n'
        '[profiles.b]\nexecutor = "codex"\ncodex_binary_sha256 = "' + "b" * 64 + '"\n',
        encoding="utf-8",
    )
    subprocess.check_call(["git", "add", "."], cwd=repo)
    subprocess.check_call(["git", "commit", "-qm", "genesis"], cwd=repo)

    monkeypatch.setattr(release, "_runtime_from_environment", lambda: (current, tmp_path))
    monkeypatch.setattr(
        release,
        "_candidate_runtime",
        lambda path: (tmp_path / "candidate", "c" * 64, "codex-cli test"),
    )

    with pytest.raises(ReleaseCheckError, match="not uniform"):
        release.prepare_runtime(
            candidate=tmp_path / "candidate",
            release_id="new-release",
            root=repo,
            releases_dir=releases,
        )

    assert not (releases / "new-release").exists()
