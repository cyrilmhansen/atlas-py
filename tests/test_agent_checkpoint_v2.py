from tools.atlas_agent.workflow import Workflow

from test_agent_workflow_w221 import accepted, git, make_repo


def test_v2_manual_checkpoint_preserves_network_provenance_without_execution_owner(tmp_path):
    root, workflow = make_repo(tmp_path)
    (root / "a").write_text("reviewed\n")
    accepted(workflow, generation=1, action="checkpoint", network=False)

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
    assert starts[0]["payload"]["network_access"] is False
    assert "execution" not in starts[0]["payload"]

    rebuilt = Workflow(root)
    rebuilt.rebuild()
    assert rebuilt._state()["generations"]["1"]["status"] == "COMPLETED"
