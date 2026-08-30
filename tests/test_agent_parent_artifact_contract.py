"""Generation-4 contract tests for canonical parent provenance."""
import hashlib
import json

import pytest

from test_agent_operator_ergonomics import CodexFake, agent, jsonl
from test_agent_workflow_w221 import POLICY, accepted, make_repo
from tools.atlas_agent.journal import Journal, JournalError, canonical, decode_context_supplement, encode_context_supplement
from tools.atlas_agent.workflow import WorkflowError


def _run(w, generation=1):
    accepted(w, generation=generation)
    w.execute(generation, CodexFake(stdout=jsonl({"type": "thread.started", "thread_id": "t"}, agent("done")), observed_thread_id="t"))


def _rehash(path, mutate):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    mutate(rows); previous="0"*64
    for row in rows:
        row["previous_event_sha256"]=previous
        body=dict(row); body.pop("event_sha256",None)
        row["event_sha256"]=hashlib.sha256(canonical(body).encode()).hexdigest(); previous=row["event_sha256"]
    path.write_text("".join(canonical(row)+"\n" for row in rows))


def test_canonical_forms_round_trip_and_checkpoint_has_no_execution_metadata():
    for form in (
        {"kind":"none"},
        {"kind":"execution","generation":4,"action":"implementation","status":"COMPLETED","execution_id":"e-1","thread_id":"t-1","report_available":True},
        {"kind":"checkpoint","generation":4,"action":"checkpoint","status":"COMPLETED","commit":"a"*40},
    ):
        encoded=encode_context_supplement(form)
        assert encode_context_supplement(decode_context_supplement(encoded)) == encoded
    checkpoint=encode_context_supplement({"kind":"checkpoint","generation":4,"action":"checkpoint","status":"COMPLETED","commit":"a"*40})
    assert "report:" not in checkpoint and "execution_id:" not in checkpoint and "thread_id:" not in checkpoint


def test_invalid_mixed_parent_forms_and_report_generation_are_rejected():
    base={"kind":"execution","generation":4,"action":"implementation","status":"COMPLETED","report_available":True}
    with pytest.raises(JournalError):
        decode_context_supplement(encode_context_supplement(base)+"- commit: "+"a"*40+"\n")
    with pytest.raises(JournalError):
        decode_context_supplement(encode_context_supplement(base).replace("report 4", "report 5"))


def test_generated_context_is_bounded_and_excludes_report_contents(tmp_path):
    _, w=make_repo(tmp_path); _run(w)
    accepted(w, generation=2)
    context=w._parent_context(w._state(), 2)[0]
    assert len(context)<=4096
    assert b"done" not in context


def test_context_paths_are_bound_to_execution_identity(tmp_path):
    _, w=make_repo(tmp_path); _run(w)
    owner=w._state()["generations"]["1"]["execution"]
    def mutate(rows):
        for row in rows:
            if row["event"]=="TRANSITION_PREPARED" and "execution" in row["payload"]:
                row["payload"]["execution"]["context_path"]="reports/contexts/another.txt"; return
    _rehash(w.journal.path, mutate)
    with pytest.raises(JournalError): Journal(w.journal.path).read()
    assert owner["context_path"].startswith("reports/contexts/")


def test_initialization_validation_epoch_rejects_boolean(tmp_path):
    _, w = make_repo(tmp_path)
    rows = [json.loads(line) for line in w.journal.path.read_text().splitlines()]
    rows[0]["payload"]["validation_epoch"] = True
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        body = dict(row); body.pop("event_sha256", None)
        row["event_sha256"] = hashlib.sha256(canonical(body).encode()).hexdigest()
        previous = row["event_sha256"]
    w.journal.path.write_text("".join(canonical(row) + "\n" for row in rows))
    with pytest.raises(JournalError, match="validation epoch"):
        Journal(w.journal.path).read()



@pytest.mark.parametrize(
    "target",
    ["PROMPT_ACCEPTED", "TRANSITION_PREPARED", "RUN_STARTED"],
)
def test_v2_network_request_provenance_cannot_be_omitted(tmp_path, target):
    _, w=make_repo(tmp_path)
    accepted(w, network=True)
    w.execute(
        1,
        CodexFake(
            stdout=jsonl(
                {"type":"thread.started","thread_id":"network-thread"},
                agent("done"),
            ),
            observed_thread_id="network-thread",
        ),
    )

    def mutate(rows):
        for row in rows:
            if row["event"] != target:
                continue
            if (
                target == "TRANSITION_PREPARED"
                and row["payload"].get("logical_event") != "RUN_STARTED"
            ):
                continue
            row["payload"].pop("network_access", None)
            return
        raise AssertionError(f"{target} not found")

    _rehash(w.journal.path, mutate)

    with pytest.raises(
        JournalError,
        match="network archive|network provenance|network request",
    ):
        Journal(w.journal.path).read()


def test_v2_network_request_must_match_archived_prompt(tmp_path):
    _, w=make_repo(tmp_path)
    accepted(w, network=True)

    def mutate(rows):
        for row in rows:
            if row["event"]=="PROMPT_ACCEPTED":
                row["payload"]["network_access"]=False
                return
        raise AssertionError("PROMPT_ACCEPTED not found")

    _rehash(w.journal.path, mutate)

    with pytest.raises(JournalError, match="prompt network archive mismatch"):
        Journal(w.journal.path).read()

def test_recovery_rejects_false_effective_hash_before_publication(tmp_path):
    _, w=make_repo(tmp_path); _run(w)
    owner=w._state()["generations"]["1"]["execution"]
    def mutate(rows):
        for row in rows:
            if row["event"] in {"TRANSITION_PREPARED", "RUN_STARTED"} and "execution" in row["payload"]:
                row["payload"]["execution"]["effective_prompt_sha256"]="b"*64
    _rehash(w.journal.path, mutate)
    with pytest.raises(Exception): w.recover()


def test_complete_stripped_modern_history_cannot_be_reclassified_as_legacy(tmp_path):
    """The reviewer's exact removable-marker shape must fail closed."""
    _, w = make_repo(tmp_path); _run(w)
    rows = [json.loads(line) for line in w.journal.path.read_text().splitlines()]
    for row in rows:
        payload = row["payload"]
        for container in (payload, payload.get("execution"), payload.get("result"), payload.get("executor_result")):
            if isinstance(container, dict):
                for key in ("provenance_version", "execution_input_sha256", "report_provenance", "prompt_schema"):
                    container.pop(key, None)
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        body = dict(row); body.pop("event_sha256", None)
        row["event_sha256"] = hashlib.sha256(canonical(body).encode()).hexdigest(); previous = row["event_sha256"]
    w.journal.path.write_text("".join(canonical(row) + "\n" for row in rows))
    with pytest.raises(JournalError): Journal(w.journal.path).read()


def test_interrupted_foreign_executor_identity_is_not_projected_to_child(tmp_path):
    from tools.atlas_agent.executor import FakeExecutor
    from tools.atlas_agent.workflow import WorkflowError
    _, w = make_repo(tmp_path); accepted(w)

    class Foreign(FakeExecutor):
        def run_execution(self, prepared):
            result = super().run_execution(prepared)
            from dataclasses import replace
            return replace(result, execution_id="foreign-execution", session_id="foreign-thread")

    with pytest.raises(WorkflowError): w.execute(1, Foreign())
    w._state_file().unlink(); state = w.rebuild()
    assert state["generations"]["1"]["status"] == "INTERRUPTED"
    accepted(w, generation=2)
    context, _ = w._parent_context(state, 2)
    assert b"foreign-execution" not in context and b"foreign-thread" not in context


def test_historical_parent_claim_survives_mutable_parent_output(tmp_path, monkeypatch):
    _, w = make_repo(tmp_path); _run(w, 1); accepted(w, generation=2)
    parent = w._state()["generations"]["1"]["execution"]
    (w.base / parent["report_dir"] / "stdout.log").write_text("mutable replacement\n")
    result_path = w.base / parent["report_dir"] / "result.json"
    result = json.loads(result_path.read_text())
    result["report_provenance"] = {"status": "unavailable"}
    result_path.write_text(json.dumps(result) + "\n")
    from dataclasses import replace
    class Capturing(CodexFake):
        def prepare_execution(self, spec):
            self.input_bytes = spec.prompt_bytes
            return super().prepare_execution(spec)
    child = Capturing(stdout=jsonl({"type": "thread.started", "thread_id": "child"}, agent("done")), observed_thread_id="child")
    w.execute(2, child)
    assert b"generation: 1" in child.input_bytes
    assert b"status: COMPLETED" in child.input_bytes
    assert b"thread_id: t" in child.input_bytes
    assert b"report: available" in child.input_bytes
    assert b"report command: python -m tools.atlas_agent report 1" in child.input_bytes


def test_keyboard_interrupt_reason_and_status_survive_journal_replay(tmp_path):
    from tools.atlas_agent.executor import FakeExecutor
    from tools.atlas_agent.workflow import WorkflowError
    _, w = make_repo(tmp_path); accepted(w)
    class Interrupted(FakeExecutor):
        def run_execution(self, prepared):
            self.launched += 1
            raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): w.execute(1, Interrupted())
    w._state_file().unlink()
    rebuilt = w.rebuild()
    assert rebuilt["generations"]["1"]["status"] == "INTERRUPTED"
    assert w._interruption_reason(1) == "KEYBOARD_INTERRUPT"


def test_policy_interruption_replays_available_report_and_rejects_tampering(tmp_path):
    import hashlib
    import re
    import sys

    executable = tmp_path / "reporting-codex.py"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import pathlib, sys, json, subprocess\n"
        "if '--version' in sys.argv: print('contract-codex'); raise SystemExit(0)\n"
        "pathlib.Path('a').write_text('policy violation'); subprocess.run(['git','add','a'], check=True)\n"
        "print(json.dumps({'type':'thread.started','thread_id':'policy-thread'}), flush=True)\n"
        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'final report'}}), flush=True)\n"
    )
    executable.chmod(0o755)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    config = codex_home / "config.toml"
    catalog = codex_home / "models-atlas-shell-only.json"
    profile = codex_home / "atlas-luna-local.config.toml"

    config.write_text("suppress_unstable_features_warning = true\n")
    catalog.write_text('{"models":[]}\n')
    profile.write_text(
        'model = "gpt-5.6-luna"\n'
        '[features]\n'
        'apps = false\n'
        'multi_agent = false\n'
        '[features.tool_registry]\n'
        'allowed_tools = ["exec_command", "write_stdin", "apply_patch"]\n'
    )

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    # This integration test deliberately injects a fake Codex executable.
    # Give that fixture a self-contained pinned Atlas runtime rather than
    # weakening production runtime-identity enforcement.
    policy = POLICY
    start = policy.index("[profiles.implementation]")
    end = policy.index("\n[profiles.", start + 1)
    block = policy[start:end]

    replacements = {
        "codex_binary_sha256": sha(executable),
        "codex_config_sha256": sha(config),
        "codex_catalog_sha256": sha(catalog),
        "codex_profile_local_sha256": sha(profile),
    }
    for key, value in replacements.items():
        block, count = re.subn(
            rf'^{key} = "[0-9a-f]{{64}}"$',
            f'{key} = "{value}"',
            block,
            count=1,
            flags=re.MULTILINE,
        )
        assert count == 1

    policy = policy[:start] + block + policy[end:]

    # The pinned fixture policy must exist before the repository commit and
    # Workflow.init(), so every durable witness sees the final policy.
    repo, w = make_repo(tmp_path, policy_text=policy)

    accepted(w)

    from tools.atlas_agent.codex_executor import CodexExecutor
    executor = CodexExecutor(
        executable=str(executable),
        timeout_seconds=3,
        codex_home=codex_home,
    )
    with pytest.raises(WorkflowError, match="REPOSITORY_POLICY_VIOLATION"):
        w.execute(1, executor)
    w._state_file().unlink(); state = w.rebuild()
    owner = state["generations"]["1"]["execution"]
    assert state["generations"]["1"]["status"] == "INTERRUPTED"
    assert state["generations"]["1"]["result"]["report_provenance"]["status"] == "available"
    assert w.report(1) == "final report"
    report = w.base / owner["report_dir"] / "stdout.log"
    records = [json.loads(line) for line in report.read_text().splitlines()]
    records.append({"type": "item.completed", "item": {"type": "agent_message", "text": "tampered report"}})
    report.write_text("".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records))
    with pytest.raises(WorkflowError, match="provenance|REPORT"):
        w.report(1)


def test_interrupted_replay_retains_terminal_report_and_canonical_executor_identity(tmp_path):
    from tools.atlas_agent.executor import FakeExecutor
    _, w = make_repo(tmp_path); accepted(w)
    with pytest.raises(WorkflowError, match="EXECUTOR_TIMEOUT"):
        w.execute(1, FakeExecutor(timed_out=True, observed_thread_id="canonical-thread"))
    w._state_file().unlink(); state = w.rebuild()
    record = state["generations"]["1"]
    assert record["status"] == "INTERRUPTED"
    assert record["execution"]["execution_id"] == record["execution_result"]["execution_id"]
    assert record["execution_result"]["session_id"] == "canonical-thread"
    assert record["result"]["report_provenance"]["status"] == "unavailable"
