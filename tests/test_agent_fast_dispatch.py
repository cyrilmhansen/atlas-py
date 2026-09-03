import hashlib

from tools.atlas_agent import cli
from tools.atlas_agent.bubblewrap import AtlasBubblewrapExecutor
from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionSpec, ExecutorError, FakeExecutor, PreparedExecution

from tests.codex_test_support import pinned_codex


def _spec(tmp_path, snapshot, generation=1):
    prompt = tmp_path / "prompt"
    prompt.write_text("work\n")
    return ExecutionSpec(
        generation, "a" * 64, "implementation", prompt, tmp_path,
        f"execution-{generation}", tmp_path / f"report-{generation}", tmp_path,
        policy_snapshot=snapshot, input_mode="legacy",
    )


def test_fast_command_is_once_for_fresh_and_resume_and_does_not_touch_config(tmp_path):
    executable = tmp_path / "codex"
    executable.write_text('#!/bin/sh\n[ "$1" = --version ] && echo test && exit 0\n')
    executable.chmod(0o700)
    executor, snapshot = pinned_codex(tmp_path, executable, service_tier="fast")
    config = executor.codex_home / "config.toml"
    before = hashlib.sha256(config.read_bytes()).hexdigest()

    fresh = executor.prepare_execution(_spec(tmp_path, snapshot)).command
    reuse = dict(snapshot, session_mode="reuse", reused_from_execution_id="e",
                 requested_thread_id="thread", reuse_depth=1)
    resumed = executor.prepare_execution(_spec(tmp_path, reuse, 2)).command

    assert fresh.count('service_tier="fast"') == 1
    assert resumed.count('service_tier="fast"') == 1
    assert hashlib.sha256(config.read_bytes()).hexdigest() == before
    assert executor._build_command(_spec(tmp_path, snapshot), snapshot).count(
        'service_tier="fast"') == 1


def test_normal_command_omits_fast_override(tmp_path):
    executable = tmp_path / "codex"
    executable.write_text('#!/bin/sh\n[ "$1" = --version ] && echo test && exit 0\n')
    executable.chmod(0o700)
    executor, snapshot = pinned_codex(tmp_path, executable)
    command = executor.prepare_execution(_spec(tmp_path, snapshot)).command
    assert 'service_tier="fast"' not in command


def test_normal_and_invalid_service_tier_are_safe():
    executor = CodexExecutor(service_tier=None)
    assert executor.service_tier is None
    try:
        CodexExecutor(service_tier="arbitrary")._validate_policy()
    except ExecutorError as error:
        assert str(error) == "INVALID_SERVICE_TIER"
    else:
        raise AssertionError("invalid service tier was accepted")


def test_bubblewrap_inherits_fast_command_and_cli_passes_fast(monkeypatch):
    assert AtlasBubblewrapExecutor._build_command is CodexExecutor._build_command
    seen = {}

    class FakeWorkflow:
        def __init__(self):
            pass

        def dispatch(self, executor, observer=None):
            seen["tier"] = executor.service_tier

    monkeypatch.setattr(cli, "Workflow", FakeWorkflow)
    real_init = AtlasBubblewrapExecutor.__init__

    def recording_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        seen["constructed_tier"] = self.service_tier

    # Keep the real Bubblewrap object; only avoid making dispatch do any work.
    monkeypatch.setattr(AtlasBubblewrapExecutor, "__init__", recording_init)
    cli.main(["dispatch", "--fast"])
    assert seen["tier"] == "fast"
    assert seen["constructed_tier"] == "fast"


def test_execute_cli_fast_and_default_construct_real_executor(monkeypatch):
    seen = []

    class FakeWorkflow:
        def execute(self, generation, executor):
            seen.append((generation, executor.service_tier))

    real_init = AtlasBubblewrapExecutor.__init__

    def recording_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(cli, "Workflow", FakeWorkflow)
    monkeypatch.setattr(AtlasBubblewrapExecutor, "__init__", recording_init)
    cli.main(["execute", "7", "--fast"])
    cli.main(["execute", "8"])
    assert seen == [(7, "fast"), (8, None)]


def test_real_bubblewrap_codex_argv_fast_fresh_and_resume_and_standard(tmp_path):
    # This is the production AtlasBubblewrapExecutor, not a recording fake.
    executor = AtlasBubblewrapExecutor(
        executable="/bin/true", bwrap="/bin/true",
        sandbox="workspace-write", codex_home=tmp_path / "home",
        service_tier="fast",
    )
    fresh_snapshot = dict(_command_snapshot(), session_mode="fresh")
    reuse_snapshot = dict(
        fresh_snapshot, session_mode="reuse", requested_thread_id="thread-A",
    )

    fresh = executor._build_command(_spec(tmp_path, fresh_snapshot), fresh_snapshot)
    resume = executor._build_command(_spec(tmp_path, reuse_snapshot, 2), reuse_snapshot)
    assert list(fresh)[3:5] == ["exec", "--json"]
    assert list(resume)[3:6] == ["exec", "resume", "--json"]
    assert sum(x == "-c" and i + 1 < len(fresh) and fresh[i + 1] == 'service_tier="fast"'
               for i, x in enumerate(fresh)) == 1
    assert sum(x == "-c" and i + 1 < len(resume) and resume[i + 1] == 'service_tier="fast"'
               for i, x in enumerate(resume)) == 1
    assert resume[-2:] == ("thread-A", "-")

    standard = AtlasBubblewrapExecutor(
        executable="/bin/true", bwrap="/bin/true",
        sandbox="workspace-write", codex_home=tmp_path / "home",
    )
    standard_argv = standard._build_command(
        _spec(tmp_path, fresh_snapshot), fresh_snapshot
    )
    assert 'service_tier="fast"' not in standard_argv


def _command_snapshot():
    return {
        "schema": "atlas-agent-policy-snapshot/2",
        "action": "implementation", "codex_profile": "atlas-luna-local",
        "requested_reasoning_effort": "medium", "web_search": "disabled",
        "session_storage": "persist",
    }


class _ReuseCapturingExecutor(FakeExecutor):
    def __init__(self, *, service_tier=None, **kwargs):
        super().__init__(**kwargs)
        self.service_tier = service_tier
        self.prepared_specs = []

    def prepare_execution(self, spec):
        self.prepared_specs.append(spec)
        prepared = super().prepare_execution(spec)
        thread = spec.policy_snapshot.get("requested_thread_id") if spec.policy_snapshot else None
        command = ("fake-executor", "resume", thread) if thread else prepared.command
        return PreparedExecution(
            spec, prepared.executor, command, prepared.version,
            prepared.permission_envelope, prepared.policy_snapshot,
        )


def _run_reuse_pair(tmp_path, first_fast, second_fast):
    from tests.test_agent_workflow_w221 import accepted, make_repo

    _, workflow = make_repo(tmp_path)
    accepted(workflow)
    first = _ReuseCapturingExecutor(
        service_tier="fast" if first_fast else None,
        observed_thread_id="thread-A", observed_model="gpt-5.6-luna",
        observed_reasoning="medium",
    )
    workflow.execute(1, first)
    first_owner = workflow._state()["generations"]["1"]["execution"]
    execution_id = first_owner["execution_id"]
    accepted(workflow, generation=2, session="reuse", target=execution_id)
    second = _ReuseCapturingExecutor(
        service_tier="fast" if second_fast else None,
        observed_thread_id="thread-A", observed_model="gpt-5.6-luna",
        observed_reasoning="medium",
    )
    workflow.execute(2, second)
    return workflow, first_owner, second


def test_standard_to_fast_reuse_is_same_thread_and_fast_is_not_policy_identity(tmp_path):
    workflow, first, second = _run_reuse_pair(tmp_path, False, True)
    owner = workflow._state()["generations"]["2"]["execution"]
    snapshot = owner["policy_snapshot"]
    assert snapshot["session_mode"] == "reuse"
    assert snapshot["reused_from_execution_id"] == first["execution_id"]
    assert snapshot["requested_thread_id"] == "thread-A"
    assert second.prepared_specs[0].policy_snapshot["requested_thread_id"] == "thread-A"
    assert second.prepared_specs[0].policy_snapshot["session_mode"] == "reuse"
    assert second.service_tier == "fast"
    assert owner["service_tier"] == "fast"
    result = workflow._execution_result(workflow._state()["generations"]["2"])
    terminal = workflow._state()["generations"]["2"]["result"]
    assert result["session_id"] == "thread-A"
    assert terminal["observed_thread_id"] == "thread-A"
    assert terminal["freshness_verification"] == "deferred"
    assert first["policy_snapshot"]["session_mode"] == "fresh"
    assert {k: snapshot[k] for k in ("action", "profile", "executor", "requested_model",
                                      "codex_profile")} == {
        k: first["policy_snapshot"][k] for k in
        ("action", "profile", "executor", "requested_model", "codex_profile")
    }


def test_fast_to_standard_reuse_is_same_thread(tmp_path):
    workflow, first, second = _run_reuse_pair(tmp_path, True, False)
    owner = workflow._state()["generations"]["2"]["execution"]
    assert first["service_tier"] == "fast"
    assert "service_tier" not in owner
    assert owner["policy_snapshot"]["session_mode"] == "reuse"
    assert owner["policy_snapshot"]["reused_from_execution_id"] == first["execution_id"]
    assert owner["policy_snapshot"]["requested_thread_id"] == "thread-A"
    assert second.prepared_specs[0].policy_snapshot["requested_thread_id"] == "thread-A"
    result = workflow._execution_result(workflow._state()["generations"]["2"])
    assert result["session_id"] == "thread-A"
    assert workflow._state()["generations"]["2"]["result"]["observed_thread_id"] == "thread-A"


def test_fast_is_presented_and_durable_but_not_a_reuse_dimension(capsys, tmp_path):
    cli.DispatchPresenter().event({
        "kind": "dispatch_started", "generation": 1, "action": "implementation",
        "session_mode": "fresh", "service_tier": "fast",
        "permission_envelope": {},
    })
    assert "service fast" in capsys.readouterr().out

    from tests.test_agent_workflow_w221 import accepted, make_repo
    _, workflow = make_repo(tmp_path)
    accepted(workflow)

    class FastFake(FakeExecutor):
        service_tier = "fast"

    workflow.execute(1, FastFake(observed_thread_id="thread"))
    execution = workflow._state()["generations"]["1"]["execution"]
    assert execution["service_tier"] == "fast"
    assert "service_tier" not in execution["policy_snapshot"]
