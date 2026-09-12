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
