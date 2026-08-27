import hashlib
import json

import pytest

from test_agent_operator_ergonomics import CodexFake, agent, jsonl
from test_agent_workflow_w221 import accepted, make_repo
from tools.atlas_agent.journal import Journal, JournalError, canonical
from tools.atlas_agent.workflow import replay_journal


def _rehash(path, rows):
    previous = "0" * 64
    for seq, row in enumerate(rows, 1):
        row["seq"] = seq
        row["previous_event_sha256"] = previous
        body = dict(row)
        body.pop("event_sha256", None)
        row["event_sha256"] = hashlib.sha256(canonical(body).encode()).hexdigest()
        previous = row["event_sha256"]
    path.write_text("".join(canonical(row) + "\n" for row in rows))


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def _run(w):
    accepted(w)
    w.execute(1, CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "parent"}, agent("done")), observed_thread_id="parent"))


def test_epoch_2_rejects_lifecycle_with_complete_modern_bundle_removed(tmp_path):
    _, w = make_repo(tmp_path)
    _run(w)
    rows = _rows(w.journal.path)
    modern = ("provenance_version", "execution_input_sha256", "report_provenance",
              "prompt_input", "context_path", "effective_prompt_path",
              "context_sha256", "effective_prompt_sha256")
    for row in rows:
        payload = row["payload"]
        if row["event"] in {"TRANSITION_PREPARED", "RUN_STARTED", "RUN_COMPLETED"}:
            payload.pop("context_supplement", None)
            for container in (payload, payload.get("execution"), payload.get("result"), payload.get("executor_result")):
                if isinstance(container, dict):
                    for key in modern:
                        container.pop(key, None)
    _rehash(w.journal.path, rows)
    with pytest.raises(JournalError):
        Journal(w.journal.path).read()


def test_epoch_2_rejects_running_start_without_modern_bundle_immediately(tmp_path):
    _, w = make_repo(tmp_path)
    _run(w)
    rows = _rows(w.journal.path)
    started = next(i for i, row in enumerate(rows) if row["event"] == "RUN_STARTED")
    modern = ("provenance_version", "execution_input_sha256", "report_provenance",
              "prompt_input", "context_path", "effective_prompt_path",
              "context_sha256", "effective_prompt_sha256")
    for row in rows[:started + 1]:
        if row["event"] in {"TRANSITION_PREPARED", "RUN_STARTED"}:
            row["payload"].pop("context_supplement", None)
            execution = row["payload"].get("execution")
            if isinstance(execution, dict):
                for key in modern:
                    execution.pop(key, None)
    # Keep the prepared transaction and RUN_STARTED pair, but omit terminal
    # events: this is a coherent journal ending in RUNNING.
    _rehash(w.journal.path, rows[:started + 1])
    with pytest.raises(JournalError, match="epoch-2 execution provenance"):
        Journal(w.journal.path).read()


def test_epoch_2_rejects_running_start_with_entire_execution_bundle_removed(tmp_path):
    _, w = make_repo(tmp_path)
    _run(w)
    rows = _rows(w.journal.path)
    started = next(i for i, row in enumerate(rows) if row["event"] == "RUN_STARTED")
    for row in rows[:started + 1]:
        if row["event"] in {"TRANSITION_PREPARED", "RUN_STARTED"}:
            row["payload"].pop("execution", None)
            row["payload"].pop("context_supplement", None)
    _rehash(w.journal.path, rows[:started + 1])
    with pytest.raises(JournalError, match="epoch-2 execution provenance"):
        Journal(w.journal.path).read()


def test_epoch_2_missing_schema_and_execution_bundle_cannot_downgrade_to_legacy(tmp_path):
    """A v2 root remains v2 when all positive modern lifecycle evidence is removed."""
    _, w = make_repo(tmp_path)
    _run(w)
    rows = _rows(w.journal.path)
    started = next(i for i, row in enumerate(rows) if row["event"] == "RUN_STARTED")
    for row in rows[:started + 1]:
        payload = row["payload"]
        if row["event"] == "PROMPT_ACCEPTED":
            payload.pop("prompt_schema", None)
        if row["event"] in {"TRANSITION_PREPARED", "RUN_STARTED"}:
            payload.pop("execution", None)
            payload.pop("context_supplement", None)
    _rehash(w.journal.path, rows[:started + 1])
    # PRODUCT_RED before the fix: the absent schema is incorrectly accepted as
    # explicit legacy evidence, despite the epoch-2 root.
    with pytest.raises(JournalError, match="epoch-2 execution provenance"):
        Journal(w.journal.path).read()


def test_initialization_is_single_durable_root_event(tmp_path):
    _, w = make_repo(tmp_path)
    original = _rows(w.journal.path)[0]

    duplicate = _rows(w.journal.path) + [json.loads(json.dumps(original))]
    _rehash(w.journal.path, duplicate)
    with pytest.raises(JournalError):
        Journal(w.journal.path).read()


def test_nonempty_journal_requires_initialization_root(tmp_path):
    _, w = make_repo(tmp_path)
    row = {"schema": _rows(w.journal.path)[0]["schema"], "seq": 1,
           "timestamp": _rows(w.journal.path)[0]["timestamp"],
           "event": "PROMPT_RECEIVED",
           "payload": {"prompt_sha256": "a" * 64, "source": "inbox/prompt.txt"},
           "previous_event_sha256": "0" * 64}
    row["event_sha256"] = hashlib.sha256(canonical(row).encode()).hexdigest()
    w.journal.path.write_text(canonical(row) + "\n")
    with pytest.raises(JournalError, match="initialization"):
        Journal(w.journal.path).read()


def test_root_moved_later_has_a_valid_event_before_it(tmp_path):
    _, w = make_repo(tmp_path)
    original = _rows(w.journal.path)[0]
    before = dict(original)
    before["event"] = "PROMPT_RECEIVED"
    before["payload"] = {"prompt_sha256": "b" * 64, "source": "inbox/prompt.txt"}
    rows = [before, original]
    _rehash(w.journal.path, rows)
    with pytest.raises(JournalError, match="root event"):
        Journal(w.journal.path).read()


def test_conflicting_later_epoch_is_rejected_independently(tmp_path):
    _, w = make_repo(tmp_path)
    original = _rows(w.journal.path)[0]
    later = json.loads(json.dumps(original))
    later["payload"]["validation_epoch"] = 1
    rows = [original, later]
    _rehash(w.journal.path, rows)
    with pytest.raises(JournalError, match="unique root"):
        Journal(w.journal.path).read()


def test_duplicate_initialization_is_rejected_independently(tmp_path):
    _, w = make_repo(tmp_path)
    original = _rows(w.journal.path)[0]
    rows = [original, json.loads(json.dumps(original))]
    _rehash(w.journal.path, rows)
    with pytest.raises(JournalError, match="unique root"):
        Journal(w.journal.path).read()



def test_genuine_legacy_initialization_remains_readable_and_rebuildable(tmp_path):
    _, w = make_repo(tmp_path)
    rows = _rows(w.journal.path)
    rows[0]["payload"].pop("validation_epoch")
    _rehash(w.journal.path, rows)
    for path in (w.base / "reports" / "contexts").glob("*.txt"):
        path.unlink()
    w._state_file().unlink()
    state = w.rebuild()
    assert state["initialized"] is True
    assert state.get("validation_epoch", 1) == 1


def test_genuine_legacy_execution_lifecycle_rebuilds(tmp_path):
    _, w = make_repo(tmp_path)
    _run(w)
    rows = _rows(w.journal.path)
    modern = ("provenance_version", "execution_input_sha256", "report_provenance",
              "prompt_input", "context_path", "effective_prompt_path",
              "context_sha256", "effective_prompt_sha256")
    for row in rows:
        payload = row["payload"]
        if row["event"] == "WORKFLOW_INITIALIZED":
            payload.pop("validation_epoch", None)
        if row["event"] in {"TRANSITION_PREPARED", "RUN_STARTED", "RUN_COMPLETED"}:
            payload.pop("context_supplement", None)
            for container in (payload, payload.get("execution"), payload.get("result")):
                if isinstance(container, dict):
                    for key in modern:
                        container.pop(key, None)
    _rehash(w.journal.path, rows)
    for path in (w.base / "reports" / "contexts").glob("*.txt"):
        path.unlink()
    w._state_file().unlink()
    state = w.rebuild()
    assert state["generations"]["1"]["status"] == "COMPLETED"


def test_post_start_keyboard_interrupt_durably_interrupts_generation(tmp_path, monkeypatch):
    _, w = make_repo(tmp_path)
    accepted(w)

    def interrupt_during_context(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(w, "_publish_context", interrupt_during_context)
    with pytest.raises(KeyboardInterrupt):
        w.execute(1, CodexFake())

    reconstructed = replay_journal(w.journal.read())
    assert reconstructed["generations"]["1"]["status"] == "INTERRUPTED"
    interrupted = [e for e in w.journal.read() if e["event"] == "RUN_INTERRUPTED"]
    assert interrupted[-1]["payload"]["reason"] == "KEYBOARD_INTERRUPT"


def test_keyboard_interrupt_at_first_post_start_projection_is_terminal(tmp_path, monkeypatch):
    _, w = make_repo(tmp_path)
    accepted(w)
    from tools.atlas_agent import workflow as workflow_module
    original = workflow_module.replay_journal
    tripped = False

    def interrupt_after_start(events):
        nonlocal tripped
        if not tripped and any(e["event"] == "RUN_STARTED" for e in events):
            tripped = True
            raise KeyboardInterrupt()
        return original(events)

    monkeypatch.setattr(workflow_module, "replay_journal", interrupt_after_start)
    with pytest.raises(KeyboardInterrupt):
        w.execute(1, CodexFake())
    reconstructed = original(w.journal.read())
    assert reconstructed["generations"]["1"]["status"] == "INTERRUPTED"
    assert reconstructed["generations"]["1"]["status"] != "RUNNING"
    assert w._interruption_reason(1) == "KEYBOARD_INTERRUPT"


def test_start_run_keyboard_interrupt_at_first_post_start_projection_is_terminal(tmp_path, monkeypatch):
    _, w = make_repo(tmp_path)
    accepted(w)
    from tools.atlas_agent import workflow as workflow_module
    original = workflow_module.replay_journal
    tripped = False

    def interrupt_after_start(events):
        nonlocal tripped
        if not tripped and any(e["event"] == "RUN_STARTED" for e in events):
            tripped = True
            raise KeyboardInterrupt()
        return original(events)

    monkeypatch.setattr(workflow_module, "replay_journal", interrupt_after_start)
    with pytest.raises(KeyboardInterrupt):
        w.start_run(1, execution={
            "execution_id": "start-run-interrupted",
            "executor": "fake",
            "started_at": "2026-01-01T00:00:00Z",
            "pid": None,
            "report_dir": "reports/executions/start-run-interrupted",
        })
    monkeypatch.setattr(workflow_module, "replay_journal", original)
    rebuilt = original(w.journal.read())
    assert rebuilt["generations"]["1"]["status"] == "INTERRUPTED"
    assert rebuilt["generations"]["1"]["status"] != "RUNNING"
    assert w._interruption_reason(1) == "KEYBOARD_INTERRUPT"


def test_execute_preserves_keyboard_interrupt_when_terminal_projection_fails(tmp_path, monkeypatch):
    _, w = make_repo(tmp_path)
    accepted(w)

    class Interrupted(CodexFake):
        def run_execution(self, prepared):
            raise KeyboardInterrupt()

    original_save = w._save

    def fail_interrupted_projection(state):
        if state["generations"]["1"]["status"] == "INTERRUPTED":
            raise OSError("projection failure")
        return original_save(state)

    monkeypatch.setattr(w, "_save", fail_interrupted_projection)
    # PRODUCT_RED before the fix: RUN_TERMINALIZATION_FAILED masks the abort.
    with pytest.raises(KeyboardInterrupt):
        w.execute(1, Interrupted())
    events = w.journal.read()
    assert events[-1]["event"] == "RUN_INTERRUPTED"
    assert events[-1]["payload"]["reason"] == "KEYBOARD_INTERRUPT"
    assert replay_journal(events)["generations"]["1"]["status"] == "INTERRUPTED"
