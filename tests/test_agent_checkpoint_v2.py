import json

import pytest

from tools.atlas_agent.journal import JournalError, _hash_event, canonical
from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import Workflow

from test_agent_workflow_w221 import accepted, git, make_repo


@pytest.mark.parametrize("network", [False, True])
def test_v2_manual_checkpoint_preserves_network_provenance_without_execution_owner(tmp_path, network):
    # The modification is part of the repository state reviewed by the
    # workflow witness, rather than a change made after Workflow.init().
    root, workflow = make_repo(tmp_path, dirty_tracked="reviewed\n")
    accepted(workflow, generation=1, action="checkpoint", network=network)
    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"

    state = workflow.checkpoint(1, "checkpoint v2 provenance")

    record = state["generations"]["1"]
    assert record["status"] == "COMPLETED"
    assert record["result"]["commit_sha"] == git(root, "rev-parse", "HEAD")
    assert "execution" not in record

    starts = [
        event
        for event in workflow.journal.read()
        if event["event"] == "RUN_STARTED" and event["payload"]["generation"] == 1
    ]
    assert len(starts) == 1
    assert starts[0]["payload"]["network_access"] is network
    assert "execution" not in starts[0]["payload"]

    rebuilt = Workflow(root)
    rebuilt.rebuild()
    assert rebuilt._state()["generations"]["1"]["status"] == "COMPLETED"


def _rehash(path, rows):
    previous = "0" * 64
    for seq, row in enumerate(rows, 1):
        row["seq"] = seq
        row["previous_event_sha256"] = previous
        row["event_sha256"] = _hash_event(row)
        previous = row["event_sha256"]
    path.write_text("\n".join(canonical(row) for row in rows) + "\n")


def test_rehashed_implementation_history_cannot_claim_checkpoint_authority(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow, action="implementation")
    workflow.execute(1, FakeExecutor(
        observed_thread_id="thread-authority",
        observed_model="gpt-5.6-luna",
        observed_reasoning="medium",
    ))

    path = workflow.journal.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        payload = row["payload"]
        if "action" in payload:
            payload["action"] = "checkpoint"
        payload.pop("execution", None)
        payload.pop("context_supplement", None)
    _rehash(path, rows)

    with pytest.raises(JournalError, match="prompt action archive mismatch"):
        workflow.journal.read()


def test_rehashed_run_started_cannot_change_accepted_action(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow, action="implementation")
    workflow.execute(1, FakeExecutor(
        observed_thread_id="thread-authority",
        observed_model="gpt-5.6-luna",
        observed_reasoning="medium",
    ))

    path = workflow.journal.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row["event"] in {"TRANSITION_PREPARED", "RUN_STARTED"}:
            row["payload"]["action"] = "checkpoint"
            row["payload"].pop("execution", None)
            row["payload"].pop("context_supplement", None)
    _rehash(path, rows)

    with pytest.raises(JournalError, match="lifecycle action mismatch"):
        workflow.journal.read()
