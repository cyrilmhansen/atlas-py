import hashlib
import json

import pytest

from test_agent_operator_ergonomics import CodexFake, agent, jsonl
from test_agent_workflow_w221 import accepted, make_repo
from tools.atlas_agent.journal import Journal, JournalError, canonical
from tools.atlas_agent.workflow import WorkflowError


def _rehash(path, mutate):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    mutate(rows)
    previous="0"*64
    for row in rows:
        row["previous_event_sha256"]=previous
        body=dict(row); body.pop("event_sha256",None)
        row["event_sha256"]=hashlib.sha256(canonical(body).encode()).hexdigest()
        previous=row["event_sha256"]
    path.write_text("".join(canonical(row)+"\n" for row in rows))


def _two_runs(w):
    accepted(w)
    w.execute(1,CodexFake(stdout=jsonl({"type":"thread.started","thread_id":"p"},agent("done")),observed_thread_id="p"))
    accepted(w,generation=2)
    return w


def test_rehashed_false_parent_semantics_fail_closed(tmp_path):
    w=_two_runs(make_repo(tmp_path)[1])
    events=w.journal.read()
    context=next(e["payload"]["context_supplement"] for e in reversed(events) if "context_supplement" in e["payload"])
    forged=context.replace("- action: implementation", "- action: patch_review")
    with pytest.raises(JournalError):
        Journal._validate_payload("RUN_STARTED", {
            "transaction_id":"tx","source":"accepted/x","destination":"running/implementation/x",
            "generation":2,"prompt_sha256":"a"*64,"action":"implementation",
            "context_supplement":forged,
            "execution":{"execution_id":"e","executor":"fake","started_at":"2026-01-01T00:00:00Z","pid":None,"report_dir":"reports/executions/e",
                         "prompt_input":"accepted_prompt_plus_atlas_context","context_path":"reports/contexts/e.txt","effective_prompt_path":"reports/contexts/e-effective.txt",
                         "context_sha256":hashlib.sha256(forged.encode()).hexdigest(),"effective_prompt_sha256":"b"*64}}, 1,
            {1:{"generation":1,"action":"implementation","status":"COMPLETED","execution":{"execution_id":"p"},"result":{"executor_result":{"session_id":"p"}}}})


def test_parent_context_uses_historical_state(tmp_path):
    _,w=make_repo(tmp_path)
    accepted(w)
    # Leave generation 1 accepted while generation 2 is prepared manually is
    # invalid; the useful historical check is exercised by recovery below.
    w.execute(1,CodexFake(stdout=jsonl({"type":"thread.started","thread_id":"p"},agent("done")),observed_thread_id="p"))
    accepted(w,generation=2)
    child=w.execute(2,CodexFake(stdout=jsonl({"type":"thread.started","thread_id":"c"},agent("done")),observed_thread_id="c"))
    owner=w._state()["generations"]["2"]["execution"]
    (w.base/owner["context_path"]).unlink(); (w.base/owner["effective_prompt_path"]).unlink()
    assert w.recover()["generations"]["2"]["status"]=="COMPLETED"
    assert child is not None


def test_false_effective_hash_does_not_publish_owner_or_commit(tmp_path):
    _,w=make_repo(tmp_path); raw=accepted(w)
    source=next((w.base/"accepted").iterdir())
    supplement=w._parent_context({"generations":{}},1)[0].decode()
    execution_id="123e4567-e89b-12d3-a456-426614174000"
    owner={"execution_id":execution_id,"executor":"fake","started_at":"2026-08-26T00:00:00Z","pid":None,
           "report_dir":f"reports/executions/{execution_id}","prompt_input":"accepted_prompt_plus_atlas_context",
           "context_path":f"reports/contexts/{execution_id}.txt","effective_prompt_path":f"reports/contexts/{execution_id}-effective.txt",
           "context_sha256":hashlib.sha256(supplement.encode()).hexdigest(),"effective_prompt_sha256":"0"*64}
    w.journal.append("TRANSITION_PREPARED",transaction_id="tx",logical_event="RUN_STARTED",
                     source=f"accepted/{source.name}",destination=f"running/implementation/{source.name}",
                     prompt_sha256=hashlib.sha256(raw).hexdigest(),generation=1,action="implementation",
                     execution=owner,context_supplement=supplement)
    with pytest.raises(WorkflowError,match="(?:EXECUTION_CONTEXT_HASH_MISMATCH|epoch-2 start witness incomplete)"):
        w.recover()
    assert not (w.base/"reports"/"executions"/execution_id/"execution.json").exists()
    with pytest.raises(JournalError, match="epoch-2 start witness"):
        w.journal.read()


def test_modern_provenance_fields_cannot_be_reclassified_as_legacy(tmp_path):
    w=_two_runs(make_repo(tmp_path)[1])
    def mutate(rows):
        for row in rows:
            if row["event"]=="RUN_STARTED":
                row["payload"]["execution"].pop("provenance_version")
                return
    _rehash(w.journal.path, mutate)
    with pytest.raises(JournalError):
        Journal(w.journal.path).read()


def test_complete_v2_downgrade_shape_is_rejected(tmp_path):
    w=_two_runs(make_repo(tmp_path)[1])
    def mutate(rows):
        for row in rows:
            payload=row["payload"]
            for container in (payload, payload.get("execution"), payload.get("result"), payload.get("executor_result")):
                if isinstance(container,dict):
                    for key in ("provenance_version", "execution_input_sha256", "report_provenance"):
                        container.pop(key, None)
    _rehash(w.journal.path, mutate)
    with pytest.raises(JournalError):
        Journal(w.journal.path).read()


def test_interrupted_projection_preserves_executor_result_and_thread_identity(tmp_path):
    _,w=make_repo(tmp_path)
    state={"generations":{"1":{"status":"INTERRUPTED","execution":{"execution_id":"e"},
        "result":{"report_provenance":{"status":"available","report_sha256":"a"*64}},
        "execution_result":{"session_id":"interrupted-thread","outcome":"failed"}}}}
    assert w._execution_result(state["generations"]["1"])["session_id"] == "interrupted-thread"
    assert "interrupted-thread" in w._known_thread_ids(state)


def test_terminal_v2_record_binds_observed_input_digest(tmp_path):
    w=_two_runs(make_repo(tmp_path)[1])
    def mutate(rows):
        for row in rows:
            if row["event"]=="RUN_COMPLETED":
                row["payload"]["result"]["executor_result"]["execution_input_sha256"]="f"*64
                return
    _rehash(w.journal.path, mutate)
    with pytest.raises(JournalError):
        Journal(w.journal.path).read()


def test_legacy_parent_report_availability_is_terminal_state(tmp_path):
    _,w=make_repo(tmp_path)
    state={"generations": {"1": {
        "generation": 1, "action": "implementation", "status": "COMPLETED",
        "execution": {"execution_id": "legacy", "executor": "fake"},
        "result": {"executor_result": {"session_id": "thread"},
                    "report_provenance": {"status": "available"}},
    }}}
    data,_=w._parent_context(state,2)
    assert "report: available" in data.decode()
