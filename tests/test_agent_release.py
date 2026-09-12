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
