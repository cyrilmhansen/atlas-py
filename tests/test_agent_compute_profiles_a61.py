"""Substantive A6.1 frozen-format and compute-profile qualification tests."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionSpec, ExecutorError, FakeExecutor
from tools.atlas_agent.policy import (
    PolicyError, SNAPSHOT_SCHEMA, load_policy, policy_config_sha256, resolve_policy, toml_dumps, validate_policy,
    validate_snapshot,
)
from tools.atlas_agent.prompt import PromptError, parse_prompt
from tools.atlas_agent.workflow import WorkflowError

from tests.codex_test_support import pinned_codex
from tests.test_agent_workflow_w221 import make_repo


ROOT = Path(__file__).parents[1]


def _prompt(action="implementation", *, schema=3, compute=None, model=None,
            session_mode="fresh", network=False):
    extra = ""
    if schema >= 2:
        extra += f"network_access = {'true' if network else 'false'}\n"
    if schema == 3 and compute is None:
        compute = "action-default"
    if compute is not None:
        extra += f'compute_profile = "{compute}"\n'
    raw = (
        "+++\n"
        f'schema = "atlas-agent-prompt/{schema}"\n'
        "generation = 1\nparent = \"genesis\"\ncheckpoint = \"a61\"\n"
        f'action = "{action}"\nexpected_head = "{"a" * 40}"\n'
        f'session_mode = "{session_mode}"\n' + extra + "+++\nbody\n"
    ).encode()
    return parse_prompt(raw)


def _policies():
    current = __import__("tomllib").loads(
        (ROOT / "atlas-agent-policy.toml").read_text()
    )
    p2 = deepcopy(current)
    p2["schema"] = "atlas-agent-policy/2"
    p2.pop("compute_profiles")
    p1 = deepcopy(p2)
    p1["schema"] = "atlas-agent-policy/1"
    for profile in p1["profiles"].values():
        if profile["executor"] == "codex":
            profile.pop("required_toolchains", None)
            profile.pop("writable_caches", None)
    validate_policy(p1)
    validate_policy(p2)
    return p1, p2, current


def test_policy_to_snapshot_epochs_are_exact():
    p1, p2, p3 = _policies()
    assert resolve_policy(p1, _prompt(schema=2))["schema"].endswith("/2")
    assert resolve_policy(p2, _prompt(schema=2))["schema"].endswith("/3")
    assert resolve_policy(p3, _prompt(schema=3))["schema"] == SNAPSHOT_SCHEMA


def test_policy_one_snapshot_two_is_a_positive_replay_before_mutation():
    p1, _, _ = _policies()
    snapshot = resolve_policy(p1, _prompt(schema=1))
    assert snapshot["schema"] == "atlas-agent-policy-snapshot/2"
    assert snapshot["policy_schema"] == "atlas-agent-policy/1"
    assert snapshot["codex_profile"]
    assert validate_snapshot(snapshot) is snapshot


def test_policy_two_snapshot_three_is_a_positive_capability_replay_before_mutation():
    _, p2, _ = _policies()
    snapshot = resolve_policy(p2, _prompt(schema=2))
    snapshot.update({
        "capability_plan_sha256": "a" * 64,
        "capability_archive_path": "reports/capabilities/execution.json",
        "capability_archive_sha256": "b" * 64,
    })
    assert snapshot["schema"] == "atlas-agent-policy-snapshot/3"
    assert validate_snapshot(snapshot) is snapshot


def test_policy_three_snapshot_four_is_a_positive_current_replay_before_mutation():
    _, _, p3 = _policies()
    snapshot = resolve_policy(p3, _prompt(schema=3))
    assert snapshot["schema"] == SNAPSHOT_SCHEMA
    assert snapshot["requested_compute_profile"] == "action-default"
    assert validate_snapshot(snapshot) is snapshot


def test_historical_snapshots_are_replayable_but_not_executable():
    p1, p2, p3 = _policies()
    executor = CodexExecutor(executable="/bin/true")
    for policy, prompt in ((p1, _prompt(schema=2)),
                           (p2, _prompt(schema=2))):
        snapshot = resolve_policy(policy, prompt)
        assert validate_snapshot(snapshot) is snapshot
        with pytest.raises(ExecutorError, match="POLICY_SNAPSHOT_NOT_EXECUTABLE"):
            executor._require_executable_snapshot(snapshot)
    current = resolve_policy(p3, _prompt(schema=3))
    assert validate_snapshot(current) is current
    assert executor._require_executable_snapshot(current) is current


@pytest.mark.parametrize("field", [
    "requested_compute_profile", "resolved_compute_profile",
    "required_toolchains", "writable_caches",
])
def test_frozen_snapshots_reject_a61_fields(field):
    p1, p2, p3 = _policies()
    for policy, prompt in ((p1, _prompt(schema=2)),
                           (p2, _prompt(schema=2))):
        snapshot = resolve_policy(policy, prompt)
        if field in {"required_toolchains", "writable_caches"} and policy is p2:
            continue  # capability lists are the defining /3 addition
        assert validate_snapshot(snapshot) is snapshot
        snapshot[field] = [] if "toolchains" in field or "caches" in field else "action-default"
        with pytest.raises(PolicyError):
            validate_snapshot(snapshot)


def test_snapshot_three_requires_capabilities_but_snapshot_four_manual_does_not():
    p1, p2, p3 = _policies()
    old = resolve_policy(p2, _prompt(schema=2))
    assert validate_snapshot(old) == old
    old.pop("required_toolchains")
    with pytest.raises(PolicyError):
        validate_snapshot(old)

    manual = resolve_policy(p3, _prompt("checkpoint", schema=2))
    assert validate_snapshot(manual) == manual
    manual["requested_compute_profile"] = "action-default"
    with pytest.raises(PolicyError):
        validate_snapshot(manual)


def test_a61_matrix_defaults_and_action_profile_provenance():
    _, _, policy = _policies()
    expected = {
        ("implementation", None): ("gpt-5.6-luna", "medium", "atlas-luna-local"),
        ("implementation", "sol-medium"): ("gpt-5.6-sol", "medium", "atlas-luna-local"),
        ("implementation", "astra-medium"): ("gpt-6-astra", "medium", "atlas-luna-local"),
        ("patch_review", None): ("gpt-5.6-sol", "high", "atlas-sol-local"),
        ("state_audit", None): ("gpt-5.6-sol", "high", "atlas-sol-local"),
    }
    for (action, compute), values in expected.items():
        snap = resolve_policy(policy, _prompt(action, compute=compute))
        assert (snap["requested_model"], snap["requested_reasoning_effort"],
                snap["codex_profile"]) == values
        assert snap["requested_compute_profile"] == (compute or "action-default")
    with pytest.raises(PolicyError):
        resolve_policy(policy, _prompt("patch_review", compute="luna-high"))


@pytest.mark.parametrize("action", ["implementation", "patch_review", "state_audit"])
def test_exact_compute_profile_action_matrix(action):
    _, _, policy = _policies()
    allowed = {
        "action-default": True,
        "luna-high": action == "implementation",
        "sol-medium": True,
        "astra-medium": True,
        "astra-high": True,
    }
    for compute, is_allowed in allowed.items():
        if is_allowed:
            snapshot = resolve_policy(policy, _prompt(action, compute=compute))
            assert validate_snapshot(snapshot) is snapshot
        else:
            with pytest.raises(PolicyError):
                resolve_policy(policy, _prompt(action, compute=compute))


def test_policy_three_model_reasoning_and_compute_action_set_tampering_fails_closed():
    _, _, policy = _policies()
    snapshot = resolve_policy(policy, _prompt("implementation"))
    assert validate_snapshot(snapshot) is snapshot
    for field, value in (
        ("requested_model", "gpt-6-astra"),
        ("requested_reasoning_effort", "low"),
        ("requested_compute_profile", "sol-medium"),
    ):
        mutated = deepcopy(snapshot)
        mutated[field] = value
        with pytest.raises(PolicyError):
            validate_snapshot(mutated)

    for field in ("luna-high", "sol-medium", "astra-medium", "astra-high"):
        mutated_policy = deepcopy(policy)
        mutated_policy["compute_profiles"][field]["actions"] = ["checkpoint"]
        with pytest.raises(PolicyError):
            validate_policy(mutated_policy)


def test_snapshot_four_tuple_tampering_fails_after_positive_base_validation():
    _, _, policy = _policies()
    base = resolve_policy(policy, _prompt("implementation", compute="astra-medium"))
    assert validate_snapshot(base) is base
    for field, value in (
        ("requested_compute_profile", "sol-medium"),
        ("resolved_compute_profile", "luna-high"),
        ("requested_model", "gpt-5.6-luna"),
        ("requested_reasoning_effort", "high"),
        ("codex_profile", "atlas-sol-local"),
    ):
        mutated = deepcopy(base)
        mutated[field] = value
        with pytest.raises(PolicyError):
            validate_snapshot(mutated)


@pytest.mark.parametrize(
    "action, mutation",
    [
        ("implementation",
         lambda value: value.update(sandbox_mode="read-only")),
        ("implementation",
         lambda value: value.update(session_storage="ephemeral")),
        ("patch_review",
         lambda value: value.update(sandbox_mode="workspace-write")),
        ("patch_review",
         lambda value: value.update(session_storage="ephemeral")),
        ("patch_review",
         lambda value: value.update(
             network_access=True,
             network_access_requested=True,
             web_search="live",
             codex_profile="atlas-sol-web")),
        ("state_audit",
         lambda value: value.update(
             network_access=True,
             network_access_requested=True,
             web_search="live",
             codex_profile="atlas-sol-web")),
        ("state_audit",
         lambda value: value.update(
             session_mode="reuse",
             session_mode_requested="reuse",
             session_mode_resolved="reuse",
             reused_from_execution_id="execution",
             requested_thread_id="thread",
             reuse_depth=1)),
        ("state_audit",
         lambda value: value.update(session_storage="persist")),
    ],
)
def test_snapshot_four_action_authority_rejects_forbidden_mutations(
        action, mutation):
    _, _, policy = _policies()
    base = resolve_policy(policy, _prompt(action))
    assert validate_snapshot(base) is base
    mutated = deepcopy(base)
    mutation(mutated)
    with pytest.raises(PolicyError):
        validate_snapshot(mutated)


@pytest.mark.parametrize("network", [False, True])
def test_snapshot_four_implementation_network_policy_forms_are_valid(network):
    _, _, policy = _policies()
    snapshot = resolve_policy(
        policy, _prompt("implementation", network=network))
    assert validate_snapshot(snapshot) is snapshot
    assert snapshot["network_access"] is network
    assert snapshot["network_access_requested"] is network


def test_default_action_compute_provenance_and_implementation_compute_profiles():
    _, _, policy = _policies()
    default = resolve_policy(policy, _prompt("implementation"))
    assert validate_snapshot(default) is default
    assert (default["requested_compute_profile"],
            default["resolved_compute_profile"],
            default["requested_model"],
            default["requested_reasoning_effort"]) == (
                "action-default", "action-default", "gpt-5.6-luna", "medium")
    for compute, model in (("sol-medium", "gpt-5.6-sol"),
                           ("astra-medium", "gpt-6-astra")):
        snapshot = resolve_policy(policy, _prompt("implementation",
                                                   compute=compute))
        assert validate_snapshot(snapshot) is snapshot
        assert snapshot["codex_profile"] == "atlas-luna-local"
        assert snapshot["requested_model"] == model


def test_snapshot_four_authority_and_manual_forbidden_fields_are_closed():
    _, _, policy = _policies()
    manual = resolve_policy(policy, _prompt("checkpoint", schema=2))
    assert validate_snapshot(manual) is manual
    for mutation in (
        lambda value: value.update(action="implementation"),
        lambda value: value.update(executor="codex"),
        lambda value: value.update(requested_compute_profile="action-default"),
        lambda value: value.update(resolved_compute_profile="action-default"),
        lambda value: value.update(codex_profile="atlas-luna-local"),
        lambda value: value.update(codex_binary_sha256="a" * 64),
        lambda value: value.update(asset_set_sha256="a" * 64),
        lambda value: value.update(prompt_set_sha256="a" * 64),
        lambda value: value.update(asset_version="v0.1.1"),
        lambda value: value.update(required_toolchains=[]),
        lambda value: value.update(writable_caches=[]),
        lambda value: value.update(capability_plan_sha256="a" * 64),
        lambda value: value.update(capability_archive_path="reports/capabilities/e.json"),
        lambda value: value.update(capability_archive_sha256="a" * 64),
    ):
        mutated = deepcopy(manual)
        mutation(mutated)
        with pytest.raises(PolicyError):
            validate_snapshot(mutated)


@pytest.mark.parametrize("action", ["implementation", "patch_review",
                                    "state_audit"])
def test_manual_snapshot_four_cannot_claim_a_codex_action(action):
    _, _, policy = _policies()
    base = resolve_policy(policy, _prompt("checkpoint", schema=2))
    assert validate_snapshot(base) is base
    mutated = deepcopy(base)
    mutated["action"] = action
    with pytest.raises(PolicyError):
        validate_snapshot(mutated)


def test_codex_cannot_claim_a_snapshot_four_checkpoint():
    _, _, policy = _policies()
    base = resolve_policy(policy, _prompt("implementation"))
    assert validate_snapshot(base) is base
    mutated = deepcopy(base)
    mutated["action"] = "checkpoint"
    with pytest.raises(PolicyError):
        validate_snapshot(mutated)


def test_snapshot_four_capability_names_hashes_and_paths_use_subsystem_shapes():
    _, _, policy = _policies()
    base = resolve_policy(policy, _prompt("implementation"))
    assert validate_snapshot(base) is base
    valid = deepcopy(base)
    valid.update({
        "required_toolchains": ["rust"],
        "writable_caches": ["cargo"],
        "capability_plan_sha256": "a" * 64,
        "capability_archive_path": "reports/capabilities/abc-123.json",
        "capability_archive_sha256": "b" * 64,
    })
    assert validate_snapshot(valid) is valid
    for field, value in (
        ("required_toolchains", ["rust/bin"]),
        ("writable_caches", ["."]),
        ("required_toolchains", [1]),
        ("capability_plan_sha256", "not-a-sha256"),
        ("capability_archive_sha256", "G" * 64),
        ("capability_archive_path", "../capabilities/abc.json"),
        ("capability_archive_path", "reports/capabilities/../abc.json"),
        ("capability_archive_path", "reports/capabilities"),
    ):
        mutated = deepcopy(valid)
        mutated[field] = value
        with pytest.raises(PolicyError):
            validate_snapshot(mutated)


def test_checkpoint_compute_profiles_are_rejected_when_read_from_durable_storage(
        tmp_path):
    raw = (
        "+++\n"
        'schema = "atlas-agent-prompt/3"\n'
        "generation = 1\nparent = \"genesis\"\ncheckpoint = \"a61\"\n"
        'action = "checkpoint"\nexpected_head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
        'session_mode = "fresh"\nnetwork_access = false\n'
        'compute_profile = "action-default"\n+++\nbody\n'
    ).encode()
    durable = tmp_path / "accepted-prompt.txt"
    durable.write_bytes(raw)
    with pytest.raises(PromptError, match="compute"):
        parse_prompt(durable.read_bytes())


def _executor_spec(tmp_path, snapshot):
    prompt_path = tmp_path / "prompt.txt"
    prompt_bytes = b"prompt\n"
    prompt_path.write_bytes(prompt_bytes)
    return ExecutionSpec(
        generation=1, prompt_sha256="a" * 64, action="implementation",
        prompt_path=prompt_path, repository_root=tmp_path,
        execution_id="execution", report_dir=tmp_path / "reports",
        policy_snapshot=snapshot, prompt_bytes=prompt_bytes,
        input_mode="bytes-v1",
        expected_input_sha256=__import__("hashlib").sha256(prompt_bytes).hexdigest(),
    )


@pytest.mark.parametrize("caller_model", [None, "gpt-5.6-luna"])
def test_caller_model_omitted_or_matching_is_accepted(tmp_path, caller_model):
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o700)
    executor, snapshot = pinned_codex(tmp_path, executable, model=caller_model)
    executor._sealed_runtime_fd = lambda value: os.open(os.devnull, os.O_RDONLY)
    executor._runtime_info = lambda value, fd: {"version": "test"}
    prepared = executor._prepare_execution(_executor_spec(tmp_path, snapshot))
    assert "--model" in prepared.command
    assert "gpt-5.6-luna" in prepared.command


def test_caller_model_mismatch_fails_closed(tmp_path):
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o700)
    executor, snapshot = pinned_codex(tmp_path, executable, model="gpt-6-astra")
    with pytest.raises(ExecutorError, match="POLICY_RESOLUTION_MISMATCH"):
        executor._prepare_execution(_executor_spec(tmp_path, snapshot))


def test_fast_is_independent_of_compute_profile(tmp_path):
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o700)
    executor, snapshot = pinned_codex(tmp_path, executable, service_tier="fast")
    snapshot = deepcopy(snapshot)
    snapshot.update({
        "requested_compute_profile": "astra-medium",
        "resolved_compute_profile": "astra-medium",
        "requested_model": "gpt-6-astra",
    })
    # The action/profile tuple is intentionally made coherent for this
    # command-construction check; service tier remains an independent switch.
    command = executor._build_command(_executor_spec(tmp_path, snapshot), snapshot)
    assert 'service_tier="fast"' in command
    assert "--model" in command and "gpt-6-astra" in command


def test_reuse_is_incompatible_across_compute_identities(tmp_path):
    _, workflow = make_repo(tmp_path)
    workflow.prompt_create("a61-first", "implementation", b"body\n",
                           compute_profile="astra-medium")
    workflow.ingest()
    workflow.execute(1, FakeExecutor(
            observed_thread_id="compute-thread",
            observed_model="gpt-6-astra",
            observed_reasoning="medium"))
    execution_id = workflow._state()["generations"]["1"]["execution"]["execution_id"]
    workflow.prompt_create(
        "a61-second", "implementation", b"body\n", session_mode="reuse",
        reuse_execution_id=execution_id, compute_profile="sol-medium")
    workflow.ingest()
    with pytest.raises(WorkflowError):
        workflow.execute(2, FakeExecutor(
                observed_thread_id="compute-thread",
                observed_model="gpt-5.6-sol",
                observed_reasoning="medium"))


def test_observed_model_and_reasoning_do_not_synthesize_compute_provenance(tmp_path):
    _, workflow = make_repo(tmp_path)
    workflow.prompt_create("a61-observed", "implementation", b"body\n",
                           compute_profile="astra-medium")
    workflow.ingest()
    workflow.execute(1, FakeExecutor(
            observed_thread_id="observed-thread",
            observed_model="gpt-6-astra",
            observed_reasoning="medium"))
    record = workflow._state()["generations"]["1"]
    assert record["execution"]["policy_snapshot"]["requested_compute_profile"] == "astra-medium"
    assert "observed_compute_profile" not in record["execution"]
    assert "observed_compute_profile" not in record["result"]


def test_prompt_create_rejects_checkpoint_compute_profile(tmp_path):
    _, workflow = make_repo(tmp_path)
    with pytest.raises(WorkflowError, match="COMPUTE_PROFILE_FORBIDDEN"):
        workflow.prompt_create("a61-checkpoint", "checkpoint", b"body\n",
                               compute_profile="action-default")


def test_only_current_pair_is_codex_execution_authority():
    p1, p2, p3 = _policies()
    executor = CodexExecutor(executable="/bin/true")
    for policy, prompt in ((p1, _prompt(schema=2)),
                           (p2, _prompt(schema=2)),
                           (p3, _prompt(schema=3))):
        snapshot = resolve_policy(policy, prompt)
        if policy is p3:
            assert executor._require_executable_snapshot(snapshot)["schema"] == SNAPSHOT_SCHEMA
        else:
            with pytest.raises(Exception):
                executor._require_executable_snapshot(snapshot)


@pytest.mark.parametrize("action", ["implementation", "patch_review", "state_audit"])
def test_astra_high_exact_resolution(action):
    _, _, policy = _policies()
    assert set(policy["compute_profiles"]) == {
        "luna-high", "sol-medium", "astra-medium", "astra-high",
    }
    snapshot = resolve_policy(policy, _prompt(action, compute="astra-high"))
    assert snapshot["requested_model"] == "gpt-6-astra"
    assert snapshot["requested_reasoning_effort"] == "high"
    assert snapshot["requested_compute_profile"] == "astra-high"
    assert snapshot["resolved_compute_profile"] == "astra-high"
    assert validate_snapshot(snapshot) is snapshot
    for field, value in (
        ("requested_model", "gpt-5.6-sol"),
        ("requested_reasoning_effort", "medium"),
        ("requested_compute_profile", "astra-medium"),
        ("resolved_compute_profile", "astra-medium"),
        ("requested_compute_profile", "astra-unknown"),
    ):
        mutated = deepcopy(snapshot)
        mutated[field] = value
        with pytest.raises(PolicyError):
            validate_snapshot(mutated)


def test_pre_astra_high_policy_replays_without_new_authority(tmp_path):
    _, _, policy = _policies()
    assert validate_policy(policy) is policy
    assert validate_policy(policy, historical=True) is policy
    resolve_policy(policy, _prompt(compute="astra-high"), for_new_execution=True)
    del policy["compute_profiles"]["astra-high"]
    original = deepcopy(policy)
    expected_hash = hashlib.sha256(toml_dumps(policy).encode()).hexdigest()
    assert validate_policy(policy, historical=True) is policy
    assert policy_config_sha256(policy, historical=True) == expected_hash
    with pytest.raises(PolicyError, match="POLICY_SCHEMA_INVALID"):
        validate_policy(policy)
    with pytest.raises(PolicyError, match="POLICY_SCHEMA_INVALID"):
        policy_config_sha256(policy)
    path = tmp_path / "policy.toml"
    path.write_text(toml_dumps(policy))
    with pytest.raises(PolicyError, match="POLICY_SCHEMA_INVALID"):
        load_policy(path)
    with pytest.raises(PolicyError, match="POLICY_SCHEMA_INVALID"):
        resolve_policy(policy, _prompt(compute="astra-medium"))
    for historical in (False, True):
        with pytest.raises(PolicyError, match="POLICY_SCHEMA_INVALID"):
            resolve_policy(policy, _prompt(compute="astra-medium"),
                           for_new_execution=True, historical=historical)
    snapshot = resolve_policy(policy, _prompt(compute="astra-medium"), historical=True)
    assert validate_snapshot(snapshot) is snapshot
    assert snapshot["policy_config_sha256"] == expected_hash
    assert snapshot["requested_reasoning_effort"] == "medium"
    with pytest.raises(PolicyError):
        resolve_policy(policy, _prompt(compute="astra-high"), historical=True)
    assert policy == original


def test_compute_matrix_rejects_unknown_profiles_and_partial_sets():
    _, _, policy = _policies()
    with pytest.raises(PolicyError):
        resolve_policy(policy, _prompt(compute="astra-unknown"))
    mutated = deepcopy(policy)
    mutated["compute_profiles"]["astra-unknown"] = deepcopy(
        mutated["compute_profiles"]["astra-high"])
    with pytest.raises(PolicyError):
        validate_policy(mutated)
    for name in ("luna-high", "sol-medium", "astra-medium"):
        mutated = deepcopy(policy)
        del mutated["compute_profiles"][name]
        with pytest.raises(PolicyError):
            validate_policy(mutated)


def test_archived_three_profile_execution_replays_after_extension(tmp_path, monkeypatch):
    _, _, policy = _policies()
    old_policy = deepcopy(policy)
    del old_policy["compute_profiles"]["astra-high"]
    # Simulate the validator in force before the extension only while creating
    # the historical execution. Replay below uses unmodified current code.
    def historical_validator(data, **kwargs):
        assert set(data["compute_profiles"]) == {
            "luna-high", "sol-medium", "astra-medium",
        }
        return validate_policy(data, historical=True)

    with monkeypatch.context() as historical_runtime:
        historical_runtime.setattr(
            "tools.atlas_agent.policy.validate_policy", historical_validator)
        repo, workflow = make_repo(tmp_path, policy_text=toml_dumps(old_policy))
        workflow.prompt_create("before-astra-high", "implementation", b"body\n",
                               compute_profile="astra-medium")
        workflow.ingest()
        workflow.execute(1, FakeExecutor(
            observed_thread_id="historical-compute-thread",
            observed_model="gpt-6-astra", observed_reasoning="medium"))
    before = deepcopy(workflow._state()["generations"]["1"])
    assert before["status"] == "COMPLETED"
    execution = before["execution"]
    archive = workflow.base / execution["historical_policy_path"]
    original_bytes = archive.read_bytes()
    assert json.loads(original_bytes) == old_policy
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    assert execution["historical_policy_sha256"] == original_hash
    expected_semantic_hash = hashlib.sha256(toml_dumps(old_policy).encode()).hexdigest()
    assert execution["policy_snapshot"]["policy_config_sha256"] == expected_semantic_hash
    (repo / "atlas-agent-policy.toml").write_text(toml_dumps(policy))
    assert load_policy(repo / "atlas-agent-policy.toml") == policy
    (workflow.base / "state.json").unlink()
    rebuilt = workflow.rebuild()
    assert rebuilt["generations"]["1"] == before
    assert archive.read_bytes() == original_bytes
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == original_hash
