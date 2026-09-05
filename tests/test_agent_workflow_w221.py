import hashlib, json, subprocess
from pathlib import Path

import pytest

from tools.atlas_agent.executor import FakeExecutor
from tools.atlas_agent.policy import PolicyError, load_policy, policy_config_sha256, resolve_policy, validate_snapshot
from tools.atlas_agent.prompt import PromptError, parse_prompt
from tools.atlas_agent.workflow import Workflow, WorkflowError


ROOT = Path(__file__).parents[1]
POLICY = (ROOT / "atlas-agent-policy.toml").read_text()


def git(path, *args):
    return subprocess.check_output(["git", *args], cwd=path, text=True).strip()


def make_repo(tmp_path, policy=True, project_config=False, policy_text=None, dirty_tracked=None):
    repo = tmp_path / "repo"; repo.mkdir(parents=True)
    git(repo, "init", "-q"); git(repo, "config", "user.email", "t@e"); git(repo, "config", "user.name", "t")
    (repo / "a").write_text("a")
    (repo / "atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    if policy:
        (repo / "atlas-agent-policy.toml").write_text(
            POLICY if policy_text is None else policy_text
        )
    if project_config:
        (repo/".codex").mkdir(); (repo/".codex"/"config.toml").write_text("hooks = []\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "fixture")
    if dirty_tracked is not None:
        (repo / "a").write_text(dirty_tracked)
    w=Workflow(repo); w.init(); return repo,w


def prompt(w, generation=1, action="implementation", session="fresh", network=False, target=None, schema=2):
    fields=[f'schema = "atlas-agent-prompt/{schema}"',f"generation = {generation}",f"parent = {'\"genesis\"' if generation == 1 else generation - 1}",f'checkpoint = "W221-{generation}"',f'action = "{action}"',f'expected_head = "{git(w.root, "rev-parse", "HEAD")}"',f'session_mode = "{session}"']
    if schema == 2:
        fields += [f"network_access = {'true' if network else 'false'}"]
        if target is not None: fields.append(f'reuse_execution_id = "{target}"')
    raw=("+++\n"+"\n".join(fields)+"\n+++\nW2.2.1\n").encode()
    (w.base/"inbox"/f"g{generation}.txt").write_bytes(raw); return raw


def accepted(w, **kwargs):
    raw=prompt(w, **kwargs); w.ingest(); return raw


def test_sandbox_descriptor_failure_does_not_orphan_policy_archive(tmp_path):
    _, w = make_repo(tmp_path)
    accepted(w)

    class DescriptorFailure(FakeExecutor):
        def sandbox_descriptor(self):
            raise RuntimeError("sandbox setup failed")

    with pytest.raises(RuntimeError, match="sandbox setup failed"):
        w.execute(1, DescriptorFailure())

    policies = w.base / "reports" / "policies"
    assert not policies.exists() or not list(policies.iterdir())
    events = w.journal.read()
    assert not any(event["event"] == "RUN_STARTED" for event in events)
    assert not any(
        event["event"] == "TRANSITION_PREPARED"
        and "execution" in event["payload"]
        for event in events
    )
    assert w._state()["generations"]["1"]["status"] == "ACCEPTED"
    w._preflight()

    w.execute(1, FakeExecutor(observed_thread_id="normal-thread"))
    assert w._state()["generations"]["1"]["status"] == "COMPLETED"


def test_policy_valid_closed_and_hash_semantics(tmp_path):
    path=tmp_path/"policy.toml"; path.write_text(POLICY); data=load_policy(path); first=policy_config_sha256(data)
    equivalent=path.read_text().replace('schema = "atlas-agent-policy/1"','schema = "atlas-agent-policy/1" # same').replace('max_hot_reuse_hops = 3','max_hot_reuse_hops=3')
    path.write_text(equivalent); assert policy_config_sha256(load_policy(path))==first
    path.write_text(equivalent.replace('network_default = false','network_default = true',1)); assert policy_config_sha256(load_policy(path))!=first


def test_policy_model_split_and_implementation_lifecycle_are_exact():
    policy=load_policy(ROOT/"atlas-agent-policy.toml")
    implementation=policy["profiles"]["implementation"]
    assert (implementation["model"],implementation["reasoning_effort"])==("gpt-5.6-luna","medium")
    assert implementation["allowed_session_modes"]==["fresh","reuse"]
    assert implementation["sandbox"]=="workspace-write"
    assert (implementation["network_default"],implementation["network_override"])==(False,"explicit")
    for name in ("patch_review","state_audit"):
        profile=policy["profiles"][name]
        assert (profile["model"],profile["reasoning_effort"])==("gpt-5.6-sol","high")
    assert policy["profiles"]["state_audit"]["allowed_session_modes"]==["fresh"]
    assert policy["profiles"]["checkpoint"]=={"executor":"manual","allowed_session_modes":["fresh"]}

    def resolved(action,session="fresh",network=False):
        target='reuse_execution_id = "historical-execution"\n' if session=="reuse" else ""
        raw=f'+++\nschema = "atlas-agent-prompt/2"\ngeneration = 1\nparent = "genesis"\ncheckpoint = "policy"\naction = "{action}"\nexpected_head = "{"a"*40}"\nsession_mode = "{session}"\nnetwork_access = {str(network).lower()}\n{target}+++\n'.encode()
        return resolve_policy(policy,parse_prompt(raw))

    fresh=resolved("implementation")
    reuse=resolved("implementation","reuse")
    enabled=resolved("implementation",network=True)
    assert (fresh["requested_model"],fresh["requested_reasoning_effort"])==("gpt-5.6-luna","medium")
    assert (fresh["session_mode"],reuse["session_mode"])==("fresh","reuse")
    assert fresh["sandbox_mode"]=="workspace-write"
    assert fresh["network_access"] is False and enabled["network_access"] is True
    assert fresh["codex_profile"]=="atlas-luna-local" and fresh["web_search"]=="disabled"
    assert enabled["codex_profile"]=="atlas-luna-web" and enabled["web_search"]=="live"
    for action in ("patch_review","state_audit"):
        snapshot=resolved(action)
        assert (snapshot["requested_model"],snapshot["requested_reasoning_effort"])==("gpt-5.6-sol","high")
        assert snapshot["codex_profile"]=="atlas-sol-local" and snapshot["web_search"]=="disabled"


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema="wrong"),
    lambda d: d["profiles"].pop("checkpoint"),
    lambda d: d["profiles"].update(extra=d["profiles"]["implementation"]),
])
def test_policy_schema_rejects_closed_mutations(tmp_path, mutation):
    path=tmp_path/"policy.toml"; path.write_text(POLICY); data=load_policy(path); mutation(data); path.write_text("schema = \"wrong\"\n")
    with pytest.raises(PolicyError): load_policy(path)


def test_prompt_v2_rules_and_v1_compatibility():
    head="a"*40
    base=f"+++\nschema = \"atlas-agent-prompt/2\"\ngeneration = 1\nparent = \"genesis\"\ncheckpoint = \"x\"\naction = \"implementation\"\nexpected_head = \"{head}\"\nsession_mode = \"fresh\"\nnetwork_access = false\n"
    with pytest.raises(PromptError, match="network_access"): parse_prompt((base+"+++\n").encode().replace(b"network_access = false\n",b""))
    with pytest.raises(PromptError, match="fresh prompts"): parse_prompt((base+"reuse_execution_id = \"e\"\n+++\n").encode())
    reuse=base.replace('session_mode = "fresh"','session_mode = "reuse"')+"reuse_execution_id = \"e\"\n+++\n"
    assert parse_prompt(reuse.encode()).reuse_execution_id=="e"
    v1=base.replace("atlas-agent-prompt/2","atlas-agent-prompt/1").replace("\nnetwork_access = false","")
    assert parse_prompt((v1+"+++\n").encode()).prompt_schema=="atlas-agent-prompt/1"


def test_v2_snapshot_owner_and_telemetry_enrichment(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w); fake=FakeExecutor(observed_thread_id="thread-A",observed_model="gpt-5.6-luna",observed_reasoning="medium"); w.execute(1,fake)
    rec=w._state()["generations"]["1"]; owner=rec["execution"]; report=w.base/owner["report_dir"]
    assert owner["owner_schema"]=="atlas-agent-execution-owner/3" and owner["policy_snapshot"]["profile"]=="implementation"
    assert owner["policy_snapshot"]["network_access"] is False
    for name in ("execution.json","result.json"):
        assert json.loads((report/name).read_text())["policy_snapshot"]==owner["policy_snapshot"]
    usage=json.loads((report/"usage.json").read_text()); assert usage["policy_config_sha256"]==owner["policy_snapshot"]["policy_config_sha256"]
    assert usage["observed_model"]=="gpt-5.6-luna" and usage["requested_reasoning"]=="medium"
    history=json.loads((w.base/"usage"/"events.jsonl").read_text()); assert history["policy_config_sha256"]==usage["policy_config_sha256"] and history["profile"]=="implementation" and history["session_mode"]=="fresh"


def test_codex_w221_argv_is_explicit_and_reuse_never_becomes_fresh(tmp_path):
    import hashlib
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec, ExecutorError

    root=tmp_path
    prompt_path=root/"prompt"
    prompt_path.write_text("p")

    # /1 remains readable historical provenance, but is never launch authority.
    legacy={
        "schema":"atlas-agent-policy-snapshot/1",
        "policy_schema":"atlas-agent-policy/1",
        "policy_config_sha256":"a"*64,
        "action":"implementation",
        "checkpoint":"x",
        "profile":"implementation",
        "executor":"codex",
        "requested_model":"gpt-5.6-sol",
        "requested_reasoning_effort":"medium",
        "session_mode":"fresh",
        "sandbox_mode":"workspace-write",
        "network_access_requested":False,
        "network_access":False,
        "web_search":"disabled",
        "apps_enabled":False,
        "session_storage":"persist",
        "max_hot_reuse_hops":3,
        "max_reuse_generation_gap":2,
    }
    assert validate_snapshot(legacy)==legacy

    legacy_spec=ExecutionSpec(
        generation=1,
        prompt_sha256="a"*64,
        action="implementation",
        prompt_path=prompt_path,
        repository_root=root,
        execution_id="legacy",
        report_dir=root/"legacy-report",
        runtime_root=root,
        checkpoint=None,
        policy_snapshot=legacy,
        input_mode="legacy",
    )
    legacy_executor=CodexExecutor(
        executable="/bin/true",
        model="gpt-5.6-sol",
        sandbox="workspace-write",
        network_access=False,
    )
    with pytest.raises(ExecutorError, match="POLICY_SNAPSHOT_NOT_EXECUTABLE"):
        legacy_executor.prepare_execution(legacy_spec)

    # /2 is the only executable form. Use a complete pinned fixture runtime.
    codex_home=root/"codex-home"
    codex_home.mkdir(mode=0o700)

    config=codex_home/"config.toml"
    catalog=codex_home/"models-atlas-shell-only.json"
    profile=codex_home/"atlas-luna-local.config.toml"

    config.write_text("suppress_unstable_features_warning = true\n")
    catalog.write_text('{"models":[]}\n')
    profile.write_text(
        'model = "gpt-5.6-luna"\n'
        '[features.tool_registry]\n'
        'allowed_tools = ["exec_command","write_stdin","apply_patch"]\n'
    )

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    snapshot={
        "schema":"atlas-agent-policy-snapshot/3",
        "policy_schema":"atlas-agent-policy/2",
        "policy_config_sha256":"a"*64,
        "action":"implementation",
        "checkpoint":"x",
        "profile":"implementation",
        "executor":"codex",
        "requested_model":"gpt-5.6-luna",
        "requested_reasoning_effort":"medium",
        "session_mode":"fresh",
        "sandbox_mode":"workspace-write",
        "network_access_requested":False,
        "network_access":False,
        "web_search":"disabled",
        "apps_enabled":False,
        "session_storage":"persist",
        "max_hot_reuse_hops":3,
        "max_reuse_generation_gap":2,
        "codex_profile":"atlas-luna-local",
        "codex_binary_sha256":sha(Path("/bin/true").resolve()),
        "codex_config_sha256":sha(config),
        "codex_catalog_sha256":sha(catalog),
        "codex_profile_sha256":sha(profile),
        "required_toolchains":[],
        "writable_caches":[],
    }
    assert validate_snapshot(snapshot)==snapshot

    true_executable=str(Path("/bin/true").resolve())
    ex=CodexExecutor(
        executable=true_executable,
        model="gpt-5.6-luna",
        sandbox="workspace-write",
        network_access=False,
        codex_home=codex_home,
    )

    fresh_spec=ExecutionSpec(
        generation=1,
        prompt_sha256="a"*64,
        action="implementation",
        prompt_path=prompt_path,
        repository_root=root,
        execution_id="fresh",
        report_dir=root/"fresh-report",
        runtime_root=root,
        checkpoint=None,
        policy_snapshot=snapshot,
        input_mode="legacy",
    )
    prepared=ex.prepare_execution(fresh_spec)

    assert prepared.command[:4]==(
        true_executable,"--profile","atlas-luna-local","exec"
    )
    assert "--ignore-user-config" not in prepared.command
    assert "--strict-config" in prepared.command
    assert "--ignore-rules" in prepared.command
    assert "features.apps=false" in prepared.command
    assert 'web_search="disabled"' in prepared.command
    assert 'model_reasoning_effort="medium"' in prepared.command

    reuse=dict(
        snapshot,
        session_mode="reuse",
        reused_from_execution_id="e0",
        requested_thread_id="thread",
        reuse_depth=1,
    )
    assert validate_snapshot(reuse)==reuse

    reuse_spec=ExecutionSpec(
        generation=2,
        prompt_sha256="b"*64,
        action="implementation",
        prompt_path=prompt_path,
        repository_root=root,
        execution_id="reuse",
        report_dir=root/"reuse-report",
        runtime_root=root,
        checkpoint=None,
        policy_snapshot=reuse,
        input_mode="legacy",
    )
    resumed=ex.prepare_execution(reuse_spec)

    assert resumed.command[:5]==(
        true_executable,"--profile","atlas-luna-local","exec","resume"
    )
    assert "thread" in resumed.command
    assert "--ignore-user-config" not in resumed.command



def test_codex_atlas_profile_and_home_are_pinned_and_rechecked(tmp_path, monkeypatch):
    import hashlib
    import os
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec, ExecutorError

    root=tmp_path
    prompt_path=root/"prompt"; prompt_path.write_text("p")

    codex_home=root/"codex-home"; codex_home.mkdir(mode=0o700)
    config=codex_home/"config.toml"; config.write_text("suppress_unstable_features_warning = true\n")
    catalog=codex_home/"models-atlas-shell-only.json"; catalog.write_text('{"models":[]}\n')
    profile=codex_home/"atlas-luna-local.config.toml"
    profile.write_text('model = "gpt-5.6-luna"\n[features.tool_registry]\nallowed_tools = ["exec_command","write_stdin","apply_patch"]\n')

    executable=root/"codex"
    executable.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        "  echo 'codex-atlas-test 0.0'\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    )
    executable.chmod(0o700)

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    snapshot={
        "schema":"atlas-agent-policy-snapshot/3",
        "policy_schema":"atlas-agent-policy/2",
        "policy_config_sha256":"a"*64,
        "action":"implementation",
        "checkpoint":"x",
        "profile":"implementation",
        "executor":"codex",
        "requested_model":"gpt-5.6-luna",
        "requested_reasoning_effort":"medium",
        "session_mode":"fresh",
        "sandbox_mode":"workspace-write",
        "network_access_requested":False,
        "network_access":False,
        "web_search":"disabled",
        "apps_enabled":False,
        "session_storage":"persist",
        "max_hot_reuse_hops":3,
        "max_reuse_generation_gap":2,
        "codex_profile":"atlas-luna-local",
        "codex_binary_sha256":sha(executable),
        "codex_config_sha256":sha(config),
        "codex_catalog_sha256":sha(catalog),
        "codex_profile_sha256":sha(profile),
        "required_toolchains":[],
        "writable_caches":[],
    }

    spec=ExecutionSpec(
        1,"a"*64,"implementation",prompt_path,root,"e",root/"r",root,
        None,snapshot,input_mode="legacy",
    )
    ex=CodexExecutor(
        executable=str(executable),
        model="gpt-5.6-luna",
        sandbox="workspace-write",
        network_access=False,
        codex_home=codex_home,
    )

    prepared=ex.prepare_execution(spec)
    assert prepared.command[:4]==(
        str(executable),"--profile","atlas-luna-local","exec"
    )
    assert "--ignore-user-config" not in prepared.command
    command, handles, owned = ex._validated_runtime_command(prepared)
    os.close(handles[0])
    runtime_home = Path(ex._environment()["CODEX_HOME"])
    assert runtime_home != codex_home
    assert runtime_home.parent == Path("/tmp")
    runtime_root = codex_home.parent / (codex_home.name + ".runtime")
    (runtime_root / "sessions").mkdir(parents=True, exist_ok=True)
    (runtime_root / "sessions" / "state").write_text("retained")
    runtime_home.joinpath("config.toml").write_text('trust = "trusted"\n')
    ex._cleanup_runtime_home()
    command, handles, owned = ex._validated_runtime_command(prepared)
    os.close(handles[0])
    later_home = Path(ex._environment()["CODEX_HOME"])
    assert later_home.joinpath("config.toml").read_bytes() == config.read_bytes()
    assert config.read_bytes() == b"suppress_unstable_features_warning = true\n"
    assert later_home.joinpath("sessions", "state").read_text() == "retained"
    assert not later_home.joinpath("atlas-luna-local.config.toml").is_symlink()
    ex._cleanup_runtime_home()
    other = dict(spec.__dict__, execution_id="later")
    later = ex.prepare_execution(ExecutionSpec(**other))
    _, later_handles, _ = ex._validated_runtime_command(later)
    os.close(later_handles[0])
    assert ex._environment()["CODEX_HOME"] != str(runtime_home)
    assert Path(ex._environment()["CODEX_HOME"]).joinpath("config.toml").read_bytes() == config.read_bytes()
    ex._cleanup_runtime_home()
    assert not runtime_home.exists()

    # A CLI-compatible but unpinned executable cannot substitute for the fork.
    fake=root/"fake-codex"
    fake.write_text("#!/bin/sh\n# deliberately different binary\nexit 0\n"); fake.chmod(0o700)
    bad=CodexExecutor(
        executable=str(fake), model="gpt-5.6-luna",
        sandbox="workspace-write", network_access=False,
        codex_home=codex_home,
    )
    with pytest.raises(ExecutorError,match="CODEX_EXECUTABLE_DIGEST_MISMATCH"):
        bad.prepare_execution(spec)

    # A truncated/broadened profile cannot retain trust merely by name.
    profile.write_text('model = "gpt-5.6-luna"\n')
    with pytest.raises(ExecutorError,match="CODEX_PROFILE_DIGEST_MISMATCH"):
        ex.prepare_execution(spec)

    # Restore, prepare, then mutate: the final Popen boundary must recheck.
    profile.write_text('model = "gpt-5.6-luna"\n[features.tool_registry]\nallowed_tools = ["exec_command","write_stdin","apply_patch"]\n')
    prepared=ex.prepare_execution(spec)
    profile.write_text('model = "gpt-5.6-luna"\n')
    monkeypatch.setattr(
        "tools.atlas_agent.codex_executor.subprocess.Popen",
        lambda *a,**k: pytest.fail("Popen reached after profile mutation"),
    )
    with pytest.raises(ExecutorError,match="CODEX_PROFILE_DIGEST_MISMATCH"):
        ex.run_execution(prepared)


def test_new_snapshot_rejects_profile_network_mismatches():
    policy=load_policy(ROOT/"atlas-agent-policy.toml")

    def resolved(network):
        raw=f'''+++
schema = "atlas-agent-prompt/2"
generation = 1
parent = "genesis"
checkpoint = "mapping"
action = "implementation"
expected_head = "{"a"*40}"
session_mode = "fresh"
network_access = {str(network).lower()}
+++
'''.encode()
        return resolve_policy(policy,parse_prompt(raw))

    local=resolved(False)
    web=resolved(True)

    with pytest.raises(PolicyError):
        validate_snapshot(dict(local,codex_profile="atlas-luna-web"))
    with pytest.raises(PolicyError):
        validate_snapshot(dict(web,codex_profile="atlas-luna-local"))
    with pytest.raises(PolicyError):
        validate_snapshot(dict(local,codex_profile="atlas-anything-local"))



def test_modern_snapshot_cannot_downgrade_to_legacy_by_removing_runtime_identity():
    import sys
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec, ExecutorError

    policy=load_policy(ROOT/"atlas-agent-policy.toml")
    raw=f'''+++
schema = "atlas-agent-prompt/2"
generation = 1
parent = "genesis"
checkpoint = "downgrade"
action = "implementation"
expected_head = "{"a"*40}"
session_mode = "fresh"
network_access = false
+++
'''.encode()

    snapshot=resolve_policy(policy,parse_prompt(raw))
    assert snapshot["schema"] == "atlas-agent-policy-snapshot/3"

    downgraded=dict(snapshot)
    downgraded["schema"]="atlas-agent-policy-snapshot/1"
    for key in (
        "codex_profile",
        "codex_binary_sha256",
        "codex_config_sha256",
        "codex_catalog_sha256",
        "codex_profile_sha256",
        "required_toolchains",
        "writable_caches",
    ):
        downgraded.pop(key)

    # Explicit historical /1 remains readable as provenance.
    validate_snapshot(downgraded)

    # It is never executable.
    prompt_path=ROOT/"README.md"
    spec=ExecutionSpec(
        generation=1,
        prompt_sha256="a"*64,
        action="implementation",
        prompt_path=prompt_path,
        repository_root=ROOT,
        execution_id="legacy",
        report_dir=ROOT,
        runtime_root=ROOT,
        checkpoint=None,
        policy_snapshot=downgraded,
        input_mode="legacy",
    )
    executor=CodexExecutor(
        executable=sys.executable,
        model="gpt-5.6-luna",
        sandbox="workspace-write",
        network_access=False,
    )
    with pytest.raises(ExecutorError, match="POLICY_SNAPSHOT_NOT_EXECUTABLE"):
        executor.prepare_execution(spec)


def test_legacy_snapshot_is_never_reuse_compatible(tmp_path):
    repo,w=make_repo(tmp_path)
    accepted(w)
    fake=FakeExecutor(
        observed_thread_id="legacy-thread",
        observed_model="gpt-5.6-luna",
        observed_reasoning="medium",
    )
    w.execute(1,fake)

    # Create and accept the reuse request normally.
    state=w._state()
    target_owner=state["generations"]["1"]["execution"]
    raw2=prompt(
        w,
        generation=2,
        session="reuse",
        target=target_owner["execution_id"],
    )
    w.ingest()
    state=w._state()

    # Reclassify only our in-memory target as explicit historical /1.
    owner=state["generations"]["1"]["execution"]
    owner["policy_snapshot"]["schema"]="atlas-agent-policy-snapshot/1"
    for key in (
        "codex_profile",
        "codex_binary_sha256",
        "codex_config_sha256",
        "codex_catalog_sha256",
        "codex_profile_sha256",
        "required_toolchains",
        "writable_caches",
    ):
        owner["policy_snapshot"].pop(key,None)

    current=resolve_policy(
        load_policy(repo/"atlas-agent-policy.toml"),
        parse_prompt(raw2),
    )

    with pytest.raises(WorkflowError, match="REUSE_TARGET_INCOMPATIBLE"):
        w._reuse_snapshot(state,state["generations"]["2"],current)


def test_pinned_runtime_rejects_prepared_command_binary_substitution(tmp_path):
    import hashlib
    from dataclasses import replace
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec, ExecutorError

    root=tmp_path
    prompt_path=root/"prompt"
    prompt_path.write_text("p")

    codex_home=root/"codex-home"
    codex_home.mkdir(mode=0o700)
    config=codex_home/"config.toml"
    catalog=codex_home/"models-atlas-shell-only.json"
    profile=codex_home/"atlas-luna-local.config.toml"
    executable=root/"codex"

    config.write_text("suppress_unstable_features_warning = true\n")
    catalog.write_text('{"models":[]}\n')
    profile.write_text(
        'model = "gpt-5.6-luna"\n'
        '[features.tool_registry]\n'
        'allowed_tools = ["exec_command","write_stdin","apply_patch"]\n'
    )
    executable.write_bytes(Path("/usr/bin/true").read_bytes())
    executable.chmod(0o500)

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    snapshot={
        "schema":"atlas-agent-policy-snapshot/3",
        "policy_schema":"atlas-agent-policy/2",
        "policy_config_sha256":"a"*64,
        "action":"implementation",
        "checkpoint":"x",
        "profile":"implementation",
        "executor":"codex",
        "requested_model":"gpt-5.6-luna",
        "requested_reasoning_effort":"medium",
        "session_mode":"fresh",
        "sandbox_mode":"workspace-write",
        "network_access_requested":False,
        "network_access":False,
        "web_search":"disabled",
        "apps_enabled":False,
        "session_storage":"persist",
        "max_hot_reuse_hops":3,
        "max_reuse_generation_gap":2,
        "codex_profile":"atlas-luna-local",
        "codex_binary_sha256":sha(executable),
        "codex_config_sha256":sha(config),
        "codex_catalog_sha256":sha(catalog),
        "codex_profile_sha256":sha(profile),
        "required_toolchains":[],
        "writable_caches":[],
    }

    executor=CodexExecutor(
        executable=str(executable),
        model="gpt-5.6-luna",
        sandbox="workspace-write",
        network_access=False,
        codex_home=codex_home,
    )
    spec=ExecutionSpec(
        generation=1,
        prompt_sha256="a"*64,
        action="implementation",
        prompt_path=prompt_path,
        repository_root=root,
        execution_id="e",
        report_dir=root/"report",
        runtime_root=root,
        checkpoint=None,
        policy_snapshot=snapshot,
        input_mode="legacy",
    )
    prepared=executor.prepare_execution(spec)

    substituted=replace(
        prepared,
        command=("/usr/bin/false",)+prepared.command[1:],
    )
    with pytest.raises(ExecutorError,match="PREPARED_COMMAND_MISMATCH"):
        executor.run_execution(substituted)


def test_pinned_runtime_fd_is_sealed_and_digest_bound(tmp_path):
    import hashlib, os
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutorError

    executable=tmp_path/"codex"
    executable.write_bytes(Path("/usr/bin/true").read_bytes())
    executable.chmod(0o500)

    snapshot={
        "schema":"atlas-agent-policy-snapshot/3",
        "codex_binary_sha256":
            hashlib.sha256(executable.read_bytes()).hexdigest(),
    }

    executor=CodexExecutor(executable=str(executable))
    fd=executor._sealed_runtime_fd(snapshot)
    try:
        executor._validate_sealed_runtime_fd(fd,snapshot)

        with pytest.raises(OSError):
            os.write(fd,b"x")
    finally:
        os.close(fd)


def test_persistent_session_import_rejects_aliases_and_special_state(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutorError

    source = tmp_path / "sessions"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "ok").write_text("ordinary")
    destination = tmp_path / "runtime-sessions"
    CodexExecutor._copy_persistent_directory(source, destination)
    assert (destination / "nested" / "ok").read_text() == "ordinary"

    canonical = tmp_path / "canonical.toml"
    canonical.write_bytes(b"trusted canonical bytes")
    host_file = tmp_path / "host-secret"
    host_file.write_bytes(b"otherwise readable host bytes")
    for name, target in (("canonical", canonical), ("host", host_file)):
        hostile = tmp_path / f"hostile-{name}"
        hostile.mkdir()
        (hostile / "alias").symlink_to(target)
        with pytest.raises(ExecutorError, match="CODEX_RUNTIME_STATE_UNTRUSTED"):
            CodexExecutor._copy_persistent_directory(
                hostile, tmp_path / f"runtime-{name}"
            )
        assert not (tmp_path / f"runtime-{name}" / "alias").exists()
        assert canonical.read_bytes() == b"trusted canonical bytes"
        assert host_file.read_bytes() == b"otherwise readable host bytes"


@pytest.mark.parametrize("filename", ["codex", "renamed-codex"])
def test_native_elf_requires_explicit_isolation_capability(tmp_path, filename,
                                                           monkeypatch):
    import shutil
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec, ExecutorError, PreparedExecution

    executable = tmp_path / filename
    shutil.copyfile("/bin/true", executable)
    executable.chmod(0o700)

    class UnrelatedOverride(CodexExecutor):
        def _environment(self):
            return super()._environment()

    monkeypatch.setattr(
        CodexExecutor, "_validated_runtime_command",
        lambda self, prepared, runtime_fd=None: (list(prepared.command), (), None),
    )
    spec = ExecutionSpec(1, "a" * 64, "implementation", tmp_path / "prompt",
                         tmp_path, "execution", tmp_path / "report")
    prepared = PreparedExecution(spec, "codex", (str(executable),), "test", {})
    for executor in (CodexExecutor(executable=str(executable)),
                     UnrelatedOverride(executable=str(executable))):
        with pytest.raises(
                ExecutorError,
                match="CODEX_NATIVE_CROSS_EXECUTION_ISOLATION_UNAVAILABLE"):
            executor.run_execution(prepared)


def test_bubblewrap_explicitly_guarantees_native_isolation():
    from tools.atlas_agent.bubblewrap import AtlasBubblewrapExecutor
    assert AtlasBubblewrapExecutor.native_isolation_guaranteed is True


def test_network_resolution_and_checkpoint_are_prelaunch(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w,network=True); fake=FakeExecutor(observed_thread_id="thread-network")
    w.execute(1,fake); assert fake.launched==1
    repo2,w2=make_repo(tmp_path/"second"); accepted(w2,action="patch_review",network=True)
    with pytest.raises(WorkflowError,match="NETWORK_ACCESS_FORBIDDEN"): w2.execute(1,FakeExecutor())
    repo3,w3=make_repo(tmp_path/"third"); accepted(w3,action="checkpoint")
    fake3=FakeExecutor()
    with pytest.raises(WorkflowError,match="CHECKPOINT_MANUAL_REQUIRED"): w3.execute(1,fake3)
    assert fake3.launched==0


def test_state_audit_is_cold_fresh_and_reuse_forbidden(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w,action="state_audit",session="reuse",target="missing")
    with pytest.raises(WorkflowError,match="SESSION_MODE_FORBIDDEN"): w.execute(1,FakeExecutor())
    repo2,w2=make_repo(tmp_path/"cold"); accepted(w2,action="state_audit")
    w2.execute(1,FakeExecutor(observed_thread_id="cold")); snap=w2._state()["generations"]["1"]["execution"]["policy_snapshot"]
    assert snap["cold_policy"]=="conversational" and snap["freshness_verification"]=="deferred" and snap["sandbox_mode"]=="read-only" and snap["network_access"] is False and snap["session_storage"]=="ephemeral"


def test_reuse_exact_target_compatibility_lineage_and_limits(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w); first=FakeExecutor(observed_thread_id="thread-A",observed_model="gpt-5.6-luna",observed_reasoning="medium"); w.execute(1,first); eid=w._state()["generations"]["1"]["execution"]["execution_id"]
    accepted(w,generation=2,session="reuse",target=eid); second=FakeExecutor(observed_thread_id="thread-A",observed_model="gpt-5.6-luna",observed_reasoning="medium"); w.execute(2,second)
    snap=w._state()["generations"]["2"]["execution"]["policy_snapshot"]; assert snap["reused_from_execution_id"]==eid and snap["reuse_depth"]==1
    accepted(w,generation=3,session="reuse",target=eid)
    w.execute(3,FakeExecutor(observed_thread_id="thread-B"))
    record=w._state()["generations"]["3"]
    assert record["status"]=="COMPLETED"
    snapshot=record["execution"]["policy_snapshot"]
    assert snapshot["session_mode_requested"]=="reuse"
    assert snapshot["session_mode"]=="fresh"
    assert snapshot["reuse_fallback_reason"]=="advanced_reuse_lineage"


def test_reuse_missing_unknown_and_tainted_target_fail_before_launch(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w,session="reuse",target="unknown")
    with pytest.raises(WorkflowError,match="REUSE_TARGET_UNKNOWN"): w.execute(1,FakeExecutor())
    repo2,w2=make_repo(tmp_path/"taint"); accepted(w2); first=FakeExecutor(observed_thread_id="thread-T"); w2.execute(1,first); eid=w2._state()["generations"]["1"]["execution"]["execution_id"]
    accepted(w2,generation=2,session="reuse",target=eid); bad=FakeExecutor(observed_thread_id="thread-T",exit_code=7)
    with pytest.raises(WorkflowError): w2.execute(2,bad)
    accepted(w2,generation=3,session="reuse",target=eid); probe=FakeExecutor(observed_thread_id="thread-T")
    with pytest.raises(WorkflowError,match="REUSE_LINEAGE_TAINTED|REUSE_TARGET_STALE"): w2.execute(3,probe)
    assert probe.launched==0


def test_v1_reuse_is_readable_but_not_automatically_executable(tmp_path):
    repo,w=make_repo(tmp_path,policy=False); accepted(w,schema=1,session="reuse")
    with pytest.raises(WorkflowError,match="REUSE_TARGET_MISSING"): w.execute(1,FakeExecutor())


def test_project_local_codex_config_fails_closed_before_launch(tmp_path):
    repo,w=make_repo(tmp_path,project_config=True)
    accepted(w); fake=FakeExecutor()
    with pytest.raises(WorkflowError,match="CODEX_PROJECT_CONFIG_UNSUPPORTED"): w.execute(1,fake)
    assert fake.launched==0


def test_policy_witness_is_revalidated_after_prepare_before_run_started(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w)
    class Mutating(FakeExecutor):
        def prepare_execution(self,spec):
            prepared=super().prepare_execution(spec)
            path=spec.repository_root/"atlas-agent-policy.toml"
            before=policy_config_sha256(load_policy(path))
            path.write_text(path.read_text()+"\n# prepare-window-comment\n")
            assert policy_config_sha256(load_policy(path))==before
            return prepared
    fake=Mutating()
    with pytest.raises(WorkflowError,match="REPOSITORY_WITNESS_MISMATCH"): w.execute(1,fake)
    assert fake.launched==0
    assert not any(e["event"]=="RUN_STARTED" for e in w.journal.read())


def test_running_reuse_blocks_second_branch_from_same_thread(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w); w.execute(1,FakeExecutor(observed_thread_id="thread-T")); first=w._state()["generations"]["1"]["execution"]
    accepted(w,generation=2,session="reuse",target=first["execution_id"])
    metadata={
        # start_run is the same authority boundary used by a launcher.  Do
        # not copy g1's policy snapshot: the resolver must derive g2's
        # reuse lineage and bind it to the archived policy.
        "execution_id":"223e4567-e89b-12d3-a456-426614174000",
        "executor":"codex",
        "started_at":"now",
        "pid":None,
        "report_dir":"reports/executions/223e4567-e89b-12d3-a456-426614174000",
        "permission_envelope":{
            "sandbox_mode":"workspace-write",
            "approval_policy":"never",
            "approvals_reviewer":"user",
            "strict_config":True,
            "ignore_rules":True,
            "network_access":False,
        },
    }
    w.start_run(2,execution=metadata)
    g2=w._state()["generations"]["2"]
    assert g2["status"]=="RUNNING"
    assert g2["execution"]["policy_snapshot"]["session_mode"]=="reuse"
    w._prepare_execution_publication({
        "execution":g2["execution"], "generation":2,
        "prompt_sha256":g2["prompt_sha256"], "action":g2["action"],
    })
    accepted(w,generation=3,session="reuse",target=first["execution_id"]); probe=FakeExecutor()
    with pytest.raises(WorkflowError,match="REUSE_LINEAGE_TAINTED"): w.execute(3,probe)
    assert probe.launched==0


def test_interrupted_reuse_taints_requested_thread_without_observed_thread(tmp_path):
    repo,w=make_repo(tmp_path); accepted(w); w.execute(1,FakeExecutor(observed_thread_id="thread-T")); first=w._state()["generations"]["1"]["execution"]
    accepted(w,generation=2,session="reuse",target=first["execution_id"]); bad=FakeExecutor(exit_code=7)
    with pytest.raises(WorkflowError,match="REUSE_SESSION_UNAVAILABLE"): w.execute(2,bad)
    accepted(w,generation=3,session="reuse",target=first["execution_id"]); probe=FakeExecutor()
    with pytest.raises(WorkflowError,match="REUSE_LINEAGE_TAINTED"): w.execute(3,probe)
    assert probe.launched==0


@pytest.mark.parametrize("field",["action","session_mode"])
def test_prompt_wrong_container_types_are_prompt_errors(field):
    head="a"*40
    value="[\"implementation\"]" if field=="action" else "{\"mode\": \"fresh\"}"
    raw=f'+++\nschema = "atlas-agent-prompt/2"\ngeneration = 1\nparent = "genesis"\ncheckpoint = "x"\naction = "implementation"\nexpected_head = "{head}"\nsession_mode = "fresh"\nnetwork_access = false\n{field} = {value}\n+++\n'.encode()
    with pytest.raises(PromptError): parse_prompt(raw)
