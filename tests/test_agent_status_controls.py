import pytest

from tools.atlas_agent import cli


def _record(number, status="COMPLETED", outcome="success", fallback=None, parent=None,
            session_mode=None):
    record = {
        "generation": number,
        "checkpoint": f"cp-{number}",
        "action": "implementation",
        "status": status,
        "result": {"outcome": outcome},
    }
    if parent is not None:
        record["parent"] = parent
    if session_mode is not None:
        record["session_mode"] = session_mode
    if fallback:
        record["execution"] = {"policy_snapshot": {
            "session_mode_requested": "reuse",
            "session_mode": "fresh",
            "reuse_fallback_reason": fallback,
        }}
    return record


class _Workflow:
    def __init__(self):
        self.root = "."
        self.allowed = []
        self.journal = self
        self.records = {
            str(n): _record(n, "RUNNING" if n == 1 else "COMPLETED",
                            None if n == 1 else "success",
                            "thread unavailable" if n == 12 else None)
            for n in range(1, 13)
        }

    def read(self):
        return []

    def _validate_historical_provenance(self, events):
        return None

    def _state_file(self):
        return self

    def exists(self):
        return True

    def _state(self):
        return {"generations": self.records}


@pytest.fixture
def status_cli(monkeypatch, capsys):
    workflow = _Workflow()
    monkeypatch.setattr(cli, "Workflow", lambda: workflow)
    monkeypatch.setattr(cli, "replay_journal", lambda events: workflow._state())
    monkeypatch.setattr(cli, "witness", lambda root, allowed: "same")
    workflow._state = lambda: {
        "generations": workflow.records,
        "latest_repository_witness": "same",
        "initialized": True,
    }
    return workflow, capsys


def run_status(args, status_cli):
    cli.main(["status", *args])
    return status_cli[1].readouterr().out


def test_status_default_is_bounded_and_old_attention_remains_visible(status_cli):
    output = run_status([], status_cli)
    assert "showing last 10 of 12" in output
    assert output.count("generation ") == 11  # ten recent plus old running g1
    assert "attention:" in output and "generation 1" in output
    assert "repository witness: MATCH" in output


def test_status_history_zero_and_detail_levels(status_cli):
    output = run_status(["--history", "0"], status_cli)
    assert "generation 2" not in output
    assert "generation 1" in output  # actionable state is not ordinary history
    assert "journal: OK" in output and "state: MATCH" in output
    compact = run_status(["--history", "3", "--detail", "compact"], status_cli)
    assert "generation 10  cp-10  implementation  status COMPLETED" in compact
    assert "session requested" not in compact
    full = run_status(["--history", "all", "--detail", "full"], status_cli)
    assert "generation 12" in full and "session requested reuse" in full
    assert "reuse fallback thread unavailable" in full


@pytest.mark.parametrize("args", [["--history", "-1"], ["--history", "nonsense"]])
def test_status_rejects_invalid_history(args, status_cli):
    with pytest.raises(SystemExit):
        cli.main(["status", *args])


@pytest.mark.parametrize("value", ["1_0", "+1", "-1", "1.0", "１２", "١", "01"])
def test_status_rejects_noncanonical_history(value, status_cli):
    with pytest.raises(SystemExit):
        cli.main(["status", "--history", value])


@pytest.mark.parametrize("value", ["0", "1", "10", "100", "all"])
def test_status_accepts_canonical_history(value):
    assert cli._history_value(value) == ("all" if value == "all" else int(value))


def test_attention_only_claims_currently_actionable_states():
    interrupted = _record(1, "INTERRUPTED")
    unrelated_completed = _record(2, parent=1)
    assert not cli._status_attention(interrupted, {"1": interrupted, "2": unrelated_completed})
    assert not cli._status_attention(_record(3, "INTERRUPTED"), {"3": _record(3, "INTERRUPTED")})
    assert cli._status_attention(_record(4, "ACCEPTED"), {"4": _record(4, "ACCEPTED")})
    assert cli._status_attention(_record(5, "RUNNING"), {"5": _record(5, "RUNNING")})
    assert not cli._status_attention(_record(6, "CANCELLED"), {"6": _record(6, "CANCELLED")})
    assert not cli._status_attention(_record(7, "COMPLETED", outcome="done"),
                                     {"7": _record(7, "COMPLETED", outcome="done")})
    assert not cli._status_attention(_record(35, "INTERRUPTED"),
                                     {"35": _record(35, "INTERRUPTED")})
    assert not cli._status_attention(_record(54, "INTERRUPTED"),
                                     {"54": _record(54, "INTERRUPTED")})


def test_interrupted_history_is_not_promoted_to_attention(status_cli):
    workflow, capsys = status_cli
    workflow.records = {
        "35": _record(35, "INTERRUPTED"),
        "54": _record(54, "INTERRUPTED"),
        "55": _record(55, "COMPLETED"),
    }
    output = run_status(["--history", "all"], status_cli)
    assert output.index("recent history:") < output.index("generation 35")
    assert output.index("generation 35") < output.index("generation 54")
    assert "attention:" not in output


def test_accepted_normal_detail_uses_persisted_session_request():
    record = _record(1, "ACCEPTED", session_mode="reuse")
    line = cli._status_line(1, record, "normal")
    assert "session requested reuse" in line
    assert "session resolved unavailable" in line


def test_full_detail_omits_persisted_session_fields_without_execution_snapshot():
    record = _record(1, "COMPLETED", session_mode="reuse")
    line = cli._status_line(1, record, "full")
    assert "session requested" not in line
    assert "session resolved" not in line


def test_status_rejects_invalid_detail(status_cli):
    with pytest.raises(SystemExit):
        cli.main(["status", "--detail", "verbose-but-unsupported"])
