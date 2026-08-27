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


def make_repo(tmp_path, policy=True, project_config=False):
    repo = tmp_path / "repo"; repo.mkdir(parents=True)
    git(repo, "init", "-q"); git(repo, "config", "user.email", "t@e"); git(repo, "config", "user.name", "t")
    (repo / "a").write_text("a")
    (repo / "atlas-agent.toml").write_text('schema = "atlas-agent-project/1"\nallowed_untracked = ["corpus_miner/"]\n')
    if policy: (repo / "atlas-agent-policy.toml").write_text(POLICY)
    if project_config:
        (repo/".codex").mkdir(); (repo/".codex"/"config.toml").write_text("hooks = []\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "fixture")
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
    for action in ("patch_review","state_audit"):
        snapshot=resolved(action)
        assert (snapshot["requested_model"],snapshot["requested_reasoning_effort"])==("gpt-5.6-sol","high")


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
    assert owner["owner_schema"]=="atlas-agent-execution-owner/2" and owner["policy_snapshot"]["profile"]=="implementation"
    assert owner["policy_snapshot"]["network_access"] is False
    for name in ("execution.json","result.json"):
        assert json.loads((report/name).read_text())["policy_snapshot"]==owner["policy_snapshot"]
    usage=json.loads((report/"usage.json").read_text()); assert usage["policy_config_sha256"]==owner["policy_snapshot"]["policy_config_sha256"]
    assert usage["observed_model"]=="gpt-5.6-luna" and usage["requested_reasoning"]=="medium"
    history=json.loads((w.base/"usage"/"events.jsonl").read_text()); assert history["policy_config_sha256"]==usage["policy_config_sha256"] and history["profile"]=="implementation" and history["session_mode"]=="fresh"


def test_codex_w221_argv_is_explicit_and_reuse_never_becomes_fresh(tmp_path):
    from tools.atlas_agent.codex_executor import CodexExecutor
    from tools.atlas_agent.executor import ExecutionSpec
    root=tmp_path; prompt_path=root/"prompt"; prompt_path.write_text("p")
    snapshot={"schema":"atlas-agent-policy-snapshot/1","policy_schema":"atlas-agent-policy/1","policy_config_sha256":"a"*64,"action":"implementation","checkpoint":"x","profile":"implementation","executor":"codex","requested_model":"gpt-5.6-sol","requested_reasoning_effort":"medium","session_mode":"fresh","sandbox_mode":"workspace-write","network_access_requested":False,"network_access":False,"web_search":"disabled","apps_enabled":False,"session_storage":"persist","max_hot_reuse_hops":3,"max_reuse_generation_gap":2}
    assert validate_snapshot(snapshot)==snapshot  # Historical snapshots retain their stored model.
    ex=CodexExecutor(executable="/bin/true",model="gpt-5.6-sol",sandbox="workspace-write",network_access=False); prepared=ex.prepare_execution(ExecutionSpec(1,"a"*64,"implementation",prompt_path,root,"e",root/"r",root,None,snapshot,input_mode="legacy"))
    assert "--ignore-user-config" in prepared.command and "--strict-config" in prepared.command and "--ignore-rules" in prepared.command
    assert "features.apps=false" in prepared.command and 'web_search="disabled"' in prepared.command
    assert 'model_reasoning_effort="medium"' in prepared.command
    reuse=dict(snapshot,session_mode="reuse",reused_from_execution_id="e0",requested_thread_id="thread",reuse_depth=1)
    resumed=ex.prepare_execution(ExecutionSpec(1,"a"*64,"implementation",prompt_path,root,"e",root/"r",root,None,reuse,input_mode="legacy"))
    assert resumed.command[1:3]==("exec","resume") and "thread" in resumed.command


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
    with pytest.raises(WorkflowError,match="REUSE_TARGET_STALE"): w.execute(3,FakeExecutor(observed_thread_id="thread-A"))


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
    snapshot=dict(first["policy_snapshot"],session_mode="reuse",reused_from_execution_id=first["execution_id"],requested_thread_id="thread-T",reuse_depth=1)
    metadata={"execution_id":"running-e2","executor":"fake","started_at":"now","pid":None,"report_dir":"reports/executions/running-e2","permission_envelope":{"sandbox_mode":"workspace-write","approval_policy":"never","approvals_reviewer":"user","strict_config":True,"ignore_rules":True,"network_access":False},"owner_schema":"atlas-agent-execution-owner/2","policy_snapshot":snapshot}
    w.start_run(2,execution=metadata)
    report=w.base/"reports"/"executions"/"running-e2"; report.mkdir(parents=True); (report/"execution.json").write_text(json.dumps({**metadata,"generation":2,"prompt_sha256":w._state()["generations"]["2"]["prompt_sha256"],"action":"implementation","command":[],"version":"fake/1"}))
    accepted(w,generation=3,session="reuse",target=first["execution_id"]); probe=FakeExecutor()
    with pytest.raises(WorkflowError,match="REUSE_TARGET_STALE"): w.execute(3,probe)
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
