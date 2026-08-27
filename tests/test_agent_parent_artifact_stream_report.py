import hashlib

from test_agent_operator_ergonomics import CodexFake, agent, jsonl
from test_agent_workflow_w221 import accepted, make_repo


def test_execution_digest_is_the_handed_off_effective_bytes(tmp_path):
    _, workflow = make_repo(tmp_path)
    raw = accepted(workflow)
    executor = CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "p"}, agent("report")), observed_thread_id="p")
    workflow.execute(1, executor)
    owner = workflow._state()["generations"]["1"]["execution"]
    effective = raw + b"Atlas-generated context supplement\n\nPrevious generation artifacts:\n- unavailable: no immediate parent artifact\n"
    assert owner["effective_prompt_sha256"] == hashlib.sha256(effective).hexdigest()
    assert owner["execution_input_sha256"] == hashlib.sha256(effective).hexdigest()


def test_report_availability_uses_terminal_descriptor_not_current_stdout(tmp_path):
    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    workflow.execute(1, CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "p"}, agent("report")), observed_thread_id="p"))
    accepted(workflow, generation=2)
    parent = workflow._state()["generations"]["1"]["execution"]
    (workflow.base / parent["report_dir"] / "stdout.log").write_bytes(b"changed\n")
    child = CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "c"}, agent("child")), observed_thread_id="c")
    workflow.execute(2, child)
    assert workflow._state()["generations"]["2"]["result"]["report_provenance"]["status"] == "available"
