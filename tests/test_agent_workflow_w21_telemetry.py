import json
import subprocess

from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.workflow import Workflow


def git(p, *args):
    return subprocess.check_output(["git", *args], cwd=p, text=True).strip()


def repo(tmp_path):
    p = tmp_path / "repo"
    p.mkdir()
    git(p, "init", "-q")
    git(p, "config", "user.email", "t@e")
    git(p, "config", "user.name", "t")
    (p / "a").write_text("a")
    (p / "atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    git(p, "add", ".")
    git(p, "commit", "-qm", "g")
    w = Workflow(p)
    w.init()
    raw = f'''+++
schema = "atlas-agent-prompt/1"
generation = 1
parent = "genesis"
checkpoint = "TELEMETRY"
action = "implementation"
expected_head = "{git(p, "rev-parse", "HEAD")}"
session_mode = "fresh"
+++
telemetry test
'''.encode()
    (w.base / "inbox" / "prompt.txt").write_bytes(raw)
    w.ingest()
    return w


def jsonl(*events):
    return b"".join(json.dumps(event).encode() + b"\n" for event in events)


def usage_file(w):
    return next((w.base / "reports" / "executions").glob("*/usage.json"))


def test_usage_complete_cached_and_associated(tmp_path):
    w = repo(tmp_path)
    stdout = jsonl(
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.completed", "usage": {"input_tokens": 12, "cached_input_tokens": 8, "output_tokens": 4, "reasoning_output_tokens": 2, "total_tokens": 16}},
    )
    w.execute(1, FakeExecutor(stdout=stdout))
    rec = w._state()["generations"]["1"]
    usage = json.loads(usage_file(w).read_text())
    assert usage["status"] == "complete"
    assert usage["run"]["cached_input_tokens"] == 8
    assert usage["thread_id"] == "thread-1"
    assert usage["generation"] == 1 and usage["prompt_sha256"] == rec["prompt_sha256"]
    assert usage["quota_before"] is None and usage["quota_after"] is None
    event = json.loads((w.base / "usage" / "events.jsonl").read_text())
    assert event["execution_id"] == rec["execution"]["execution_id"]


def test_usage_reasoning_absent_and_quota_unavailable(tmp_path):
    w = repo(tmp_path)
    w.execute(1, FakeExecutor(stdout=jsonl({"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}})))
    usage = json.loads(usage_file(w).read_text())
    assert usage["run"]["reasoning_output_tokens"] is None
    assert usage["quota_status"] == "unavailable"
    assert "slash-status" not in usage["sources"]


def test_usage_partial_and_multiple_observations_are_not_estimated(tmp_path):
    w = repo(tmp_path)
    stdout = jsonl(
        {"type": "turn.completed", "usage": {"input_tokens": 1}},
        {"type": "turn.completed", "usage": {"input_tokens": 9}},
    ) + b"broken\n"
    w.execute(1, FakeExecutor(stdout=stdout))
    usage = json.loads(usage_file(w).read_text())
    assert usage["status"] == "partial"
    assert usage["run"]["consistency"] == "disagree"
    assert usage["run"]["observations"][0]["source"] == "exec-jsonl"
    assert usage["run"]["observations"][0]["metrics"]["input_tokens"] == 1
    assert usage["run"]["observations"][1]["metrics"]["input_tokens"] == 9


def test_telemetry_parser_failure_does_not_break_lifecycle(tmp_path, monkeypatch):
    w = repo(tmp_path)
    import tools.atlas_agent.telemetry as telemetry
    def fail(path):
        raise ValueError("bad telemetry")
    monkeypatch.setattr(telemetry, "parse_exec_jsonl", fail)
    w.execute(1, FakeExecutor(stdout=b"not relevant"))
    assert w._state()["generations"]["1"]["status"] == "COMPLETED"
    assert json.loads(usage_file(w).read_text())["status"] == "unavailable"


def test_usage_never_persists_secret_fields(tmp_path):
    w = repo(tmp_path)
    w.execute(1, FakeExecutor(stdout=jsonl({"type": "turn.completed", "usage": {"input_tokens": 1}, "authorization": "secret", "api_key": "secret"})))
    execution = w._state()["generations"]["1"]["execution"]
    usage_text = (w.base / execution["report_dir"] / "usage.json").read_text()
    journal_text = (w.base / "usage" / "events.jsonl").read_text()
    assert "secret" not in usage_text and "secret" not in journal_text


def test_usage_history_has_one_event_per_execution(tmp_path):
    w = repo(tmp_path)
    w.execute(1, FakeExecutor(stdout=jsonl({"type": "turn.completed", "usage": {"input_tokens": 1}})))
    lines = (w.base / "usage" / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["schema"] == "atlas-agent-codex-usage-event/1"
    assert event["metrics"]["input_tokens"] == 1

def test_unknown_jsonl_events_are_not_interpreted(tmp_path):
    from tools.atlas_agent.telemetry import parse_exec_jsonl
    path=tmp_path/"stdout"; path.write_bytes(jsonl({"type":"future.magic","usage":{"input_tokens":999,"oauth_token":"sentinel"},"thread_id":"bad"}))
    observations,metadata,_=parse_exec_jsonl(path)
    assert observations==[] and metadata=={}

def test_each_usage_observation_keeps_its_thread(tmp_path):
    from tools.atlas_agent.telemetry import parse_exec_jsonl
    path=tmp_path/"stdout"; path.write_bytes(jsonl(
        {"type":"thread.started","thread_id":"A"},
        {"type":"turn.completed","usage":{"input_tokens":1}},
        {"type":"thread.started","thread_id":"B"},
        {"type":"turn.completed","usage":{"input_tokens":2}},
    ))
    observations,_,_=parse_exec_jsonl(path)
    assert [x["thread_id"] for x in observations]==["A","B"]

def test_oversized_jsonl_line_is_discarded_and_parser_resumes(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.telemetry import parse_exec_jsonl
    path=tmp_path/"stdout"
    oversized=json.dumps({"type":"thread.started","thread_id":"FAKE","padding":"x"*300}).encode()+b"\n"
    path.write_bytes(oversized+jsonl({"type":"thread.started","thread_id":"B"},{"type":"turn.completed","usage":{"input_tokens":7}}))
    observations, metadata, malformed=parse_exec_jsonl(path,max_line_bytes=64)
    assert malformed==1 and metadata["thread_id"]=="B"
    assert observations==[{"source":"exec-jsonl","thread_id":"B","metrics":{"input_tokens":7,"cached_input_tokens":None,"output_tokens":None,"reasoning_output_tokens":None,"total_tokens":None}}]
    assert CodexExecutor._session_id_from_stdout(path,max_line_bytes=64)=="B"

def test_telemetry_allow_list_drops_all_unknown_secret_metadata(tmp_path):
    w=repo(tmp_path)
    sentinel={"access_token":"SENTINEL","authorization":"SENTINEL","api_key":"SENTINEL","cookie":"SENTINEL","oauth_token":"SENTINEL","password":"SENTINEL","secret":"SENTINEL","arbitrary_metadata":"SENTINEL"}
    event={"type":"thread.started","thread_id":"thread-safe","model":"model-safe",**sentinel}
    w.execute(1,FakeExecutor(stdout=jsonl(event,{"type":"turn.completed","usage":{"input_tokens":1},**sentinel})))
    execution=w._state()["generations"]["1"]["execution"]
    text=(w.base/execution["report_dir"]/"usage.json").read_text()+"\n"+(w.base/"usage"/"events.jsonl").read_text()
    assert "SENTINEL" not in text
    record=json.loads((w.base/execution["report_dir"]/"usage.json").read_text())
    assert record["observed_model"]=="model-safe"

def test_telemetry_write_failure_interrupts_lifecycle(tmp_path, monkeypatch):
    w=repo(tmp_path)
    import tools.atlas_agent.workflow as workflow
    def fail(*args,**kwargs): raise OSError("disk telemetry write failed")
    monkeypatch.setattr(workflow,"collect_usage",fail)
    with __import__("pytest").raises(Exception,match="TELEMETRY_WRITE_FAILURE"):
        w.execute(1,FakeExecutor(observed_thread_id="telemetry-thread"))
    assert w._state()["generations"]["1"]["status"]=="INTERRUPTED"
    interrupted=next(event for event in reversed(w.journal.read()) if event["event"]=="RUN_INTERRUPTED")
    result=interrupted["payload"]["executor_result"]
    assert result["session_id"]=="telemetry-thread"
    assert result["execution_id"]==interrupted["payload"]["execution"]["execution_id"]
    assert result["started_at"] and result["finished_at"]
    w._preflight()

def test_usage_history_preserves_execution_action_checkpoint_model_and_threads(tmp_path):
    w=repo(tmp_path); first=FakeExecutor(stdout=jsonl({"type":"thread.started","thread_id":"thread-A"},{"type":"turn.completed","usage":{"input_tokens":1}})); first.model="requested-A"; w.execute(1,first)
    raw=(f"+++\nschema = \"atlas-agent-prompt/1\"\ngeneration = 2\nparent = 1\ncheckpoint = \"TELEMETRY-2\"\naction = \"patch_review\"\nexpected_head = \"{git(w.root,'rev-parse','HEAD')}\"\nsession_mode = \"fresh\"\n+++\nsecond\n").encode(); (w.base/"inbox"/"second.txt").write_bytes(raw); w.ingest()
    second=FakeExecutor(stdout=jsonl({"type":"thread.started","thread_id":"thread-B"},{"type":"turn.completed","usage":{"input_tokens":2}})); second.model="requested-B"; w.execute(2,second)
    events=[json.loads(line) for line in (w.base/"usage"/"events.jsonl").read_text().splitlines()]
    assert [(e["generation"],e["action"],e["checkpoint"],e["requested_model"],e["thread_id"]) for e in events] == [(1,"implementation","TELEMETRY","requested-A","thread-A"),(2,"patch_review","TELEMETRY-2","requested-B","thread-B")]
