"""Material regression coverage for the frozen P0.4 cancellation contract."""
import hashlib

import pytest

from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import WorkflowError
from test_agent_workflow_w221 import accepted, make_repo, prompt


def _cancelled(w, reason="operator requested cancellation"):
    accepted(w)
    result = w.cancel(1, reason)
    return result, w._state()


def test_cancel_binds_reason_lifecycle_spool_and_archive(tmp_path):
    _, w = make_repo(tmp_path)
    result, state = _cancelled(w, "do not run this exact text")
    digest = state["generations"]["1"]["prompt_sha256"]
    name = f"g000001-{digest}.txt"

    assert result["result"] == "CANCELLED"
    assert state["generations"]["1"]["status"] == "CANCELLED"
    assert state["generations"]["1"]["cancellation_reason"] == "do not run this exact text"
    assert (w.base / "cancelled" / name).is_file()
    assert not (w.base / "accepted" / name).exists()
    assert (w.base / "prompts" / f"{digest}.txt").is_file()
    event = [e for e in w.journal.read() if e["event"] == "PROMPT_CANCELLED"][0]
    assert event["payload"]["source"] == f"accepted/{name}"
    assert event["payload"]["destination"] == f"cancelled/{name}"
    assert event["payload"]["reason"] == "do not run this exact text"


def test_cancelled_head_of_queue_is_skipped_and_is_not_reused(tmp_path):
    _, w = make_repo(tmp_path)
    accepted(w, generation=1, schema=1)
    accepted(w, generation=2, schema=1)
    w.cancel(1, "obsolete")
    assert w.dispatch(FakeExecutor(observed_thread_id="dispatch-thread"))["generation"] == 2
    assert w._state()["generations"]["1"]["status"] == "CANCELLED"
    assert not any(e["event"] == "RUN_STARTED" and e["payload"]["generation"] == 1
                   for e in w.journal.read())


def test_cancel_latest_then_ingest_changed_next_generation(tmp_path):
    _, w = make_repo(tmp_path)
    first = accepted(w, generation=1)
    first_hash = hashlib.sha256(first).hexdigest()
    w.cancel(1, "intent changed")
    replacement = prompt(w, generation=2)
    replacement = replacement.replace(b"W2.2.1\n", b"changed intent body\n")
    (w.base / "inbox" / "g2.txt").write_bytes(replacement)
    w.ingest()
    state = w._state()
    assert state["generations"]["1"]["status"] == "CANCELLED"
    assert state["generations"]["2"]["parent"] == 1
    assert state["generations"]["2"]["prompt_sha256"] != first_hash
    assert state["generations"]["2"]["session_mode"] == "fresh"
    assert (w.base / "prompts" / f"{state['generations']['2']['prompt_sha256']}.txt").read_bytes() == replacement


@pytest.mark.parametrize("terminal", ["RUNNING", "COMPLETED", "INTERRUPTED"])
def test_started_generations_cannot_be_cancelled(tmp_path, terminal):
    _, w = make_repo(tmp_path)
    accepted(w, schema=1)
    if terminal == "RUNNING":
        w.start_run(1)
    else:
        w.start_run(1)
        if terminal == "COMPLETED":
            record = w._state()["generations"]["1"]
            w.complete_run(1, {"generation": 1, "prompt_sha256": record["prompt_sha256"],
                               "action": "implementation", "outcome": "done"})
        else:
            w.interrupt_run(1, "stopped")
    before = len(w.journal.read())
    with pytest.raises(WorkflowError, match="GENERATION_ALREADY_STARTED"):
        w.cancel(1, "too late")
    assert len(w.journal.read()) == before
    assert not list((w.base / "cancelled").glob("*.txt"))


def test_checkpoint_can_cancel_before_intent_and_intent_blocks_until_recovery(tmp_path):
    _, w = make_repo(tmp_path)
    accepted(w, action="checkpoint")
    w.cancel(1, "checkpoint no longer wanted")
    assert w._state()["generations"]["1"]["status"] == "CANCELLED"

    root, w = make_repo(tmp_path / "second", dirty_tracked="checkpoint change")
    accepted(w, action="checkpoint")
    with pytest.raises(RuntimeError):
        w.checkpoint(1, "boundary", hook=lambda phase, payload: (
            (_ for _ in ()).throw(RuntimeError("crash")) if phase == "intent" else None))
    with pytest.raises(WorkflowError):
        w.cancel(1, "blocked by intent")
    w.recover()
    assert w.cancel(1, "after recovery")["result"] == "CANCELLED"


@pytest.mark.parametrize("reason", [None, 7, "", " \t"])
def test_cancel_requires_verbatim_nonblank_string_reason(tmp_path, reason):
    _, w = make_repo(tmp_path)
    accepted(w, schema=1)
    with pytest.raises(WorkflowError, match="CANCELLATION_REASON_REQUIRED"):
        w.cancel(1, reason)
    assert not any(e["event"] == "PROMPT_CANCELLED" for e in w.journal.read())


def test_cancel_operator_idempotence_and_reason_mismatch(tmp_path):
    _, w = make_repo(tmp_path)
    _cancelled(w, "same")
    events = len([e for e in w.journal.read() if e["event"] == "PROMPT_CANCELLED"])
    assert w.cancel(1, "same")["result"] == "ALREADY_CANCELLED"
    assert len([e for e in w.journal.read() if e["event"] == "PROMPT_CANCELLED"]) == events
    with pytest.raises(WorkflowError, match="CANCELLATION_REASON_MISMATCH"):
        w.cancel(1, "different")


@pytest.mark.parametrize("phase", ["prepared", "renamed", "state_save"])
def test_cancel_crash_boundaries_recover_once(tmp_path, phase, monkeypatch):
    _, w = make_repo(tmp_path)
    accepted(w, schema=1)
    def crash(at, _data):
        if at == phase:
            raise RuntimeError("simulated crash")
    if phase == "state_save":
        original_save = w._save
        def save(state):
            if state["generations"]["1"]["status"] == "CANCELLED":
                raise RuntimeError("simulated crash")
            return original_save(state)
        monkeypatch.setattr(w, "_save", save)
    with pytest.raises(RuntimeError):
        w.cancel(1, "recover me", hook=None if phase == "state_save" else crash)
    if phase == "state_save":
        monkeypatch.setattr(w, "_save", original_save)
    state = w.recover()
    assert state["generations"]["1"]["status"] == "CANCELLED"
    assert len([e for e in w.journal.read() if e["event"] == "PROMPT_CANCELLED"]) == 1
    assert w.recover()["generations"]["1"]["status"] == "CANCELLED"
    assert len([e for e in w.journal.read() if e["event"] == "PROMPT_CANCELLED"]) == 1


def test_rebuild_state_and_doctor_preserve_repository_witness(tmp_path, monkeypatch, capsys):
    root, w = make_repo(tmp_path)
    old = w._state()["latest_repository_witness"]
    accepted(w, schema=1)
    w.cancel(1, "no repository change")
    assert w._state()["latest_repository_witness"] == old
    state_file = w._state_file()
    state_file.unlink()
    rebuilt = w.rebuild()
    assert rebuilt["generations"]["1"]["status"] == "CANCELLED"
    assert rebuilt["generations"]["1"]["cancellation_reason"] == "no repository change"
    monkeypatch.chdir(root)
    from tools.atlas_agent.cli import main
    assert main(["doctor"]) == 0
    assert "doctor: OK" in capsys.readouterr().out


def test_cancellation_does_not_bless_new_repository_divergence(tmp_path, monkeypatch, capsys):
    root, w = make_repo(tmp_path)
    accepted(w)
    (root / "surprise.txt").write_text("outside the accepted witness")
    w.cancel(1, "must not bless divergence")
    assert any(e["event"] == "PROMPT_CANCELLED" for e in w.journal.read())
    monkeypatch.chdir(root)
    from tools.atlas_agent.cli import main
    assert main(["doctor"]) == 1
    assert "REPOSITORY_WITNESS_MISMATCH" in capsys.readouterr().err


def test_cancelled_parent_context_is_bounded_and_informational(tmp_path):
    _, w = make_repo(tmp_path)
    accepted(w)
    w.cancel(1, "parent stopped")
    data, metadata = w._parent_context(w._state(), 2)
    assert b"status: CANCELLED" in data
    assert metadata == {"kind": "execution", "generation": 1, "status": "CANCELLED",
                        "execution_id": None, "report_available": False}


def test_cancelled_checkpoint_parent_context_has_no_execution_authority(tmp_path):
    _, w = make_repo(tmp_path)
    accepted(w, action="checkpoint")
    w.cancel(1, "checkpoint parent stopped")
    data, metadata = w._parent_context(w._state(), 2)
    assert b"action: checkpoint" in data
    assert b"status: CANCELLED" in data
    assert metadata == {"kind": "checkpoint", "generation": 1,
                        "status": "CANCELLED", "commit": None}


def test_safe_reuse_fallback_remains_non_cancellation(tmp_path):
    _, w = make_repo(tmp_path)
    accepted(w)
    w.execute(1, FakeExecutor(observed_thread_id="thread"))
    accepted(w, generation=2, session="reuse", target="missing-execution")
    with pytest.raises(WorkflowError, match="REUSE_TARGET_UNKNOWN"):
        w.execute(2, FakeExecutor(observed_thread_id="new-thread"))
    assert not any(e["event"] == "PROMPT_CANCELLED" for e in w.journal.read())


@pytest.mark.parametrize("damage", ["missing", "corrupt", "duplicate", "orphan", "archive"])
def test_cancelled_spool_validation_fails_closed(tmp_path, damage):
    _, w = make_repo(tmp_path)
    _, state = _cancelled(w)
    record = state["generations"]["1"]
    cancelled = next((w.base / "cancelled").glob("*.txt"))
    if damage == "missing":
        cancelled.unlink()
    elif damage == "corrupt":
        cancelled.write_bytes(b"tampered")
    elif damage == "duplicate":
        (w.base / "accepted" / cancelled.name).write_bytes(cancelled.read_bytes())
    elif damage == "orphan":
        (w.base / "cancelled" / ("g000099-" + "0" * 64 + ".txt")).write_bytes(b"orphan")
    else:
        (w.base / "prompts" / f"{record['prompt_sha256']}.txt").unlink()
    with pytest.raises((RuntimeError, WorkflowError), match="SPOOL_CORRUPT|PROMPT_ARCHIVE|prompt archive"):
        w.rebuild()


@pytest.mark.parametrize("mutation", ["generation", "hash", "missing", "nonstring", "blank", "mismatch"])
def test_cancellation_journal_authority_rejects_tampering(tmp_path, mutation):
    _, w = make_repo(tmp_path)
    accepted(w)
    record = w._state()["generations"]["1"]
    digest = record["prompt_sha256"]
    tx = "tampered-cancellation"
    prepared = {"transaction_id": tx, "logical_event": "PROMPT_CANCELLED",
                "source": f"accepted/g000001-{digest}.txt",
                "destination": f"cancelled/g000001-{digest}.txt",
                "prompt_sha256": digest, "generation": 1, "reason": "valid"}
    terminal = dict(prepared)
    terminal.pop("logical_event")
    if mutation == "generation":
        terminal["generation"] = 2
    elif mutation == "hash":
        terminal["prompt_sha256"] = "0" * 64
    elif mutation == "missing":
        terminal.pop("reason")
    elif mutation == "nonstring":
        terminal["reason"] = 9
    elif mutation == "blank":
        terminal["reason"] = " "
    else:
        terminal["reason"] = "different"
    w.journal.append("TRANSITION_PREPARED", **prepared)
    w.journal.append("PROMPT_CANCELLED", **terminal)
    with pytest.raises(WorkflowError):
        w.rebuild()
