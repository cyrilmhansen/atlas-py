"""P0.6 integration contract.

These tests deliberately cross the production boundaries.  They are not
another test suite for ``tools.atlas_agent.toolchains``: until the policy,
workflow, executor, and history paths carry capabilities, the assertions
below must fail.
"""
import json
import hashlib
import base64
import os
import socket
import subprocess
import shutil
import tempfile
import shlex
from dataclasses import fields
from pathlib import Path

import pytest

from tools.atlas_agent.bubblewrap import AtlasBubblewrapExecutor
from tools.atlas_agent.executor import ExecutionSpec, FakeExecutor, PreparedExecution
from tools.atlas_agent.policy import load_policy, resolve_policy
from tools.atlas_agent.prompt import parse_prompt
from tools.atlas_agent.workflow import Workflow
from tools.atlas_agent.toolchains import CacheStore


ROOT = Path(__file__).parents[1]
BASE_POLICY = (ROOT / "atlas-agent-policy.toml").read_text()


def _git(path, *args):
    return subprocess.check_output(["git", *args], cwd=path, text=True).strip()


def _project(tmp_path, *, capabilities=True, qualification="rust:1"):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "atlas@example.invalid")
    _git(repo, "config", "user.name", "Atlas")
    (repo / "tracked").write_text("fixture\n")
    (repo / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\n'
        'allowed_untracked = ["corpus_miner/"]\n'
    )
    policy = BASE_POLICY
    if capabilities:
        policy = policy.replace(
            'required_toolchains = []\n'
            'writable_caches = []\n',
            'required_toolchains = ["rust"]\n'
            'writable_caches = ["cargo"]\n', 1)
    (repo / "atlas-agent-policy.toml").write_text(policy)
    tool = tmp_path / "qualified-toolchain" / "bin" / "cargo"
    tool.parent.mkdir(parents=True)
    tool.write_text("#!/bin/sh\nprintf 'cargo 1.0\\n'\n")
    tool.chmod(0o755)
    digest = hashlib.sha256(tool.read_bytes()).hexdigest()
    probe = hashlib.sha256(b"cargo 1.0\n\0").hexdigest()
    (tmp_path / "machine-capabilities.toml").write_text(
        'schema = "atlas-agent-machine-capabilities/1"\n'
        f'persistent_cache_root = "{tmp_path / "persistent-caches"}"\n\n'
        "[toolchains.rust]\n"
        'qualification = "rust:1"\n'
        f'source_root = "{tool.parent.parent}"\n\n'
        "[toolchains.rust.commands.cargo]\n"
        'path = "bin/cargo"\n'
        f'sha256 = "{digest}"\n'
        'probe_args = ["--version"]\n'
        f'probe_output_sha256 = "{probe}"\n\n'
        '[caches.cargo]\nqualification = "cargo-cache/1"\n'
        'environment = { CARGO_HOME = "${CACHE}" }\n'
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    workflow = Workflow(repo)
    workflow.init()
    return repo, workflow


def _accept(workflow, generation=1, *, session="fresh", target=None,
            prompt_schema=2):
    target_line = (
        f'reuse_execution_id = "{target}"\n' if target is not None else ""
    )
    network_line = "network_access = false\n" if prompt_schema == 2 else ""
    raw = (
        "+++\n"
        f'schema = "atlas-agent-prompt/{prompt_schema}"\n'
        f"generation = {generation}\n"
        f"parent = {'\"genesis\"' if generation == 1 else generation - 1}\n"
        f'checkpoint = "P06-{generation}"\n'
        'action = "implementation"\n'
        f'expected_head = "{_git(workflow.root, "rev-parse", "HEAD")}"\n'
        f'session_mode = "{session}"\n'
        + network_line
        + f"{target_line}"
        "+++\nP0.6 integration fixture\n"
    ).encode()
    (workflow.base / "inbox" / f"g{generation}.txt").write_bytes(raw)
    workflow.ingest()


def _events(workflow):
    return workflow.journal.read()


@pytest.fixture
def disk_backed_scratch_root():
    """Use the same non-tmpfs backing required by the live executor."""
    try:
        root = Path(tempfile.mkdtemp(prefix="atlas-agent-p06-", dir="/var/tmp"))
    except OSError as error:
        pytest.skip(f"host /var/tmp is unavailable: {error}")
    try:
        filesystem = subprocess.run(
            ["stat", "-f", "-c", "%T", str(root)],
            text=True, capture_output=True, check=False,
        )
        if filesystem.returncode != 0 or filesystem.stdout.strip() == "tmpfs":
            pytest.skip("host /var/tmp does not provide writable non-tmpfs storage")
        if not os.access(root, os.W_OK):
            pytest.skip("host /var/tmp is not writable")
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _production_inputs(workflow, accepted, plan, execution_id):
    """Build the current execution API inputs, as Workflow does."""
    prompt_bytes = accepted.read_bytes()
    prompt = parse_prompt(prompt_bytes)
    snapshot = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"), prompt
    )
    return dict(
        generation=1,
        prompt_sha256=hashlib.sha256(prompt_bytes).hexdigest(),
        action=prompt.action,
        prompt_path=accepted,
        repository_root=workflow.root,
        execution_id=execution_id,
        report_dir=workflow.base / "reports" / "executions" / execution_id,
        runtime_root=workflow.base,
        checkpoint=prompt.checkpoint,
        policy_snapshot=snapshot,
        prompt_bytes=prompt_bytes,
        input_mode="bytes-v1",
        expected_input_sha256=hashlib.sha256(prompt_bytes).hexdigest(),
        capability_plan=plan,
    )


def _production_executor(root, snapshot):
    return AtlasBubblewrapExecutor(
        model=snapshot["requested_model"],
        sandbox=snapshot["sandbox_mode"],
        network_access=snapshot["network_access"],
        ephemeral=snapshot["session_storage"] == "ephemeral",
        scratch_root=root,
    )


def _ws_send(sock, value):
    payload = json.dumps(value, separators=(",", ":")).encode()
    mask = os.urandom(4)
    if len(payload) <= 125:
        header = bytearray([0x81, 0x80 | len(payload)])
    elif len(payload) <= 0xffff:
        header = bytearray([0x81, 0xfe]) + len(payload).to_bytes(2, "big")
    else:
        raise AssertionError("fixture websocket payload is unexpectedly large")
    sock.sendall(header + mask + bytes(
        byte ^ mask[i % 4] for i, byte in enumerate(payload)
    ))


def _ws_recv(sock):
    def read_exact(length):
        data = bytearray()
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise AssertionError("exec-server websocket closed")
            data.extend(chunk)
        return bytes(data)

    while True:
        first, second = read_exact(2)
        length = second & 0x7f
        if length == 126:
            length = int.from_bytes(read_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(read_exact(8), "big")
        mask = read_exact(4) if second & 0x80 else None
        payload = bytearray(read_exact(length))
        if mask:
            for i in range(length):
                payload[i] ^= mask[i % 4]
        if first & 0x0f == 0x9:
            sock.sendall(bytes([0x8a, len(payload)]) + payload)
        elif first & 0x0f == 0x1:
            return json.loads(payload)


def _ws_connect(url):
    port = int(url.rsplit(":", 1)[1])
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((
        f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode())
    response = bytearray()
    while b"\r\n\r\n" not in response:
        response.extend(sock.recv(4096))
    assert response.startswith(b"HTTP/1.1 101"), response[:200]
    return sock


def test_real_policy_and_workflow_resolve_profile_capabilities(tmp_path, monkeypatch):
    repo, workflow = _project(tmp_path)
    monkeypatch.setenv(
        "ATLAS_AGENT_CAPABILITIES_FILE",
        str(tmp_path / "machine-capabilities.toml"),
    )
    policy = load_policy(repo / "atlas-agent-policy.toml")
    profile = policy["profiles"]["implementation"]
    assert profile["required_toolchains"] == ["rust"], "POLICY_NOT_CONNECTED"
    assert profile["writable_caches"] == ["cargo"], "POLICY_NOT_CONNECTED"
    _accept(workflow)
    # Freshness is part of the production session contract; a successful
    # fixture must report the identity observed by the executor.
    workflow.execute(1, FakeExecutor(observed_thread_id="fresh-thread-1"))
    owner = workflow._state()["generations"]["1"]["execution"]
    assert owner.get("capability_plan_sha256"), "WORKFLOW_NOT_CONNECTED"


def test_resolved_immutable_plan_reaches_execution_spec(tmp_path):
    _, workflow = _project(tmp_path)
    _accept(workflow)
    names = {field.name for field in fields(ExecutionSpec)}
    assert "capability_plan" in names, "EXECUTION_SPEC_NOT_CONNECTED"


def test_real_workflow_plan_changes_for_a_different_qualification(tmp_path, monkeypatch):
    _, workflow = _project(tmp_path)
    monkeypatch.setenv(
        "ATLAS_AGENT_CAPABILITIES_FILE",
        str(tmp_path / "machine-capabilities.toml"),
    )
    resolve = getattr(workflow, "resolve_capabilities", None)
    assert resolve is not None, "WORKFLOW_NOT_CONNECTED"
    first = resolve({"toolchains": ["rust"], "caches": ["cargo"]})
    manifest = (tmp_path / "machine-capabilities.toml").read_text()
    (tmp_path / "machine-capabilities.toml").write_text(
        manifest.replace('qualification = "rust:1"', 'qualification = "rust:2"', 1)
    )
    second = resolve({"toolchains": ["rust"], "caches": ["cargo"]})
    assert first.sha256 != second.sha256, "WORKFLOW_NOT_CONNECTED"


def test_real_workflow_rejects_unchecked_path_fallback(tmp_path, monkeypatch):
    _, workflow = _project(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "not-a-qualified-directory"))
    resolve = getattr(workflow, "resolve_capabilities", None)
    assert resolve is not None, "WORKFLOW_NOT_CONNECTED"
    with pytest.raises(Exception, match="UNAVAILABLE|QUALIFICATION|CAPABILITY"):
        resolve({"toolchains": ["rust"], "caches": ["cargo"]})


@pytest.mark.parametrize(
    "failure",
    ["missing required capability", "qualification mismatch",
     "persistent cache preparation/lock failure",
     "production sandbox capability-probe failure"],
)
def test_real_preflight_failures_happen_before_run_started(
    tmp_path, monkeypatch, failure, request
):
    _, workflow = _project(tmp_path)
    _accept(workflow)
    if failure != "missing required capability":
        monkeypatch.setenv(
            "ATLAS_AGENT_CAPABILITIES_FILE",
            str(tmp_path / "machine-capabilities.toml"),
        )
    if failure == "production sandbox capability-probe failure":
        if not shutil.which("bwrap") or not shutil.which("codex"):
            pytest.skip("Bubblewrap/native Codex unavailable")
        # Keep host qualification valid while making the identical probe
        # fail only in bwrap's private /tmp namespace.
        sentinel = tmp_path / "host-only-probe-sentinel"
        sentinel.write_text("host only\n")
        tool = tmp_path / "qualified-toolchain" / "bin" / "cargo"
        tool.write_text(
            f'#!/bin/sh\nif [ -e "{sentinel}" ]; then printf "cargo 1.0\\\\n"; exit 0; fi\n'
            'exit 23\n'
        )
        tool.chmod(0o755)
        manifest_path = tmp_path / "machine-capabilities.toml"
        manifest = manifest_path.read_text()
        manifest = manifest.replace(
            'sha256 = "' + hashlib.sha256(
                b"#!/bin/sh\nprintf 'cargo 1.0\\n'\n"
            ).hexdigest() + '"',
            f'sha256 = "{hashlib.sha256(tool.read_bytes()).hexdigest()}"',
        )
        manifest_path.write_text(manifest)
    if failure == "qualification mismatch":
        manifest = (tmp_path / "machine-capabilities.toml").read_text()
        # The manifest is valid and reaches host qualification first; changing
        # the observed executable identity makes this the qualification
        # contract, rather than an unavailable-capability test.
        (tmp_path / "qualified-toolchain" / "bin" / "cargo").write_text(
            "#!/bin/sh\nprintf 'cargo 9.9\\n'\n"
        )
    held_cache_lock = None
    if failure == "persistent cache preparation/lock failure":
        plan = workflow.resolve_capabilities(
            {"toolchains": ["rust"], "caches": ["cargo"]}
        )
        cache = plan.caches[0]
        held_cache_lock = CacheStore(cache.backing.parents[3]).lock_directory(
            cache.backing
        )
    # The production boundary must classify this requested failure; accepting
    # an unrelated executor/bootstrap error would make this a false positive.
    scratch_root = (
        request.getfixturevalue("disk_backed_scratch_root")
        if failure == "production sandbox capability-probe failure"
        else tmp_path / "scratch"
    )
    executor = AtlasBubblewrapExecutor(scratch_root=scratch_root)
    try:
        with pytest.raises(Exception) as caught:
            workflow.execute(1, executor)
    finally:
        if held_cache_lock is not None:
            held_cache_lock.release()
            # The failed preparation must not leave the production namespace
            # permanently wedged.
            retry = CacheStore(plan.caches[0].backing.parents[3]).lock_directory(
                plan.caches[0].backing
            )
            retry.release()
    expected = {
        "missing required capability": "ATLAS_TOOLCHAIN_REQUIRED_UNAVAILABLE",
        "qualification mismatch": "ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH",
        "persistent cache preparation/lock failure": "ATLAS_CACHE",
        "production sandbox capability-probe failure":
            "ATLAS_TOOLCHAIN_SANDBOX_PROBE_FAILED",
    }[failure]
    assert expected in str(caught.value), f"{failure}: missing real preflight"
    events = _events(workflow)
    assert not any(event["event"] == "RUN_STARTED" for event in events), (
        f"preflight {failure!r} reached RUN_STARTED"
    )
    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"
    assert executor._run_lock.locked() is False


def test_real_preflight_checks_every_exported_command(tmp_path, monkeypatch, request):
    """A host-qualified later export must not be omitted from bwrap probing."""
    if not shutil.which("bwrap") or not shutil.which("codex"):
        pytest.skip("Bubblewrap/native Codex unavailable")
    _, workflow = _project(tmp_path)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    sentinel = tmp_path / "host-only-second-command"
    sentinel.write_text("host only\n")
    second = tmp_path / "qualified-toolchain" / "bin" / "second"
    second.write_text(
        f'#!/bin/sh\nif [ -e "{sentinel}" ]; then printf second-ok; exit 0; fi\nexit 23\n'
    )
    second.chmod(0o755)
    second_digest = hashlib.sha256(second.read_bytes()).hexdigest()
    second_probe = hashlib.sha256(b"second-ok\0").hexdigest()
    manifest_path = tmp_path / "machine-capabilities.toml"
    manifest_path.write_text(manifest_path.read_text() + (
        "\n[toolchains.rust.commands.second]\npath = \"bin/second\"\n"
        f"sha256 = \"{second_digest}\"\nprobe_args = []\n"
        f"probe_output_sha256 = \"{second_probe}\"\n"
    ))
    _accept(workflow)
    plan = workflow.resolve_capabilities({"toolchains": ["rust"], "caches": ["cargo"]})
    accepted = next((workflow.base / "accepted").glob("*.txt"))
    snapshot = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"),
        parse_prompt(accepted.read_bytes()),
    )
    executor = _production_executor(
        request.getfixturevalue("disk_backed_scratch_root"), snapshot
    )
    spec = ExecutionSpec(**_production_inputs(
        workflow, accepted, plan, "all-command-preflight"
    ))
    try:
        # The second export is qualified on the host but deliberately cannot
        # pass its probe in the namespace: every exported command must be
        # probed, rather than only the first one.
        with pytest.raises(Exception, match="ATLAS_TOOLCHAIN_SANDBOX_PROBE_FAILED"):
            executor.prepare_execution(spec)
    finally:
        executor._stop_server()


def test_real_preflight_does_not_bypass_commandless_capability_plan(
    tmp_path, monkeypatch, request
):
    """Caches alone still require namespace capability validation."""
    if not shutil.which("bwrap") or not shutil.which("codex"):
        pytest.skip("Bubblewrap/native Codex unavailable")
    _, workflow = _project(tmp_path, capabilities=False)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    # An empty-command plan is constructed by the resolver from this
    # controller-authored cache-only requirement.
    plan = workflow.resolve_capabilities({"toolchains": [], "caches": ["cargo"]})
    accepted = next((workflow.base / "accepted").glob("*.txt"))
    snapshot = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"),
        parse_prompt(accepted.read_bytes()),
    )
    executor = _production_executor(
        request.getfixturevalue("disk_backed_scratch_root"), snapshot
    )
    spec = ExecutionSpec(**_production_inputs(
        workflow, accepted, plan, "commandless-preflight"
    ))
    try:
        prepared = executor.prepare_execution(spec)
        assert prepared.runtime_handle["capability_plan_sha256"] == plan.sha256
        assert prepared.runtime_handle["caches"] == [{
            "guest_path": "/var/cache/atlas-agent/cargo",
            "mount": "rw",
        }]
    finally:
        executor._stop_server()


def test_production_bubblewrap_consumes_private_toolchain_and_cache_plan(
    tmp_path, monkeypatch, request
):
    _, workflow = _project(tmp_path)
    # The manifest is machine authority, not an implicit repository fixture.
    # (The test is expected to be an environment skip where native Codex is
    # unavailable, rather than accidentally passing on a new executor.)
    if not shutil.which("bwrap") or not shutil.which(
        "codex"
    ) and not __import__("os").environ.get("ATLAS_CODEX_EXECUTABLE"):
        pytest.skip("Bubblewrap/native Codex unavailable")
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    plan = workflow.resolve_capabilities({"toolchains": ["rust"], "caches": ["cargo"]})
    _accept(workflow)
    disk_backed_scratch_root = request.getfixturevalue("disk_backed_scratch_root")
    snapshot = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"),
        parse_prompt(next((workflow.base / "accepted").glob("g000001-*.txt")).read_bytes()),
    )
    executor = _production_executor(disk_backed_scratch_root, snapshot)
    assert hasattr(executor, "prepare_execution")
    accepted = next((workflow.base / "accepted").glob("g000001-*.txt"))
    spec = ExecutionSpec(**_production_inputs(
        workflow, accepted, plan, "descriptor-fixture"
    ))
    prepared = executor.prepare_execution(spec)
    descriptor = prepared.runtime_handle
    assert descriptor.get("capability_plan_sha256"), "BUBBLEWRAP_NOT_CONNECTED"
    assert descriptor["toolchains"] == [{
        "guest_root": "/opt/atlas/toolchains/rust",
        "mount": "ro",
    }]
    assert descriptor["caches"] == [{
        "guest_path": "/var/cache/atlas-agent/cargo",
        "mount": "rw",
    }]
    assert "/opt/atlas/toolchains/rust/bin" in descriptor["environment"]["PATH"]


def test_system_visible_capability_does_not_create_unrelated_usr_bind(
    tmp_path, monkeypatch, request
):
    _, workflow = _project(tmp_path, capabilities=False)
    if not shutil.which("bwrap") or not shutil.which("codex"):
        pytest.skip("Bubblewrap/native Codex unavailable")
    manifest = tmp_path / "system-capabilities.toml"
    executable = Path("/usr/bin/cat")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    probe = hashlib.sha256(b"\0").hexdigest()
    manifest.write_text(
        'schema = "atlas-agent-machine-capabilities/1"\n'
        f'persistent_cache_root = "{tmp_path / "persistent-caches"}"\n\n'
        "[toolchains.system]\nexposure = \"system-visible\"\n"
        'qualification = "system:true"\nsource_root = "/usr"\n'
        'guest_root = "/usr"\n\n'
        "[toolchains.system.commands.cat]\npath = \"bin/cat\"\n"
        f'sha256 = "{digest}"\nprobe_args = []\n'
        f'probe_output_sha256 = "{probe}"\n'
    )
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(manifest))
    _accept(workflow)
    accepted = next((workflow.base / "accepted").glob("g000001-*.txt"))
    plan = workflow.resolve_capabilities({"toolchains": ["system"], "caches": []})
    disk_backed_scratch_root = request.getfixturevalue("disk_backed_scratch_root")
    snapshot = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"),
        parse_prompt(accepted.read_bytes()),
    )
    executor = _production_executor(disk_backed_scratch_root, snapshot)
    # This assertion is intentionally made against a descriptor produced by
    # preparation.  Constructing a descriptor on a fresh executor would not
    # exercise capability authority at all.
    spec = ExecutionSpec(**_production_inputs(
        workflow, accepted, plan, "system-fixture"
    ))
    prepared = executor.prepare_execution(spec)
    descriptor = prepared.runtime_handle
    assert descriptor.get("capability_plan_sha256"), "BUBBLEWRAP_NOT_CONNECTED"
    mounts = descriptor.get("mounts", [])
    assert not any(
        mount.get("source") != mount.get("guest_path") and
        mount.get("guest_path") == "/usr/bin"
        for mount in mounts
    ), "BUBBLEWRAP_NOT_CONNECTED: unrelated system-visible bind"


def test_real_exec_server_child_receives_capability_environment(
    tmp_path, monkeypatch, request
):
    _, workflow = _project(tmp_path)
    if not shutil.which("bwrap") or not shutil.which("codex"):
        pytest.skip("Bubblewrap/native Codex unavailable")
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    plan = workflow.resolve_capabilities({"toolchains": ["rust"], "caches": ["cargo"]})
    disk_backed_scratch_root = request.getfixturevalue("disk_backed_scratch_root")
    snapshot = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"),
        parse_prompt(next((workflow.base / "accepted").glob("g000001-*.txt")).read_bytes()),
    )
    executor = _production_executor(disk_backed_scratch_root, snapshot)
    assert hasattr(executor, "start_exec_server"), "EXEC_SERVER_NOT_CONNECTED"
    accepted = next((workflow.base / "accepted").glob("g000001-*.txt"))
    spec = ExecutionSpec(**_production_inputs(
        workflow, accepted, plan, "exec-server-fixture"
    ))
    prepared = executor.prepare_execution(spec)
    # Do not replace the production exec-server with the old host-side probe.
    # Starting the real server is deliberately allowed to remain a product
    # failure until the namespace child is wired to process/read.
    executor.start_exec_server(prepared)
    sock = _ws_connect(executor._server_url)
    try:
        def request(request_id, method, params):
            _ws_send(sock, {"id": request_id, "method": method, "params": params})
            while True:
                message = _ws_recv(sock)
                if message.get("id") == request_id:
                    assert "error" not in message, message
                    return message["result"]

        request(1, "initialize", {"clientName": "atlas-agent-p06-test"})
        _ws_send(sock, {"method": "initialized", "params": {}})
        started = request(2, "process/start", {
            "processId": "p06-true", "argv": ["/bin/true"],
            "cwd": workflow.root.as_uri(), "env": {}, "tty": False,
            "arg0": "codex-linux-sandbox",
        })
        after_seq = None
        for read_id in range(3, 7):
            result = request(read_id, "process/read", {
                "processId": started["processId"], "afterSeq": after_seq,
                "maxBytes": 4096, "waitMs": 5000,
            })
            # afterSeq is the last sequence consumed, not the next sequence
            # to read.  Only advance it from chunks actually returned.
            returned_chunks = result.get("chunks", [])
            if returned_chunks:
                after_seq = max(
                    chunk["seq"] for chunk in returned_chunks
                    if isinstance(chunk, dict) and "seq" in chunk
                )
            if result["exited"]:
                break
        assert result["exited"] is True
        assert result["exitCode"] == 0
        # Keep the transport smoke test above, but also exercise the
        # controller-authored capability plan through the real namespace
        # child.  In particular, this must not be replaced with
        # exec_server_child(), which is only a host-side helper.
        started = request(4, "process/start", {
            "processId": "p06-capabilities",
            "argv": ["sh", "-c", (
                "set -eu; command -v cargo; cargo --version >/dev/null; "
                "mkdir -p \"$CARGO_HOME/g16\"; "
                "test -w \"$CARGO_HOME/g16\"; "
                "test ! -w /opt/atlas/toolchains/rust/bin/cargo; "
                "test \"$HOME\" = /home/atlas; "
                f"test \"$HOME\" != {shlex.quote(os.environ.get('HOME', ''))}; "
                "printf CAPABILITIES_OK"
            )],
            # process/start's env is the child environment, rather than an
            # overlay on the exec-server environment.
            "cwd": workflow.root.as_uri(), "env": plan.environment(), "tty": False,
            "arg0": "codex-linux-sandbox",
        })
        chunks = []
        after_seq = None
        capability_output = None
        for read_id in range(5, 9):
            capability_output = request(read_id, "process/read", {
                "processId": started["processId"], "afterSeq": after_seq,
                "maxBytes": 4096, "waitMs": 5000,
            })
            chunks.extend(capability_output.get("chunks", []))
            # The cursor records the greatest chunk sequence consumed.  Do
            # not use nextSeq here: it is one past the last returned chunk.
            returned_chunks = capability_output.get("chunks", [])
            if returned_chunks:
                after_seq = max(
                    chunk["seq"] for chunk in returned_chunks
                    if isinstance(chunk, dict) and "seq" in chunk
                )
            if capability_output["exited"]:
                break
        assert capability_output["exited"] is True
        assert capability_output["exitCode"] == 0

        output = bytearray()
        for chunk in chunks:
            payload = chunk["chunk"] if isinstance(chunk, dict) else chunk
            output.extend(base64.b64decode(payload, validate=True))
        assert b"CAPABILITIES_OK" in output
    finally:
        sock.close()
        executor._stop_server()


def test_outer_codex_client_receives_capability_environment(
    tmp_path, monkeypatch, request
):
    """Atlas passes the sealed plan environment to the outer Codex client."""
    _, workflow = _project(tmp_path)
    if not shutil.which("bwrap") or not shutil.which("codex"):
        pytest.skip("Bubblewrap/native Codex unavailable")
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    plan = workflow.resolve_capabilities({"toolchains": ["rust"], "caches": ["cargo"]})
    accepted = next((workflow.base / "accepted").glob("g000001-*.txt"))
    snapshot = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"),
        parse_prompt(accepted.read_bytes()),
    )
    executor = _production_executor(
        request.getfixturevalue("disk_backed_scratch_root"), snapshot
    )
    spec = ExecutionSpec(**_production_inputs(
        workflow, accepted, plan, "outer-client-environment"
    ))
    try:
        executor.prepare_execution(spec)
        # _environment is the outer-client boundary.  A valid server URL is
        # sufficient here; the real child boundary is covered above.
        executor._server_url = "ws://127.0.0.1:43123"
        environment = executor._environment()
        expected = plan.environment()
        for key in ("PATH", "CARGO_HOME", "HOME", "TMPDIR", "TMP", "TEMP"):
            assert environment[key] == expected[key]
        assert environment["HOME"] == "/home/atlas"
        assert environment["HOME"] != os.environ.get("HOME", "")
    finally:
        executor._stop_server()


def test_durable_surfaces_bind_capability_provenance(tmp_path, monkeypatch):
    _, workflow = _project(tmp_path)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="durable-thread-1"))
    state = workflow._state()
    owner = state["generations"]["1"]["execution"]
    execution = json.loads(
        (workflow.base / owner["report_dir"] / "execution.json").read_text()
    )
    archive = workflow.base / "reports" / "capabilities" / (
        owner["execution_id"] + ".json"
    )
    assert archive.is_file(), "PRODUCT: dedicated capability archive missing"
    archived = json.loads(archive.read_text())
    for surface in (owner, execution):
        assert surface.get("capability_plan_sha256"), "PROVENANCE_NOT_CONNECTED"
        assert surface["capability_qualification"] == "rust:1"
        assert surface["cache_guest_path"] == "/var/cache/atlas-agent/cargo"
        assert surface["cache_lifetime"] == "persistent"
        assert surface["mutable_unhashed_cache"] is True
    assert archived["capability_plan_sha256"] == owner["capability_plan_sha256"]
    # The digest is useful only if the durable archive retains the facts that
    # produced it.  These are immutable qualification facts, not cache bytes.
    assert archived["toolchains"][0]["source_root"]
    assert archived["toolchains"][0]["commands"][0]["probe_args"]
    assert archived["toolchains"][0]["commands"][0]["probe_output_sha256"]
    assert archived["toolchains"][0]["commands"][0]["observed_version"]
    assert archived["caches"][0]["qualification"]
    assert archived["caches"][0]["scope"]
    assert execution["capability_plan_sha256"] == archived["capability_plan_sha256"]
    assert execution["capability_provenance"]["capability_plan_sha256"] == (
        archived["capability_plan_sha256"]
    )


def test_current_capability_free_execution_uses_current_schema_pairing(
    tmp_path, monkeypatch
):
    _, workflow = _project(tmp_path, capabilities=False)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    class DescriptorFake(FakeExecutor):
        def prepare_execution(self, spec):
            prepared = super().prepare_execution(spec)
            return PreparedExecution(
                prepared.spec, prepared.executor, prepared.command,
                prepared.version, prepared.permission_envelope,
                prepared.policy_snapshot, {
                    "schema": "atlas-bwrap/1", "provider": "atlas",
                    "backend": "bubblewrap", "filesystem_mode": "workspace-write",
                    "filesystem_enforcement": "atlas-bwrap",
                    "process_enforcement": "atlas-bwrap", "network_enforcement": "codex",
                    "requested_network_access": False, "resolved_network_access": False,
                    "user_namespace": "bwrap-default", "pid_namespace": True,
                    "ipc_namespace": True, "mount_roles": [],
                    "temporary_storage": {
                        "tmp": "private-tmpfs", "shm": "private-tmpfs",
                        "var_tmp": "private-disk-scratch",
                    },
                    "bwrap": "bwrap", "bwrap_version": "1", "codex_executable": "codex",
                    "codex_version": "1", "scratch_backing_class": "disk",
                    "exec_server_transport": "websocket-loopback",
                    "inner_codex_sandbox": "workspace-write",
                    "inner_codex_network": "restricted",
                },
            )

    workflow.execute(1, DescriptorFake(observed_thread_id="schema-pairing"))
    execution = workflow._state()["generations"]["1"]["execution"]
    snapshot = execution["policy_snapshot"]
    assert snapshot["schema"] == "atlas-agent-policy-snapshot/3"
    assert execution["owner_schema"] == "atlas-agent-execution-owner/3"
    assert execution["provenance_version"] == 3
    assert execution["execution_backend_schema"] == "atlas-bwrap-execution/2"


def test_start_run_cannot_replace_derived_empty_capability_plan(
    tmp_path, monkeypatch
):
    _, workflow = _project(tmp_path, capabilities=False)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    accepted = next((workflow.base / "accepted").glob("g000001-*.txt"))
    prompt = parse_prompt(accepted.read_bytes())
    derived = resolve_policy(
        load_policy(workflow.root / "atlas-agent-policy.toml"), prompt
    )
    supplied = dict(derived)
    supplied["required_toolchains"] = ["rust"]
    supplied["writable_caches"] = ["cargo"]
    with pytest.raises(Exception, match="CAPABILITY|PROVENANCE|PLAN"):
        workflow.start_run(1, execution={
            "execution_id": "start-run-capability-bypass",
            "report_dir": "reports/executions/start-run-capability-bypass",
            "policy_snapshot": supplied,
        })
    assert not any(event["event"] == "RUN_STARTED" for event in _events(workflow))


@pytest.mark.parametrize("schema_kind", ["policy", "snapshot-v1", "snapshot-v2"])
def test_start_run_rejects_replay_only_schema_as_new_execution(
    tmp_path, schema_kind
):
    _, workflow = _project(tmp_path, capabilities=False)
    _accept(workflow, prompt_schema=1 if schema_kind == "snapshot-v1" else 2)
    historical = json.loads(json.dumps(
        load_policy(workflow.root / "atlas-agent-policy.toml")
    ))
    historical["schema"] = "atlas-agent-policy/1"
    for profile in historical["profiles"].values():
        if profile.get("executor") == "codex":
            profile.pop("required_toolchains", None)
            profile.pop("writable_caches", None)
    # This is an independently valid historical policy authority, not a
    # current policy with only its schema label changed.
    workflow._policy_for = lambda record: historical
    accepted = next((workflow.base / "accepted").glob("*.txt"))
    prompt_bytes = accepted.read_bytes()
    prompt = parse_prompt(prompt_bytes)
    snapshot = resolve_policy(historical, prompt)
    if schema_kind == "snapshot-v1":
        snapshot = dict(snapshot)
        snapshot["schema"] = "atlas-agent-policy-snapshot/1"
        for key in (
            "codex_profile", "codex_binary_sha256", "codex_config_sha256",
            "codex_catalog_sha256", "codex_profile_sha256",
        ):
            snapshot.pop(key, None)
    elif schema_kind == "snapshot-v2":
        # resolve_policy() against the independently valid /1 policy already
        # produces the historical, capability-free /2 snapshot.
        assert snapshot["schema"] == "atlas-agent-policy-snapshot/2"
    execution_id = "123e4567-e89b-12d3-a456-426614174000"
    execution = {
        "execution_id": execution_id,
        "executor": "codex",
        "started_at": "2026-01-01T00:00:00Z",
        "pid": 123,
        "report_dir": f"reports/executions/{execution_id}",
        "owner_schema": "atlas-agent-execution-owner/3",
        "policy_snapshot": snapshot,
        "permission_envelope": {
            "sandbox_mode": snapshot["sandbox_mode"],
            "approval_policy": "never",
            "approvals_reviewer": "user",
            "strict_config": True,
            "ignore_rules": True,
            "network_access": snapshot["network_access"],
        },
    }
    with pytest.raises(Exception, match="REPLAY_ONLY|POLICY_REPLAY_ONLY"):
        workflow.start_run(1, execution=execution)
    assert not any(event["event"] == "RUN_STARTED" for event in _events(workflow))
    assert not (workflow.base / "reports" / "policies" /
                f"{execution_id}.json").exists()


def test_journal_rejects_current_owner_snapshot_with_historical_backend(tmp_path):
    """The real journal must reject a /3 owner paired with backend /1."""
    from tools.atlas_agent.journal import JournalError, _hash_event, canonical

    _, workflow = _project(tmp_path, capabilities=False)
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="schema-tamper"))
    path = workflow.journal.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    started = next(row for row in rows if row["event"] == "RUN_STARTED")
    started["payload"]["execution"]["execution_backend_schema"] = (
        "atlas-bwrap-execution/1"
    )
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        row["event_sha256"] = _hash_event(row)
        previous = row["event_sha256"]
    path.write_text("".join(canonical(row) + "\n" for row in rows))
    with pytest.raises(JournalError, match="schema|provenance|backend|owner"):
        workflow.journal.read()


def test_journal_accepts_transitional_historical_schema_tuple(tmp_path):
    """A synthetic journal record with the genuine transitional tuple replays."""
    from tools.atlas_agent.journal import _hash_event, canonical
    from tools.atlas_agent.workflow import replay_journal

    _, workflow = _project(tmp_path, capabilities=False)
    _accept(workflow)

    class DescriptorFake(FakeExecutor):
        def prepare_execution(self, spec):
            prepared = super().prepare_execution(spec)
            return PreparedExecution(
                prepared.spec, prepared.executor, prepared.command,
                prepared.version, prepared.permission_envelope,
                prepared.policy_snapshot, {
                    "schema": "atlas-bwrap/1", "provider": "atlas",
                    "backend": "bubblewrap", "filesystem_mode": "workspace-write",
                    "filesystem_enforcement": "atlas-bwrap",
                    "process_enforcement": "atlas-bwrap", "network_enforcement": "codex",
                    "requested_network_access": False, "resolved_network_access": False,
                    "user_namespace": "bwrap-default", "pid_namespace": True,
                    "ipc_namespace": True, "mount_roles": [],
                    "temporary_storage": {
                        "tmp": "private-tmpfs", "shm": "private-tmpfs",
                        "var_tmp": "private-disk-scratch",
                    },
                    "bwrap": "bwrap", "bwrap_version": "1", "codex_executable": "codex",
                    "codex_version": "1", "scratch_backing_class": "disk",
                    "exec_server_transport": "websocket-loopback",
                    "inner_codex_sandbox": "workspace-write",
                    "inner_codex_network": "restricted",
                },
            )

    workflow.execute(1, DescriptorFake(observed_thread_id="transitional-tuple"))
    path = workflow.journal.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        execution = (row.get("payload") or {}).get("execution")
        if isinstance(execution, dict):
            execution["execution_backend_schema"] = "atlas-bwrap-execution/1"
            for key in ("capability_plan_sha256", "toolchains", "caches", "environment"):
                (execution.get("sandbox") or {}).pop(key, None)
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        row["event_sha256"] = _hash_event(row)
        previous = row["event_sha256"]
    path.write_text("".join(canonical(row) + "\n" for row in rows))

    events = workflow.journal.read()
    assert replay_journal(events)["generations"]["1"]["status"] == "COMPLETED"


def test_native_bubblewrap_preflight_checks_command_discovery_identity(
    tmp_path, monkeypatch
):
    """An absolute command succeeding is insufficient when PATH is poisoned."""
    if shutil.which("bwrap") is None or not shutil.which("sh"):
        pytest.skip("native Bubblewrap facilities unavailable")
    _, workflow = _project(tmp_path)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    plan = workflow.resolve_capabilities({"toolchains": ["rust"], "caches": []})
    # Keep the qualified absolute executable mountable, but make command
    # discovery resolve somewhere else.  The native namespace must reject it.
    from types import MappingProxyType
    plan._environment = MappingProxyType({
        **plan.environment(), "PATH": "/usr/bin:/bin"
    })
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    executor._capability_plan = plan
    with pytest.raises(Exception, match="PROBE|QUALIFICATION|DISCOVERY|COMMAND"):
        executor._capability_probe()


def test_new_execution_rejects_replay_only_policy_and_snapshot_schemas(tmp_path):
    from tools.atlas_agent.policy import validate_policy

    _, workflow = _project(tmp_path, capabilities=False)
    policy = load_policy(workflow.root / "atlas-agent-policy.toml")
    legacy_policy = json.loads(json.dumps(policy))
    legacy_policy["schema"] = "atlas-agent-policy/1"
    for profile in legacy_policy["profiles"].values():
        if profile.get("executor") == "codex":
            for key in ("required_toolchains", "writable_caches"):
                profile.pop(key, None)
    validate_policy(legacy_policy)  # historical parsing remains supported
    (workflow.root / "atlas-agent-policy.toml").write_text(
        (workflow.root / "atlas-agent-policy.toml").read_text().replace(
            'schema = "atlas-agent-policy/2"',
            'schema = "atlas-agent-policy/1"', 1
        ).replace(
            'required_toolchains = []\n', '', 1
        ).replace(
            'writable_caches = []\n', '', 1
        )
    )
    _accept(workflow)
    with pytest.raises(Exception, match="UNKNOWN_GENERATION|CURRENT|REPLAY|HISTORICAL|SCHEMA|POLICY"):
        workflow.execute(1, FakeExecutor(observed_thread_id="historical-policy"))


def test_journal_rejects_mixed_historical_and_current_schema_tuple(tmp_path):
    from tools.atlas_agent.journal import JournalError, _hash_event, canonical

    _, workflow = _project(tmp_path, capabilities=False)
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="tuple-thread"))
    path = workflow.journal.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    started = next(row for row in rows if row["event"] == "RUN_STARTED")
    started["payload"]["execution"]["policy_snapshot"]["schema"] = (
        "atlas-agent-policy-snapshot/2"
    )
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        row["event_sha256"] = _hash_event(row)
        previous = row["event_sha256"]
    path.write_text("".join(canonical(row) + "\n" for row in rows))
    with pytest.raises(JournalError, match="schema|provenance|snapshot|owner"):
        workflow.journal.read()


@pytest.mark.parametrize(("field", "value"), [
    ("owner_schema", "atlas-agent-execution-owner/2"),
    ("policy_snapshot.schema", "atlas-agent-policy-snapshot/2"),
    ("provenance_version", 2),
    ("execution_backend_schema", "atlas-bwrap-execution/1"),
])
def test_journal_rejects_each_mixed_schema_tuple_even_when_versions_are_valid(
    tmp_path, field, value
):
    from tools.atlas_agent.journal import JournalError, _hash_event, canonical

    _, workflow = _project(tmp_path, capabilities=False)
    _accept(workflow)
    class DescriptorFake(FakeExecutor):
        def prepare_execution(self, spec):
            prepared = super().prepare_execution(spec)
            return PreparedExecution(
                prepared.spec, prepared.executor, prepared.command,
                prepared.version, prepared.permission_envelope,
                prepared.policy_snapshot, {
                    "schema": "atlas-bwrap/1", "provider": "atlas",
                    "backend": "bubblewrap", "filesystem_mode": "workspace-write",
                    "filesystem_enforcement": "atlas-bwrap",
                    "process_enforcement": "atlas-bwrap", "network_enforcement": "codex",
                    "requested_network_access": False, "resolved_network_access": False,
                    "user_namespace": "bwrap-default", "pid_namespace": True,
                    "ipc_namespace": True, "mount_roles": [],
                    "temporary_storage": {
                        "tmp": "private-tmpfs", "shm": "private-tmpfs",
                        "var_tmp": "private-disk-scratch",
                    },
                    "bwrap": "bwrap", "bwrap_version": "1", "codex_executable": "codex",
                    "codex_version": "1", "scratch_backing_class": "disk",
                    "exec_server_transport": "websocket-loopback",
                    "inner_codex_sandbox": "workspace-write",
                    "inner_codex_network": "restricted",
                },
            )

    workflow.execute(1, DescriptorFake(observed_thread_id="tuple-matrix"))
    path = workflow.journal.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    started = next(row for row in rows if row["event"] == "RUN_STARTED")
    execution = started["payload"]["execution"]
    # Each negative case begins with a valid current tuple.  Historical
    # snapshot/backend values are independently valid shapes below, rather
    # than current objects relabelled as legacy data.
    if field == "policy_snapshot.schema":
        historical = json.loads(json.dumps(
            load_policy(workflow.root / "atlas-agent-policy.toml")
        ))
        historical["schema"] = "atlas-agent-policy/1"
        for profile in historical["profiles"].values():
            if profile.get("executor") == "codex":
                profile.pop("required_toolchains", None)
                profile.pop("writable_caches", None)
        prompt_path = workflow.base / "prompts" / (
            workflow._state()["generations"]["1"]["prompt_sha256"] + ".txt"
        )
        historical_snapshot = resolve_policy(
            historical, parse_prompt(prompt_path.read_bytes())
        )
        execution["policy_snapshot"] = historical_snapshot
        value = historical_snapshot["schema"]
    elif field == "execution_backend_schema":
        descriptor = execution["sandbox"]
        for key in ("capability_plan_sha256", "toolchains", "caches", "environment"):
            descriptor.pop(key, None)
        # Backend /1 is a supported transitional tuple when the other
        # versions are /3; retain a genuinely mixed negative case here.
        execution["provenance_version"] = 2
    target = execution
    key = field
    if "." in field:
        key, nested = field.split(".", 1)
        target = execution[key]
        target[nested] = value
    else:
        target[key] = value
    # Terminal events carry the same owner copy; keep the tamper structural so
    # the journal reaches tuple validation rather than alias consistency.
    for row in rows:
        other = (row.get("payload") or {}).get("execution")
        if isinstance(other, dict):
            if "." in field:
                other[key][nested] = value
            else:
                other[key] = value
            if field == "execution_backend_schema":
                for descriptor_key in ("capability_plan_sha256", "toolchains",
                                       "caches", "environment"):
                    (other.get("sandbox") or {}).pop(descriptor_key, None)
                other["provenance_version"] = 2
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        row["event_sha256"] = _hash_event(row)
        previous = row["event_sha256"]
    path.write_text("".join(canonical(row) + "\n" for row in rows))
    with pytest.raises(JournalError, match="schema|provenance|backend|owner|snapshot"):
        workflow.journal.read()


def test_durable_plan_hash_surfaces_are_cross_bound_and_tamper_evident(tmp_path):
    from tools.atlas_agent.journal import JournalError, _hash_event, canonical

    _, workflow = _project(tmp_path)
    # The test exercises the durable publication after capability resolution.
    # The authority file is deliberately outside the repository.
    workflow._capability_file = tmp_path / "machine-capabilities.toml"
    os.environ["ATLAS_AGENT_CAPABILITIES_FILE"] = str(workflow._capability_file)
    _accept(workflow)
    try:
        workflow.execute(1, FakeExecutor(observed_thread_id="cross-bound-thread"))
    finally:
        os.environ.pop("ATLAS_AGENT_CAPABILITIES_FILE", None)
    path = workflow.journal.path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    started = next(row for row in rows if row["event"] == "RUN_STARTED")
    execution = started["payload"]["execution"]
    surface = execution.get("sandbox", execution)
    surface["capability_plan_sha256"] = "f" * 64
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        row["event_sha256"] = _hash_event(row)
        previous = row["event_sha256"]
    path.write_text("".join(canonical(row) + "\n" for row in rows))
    with pytest.raises(JournalError, match="PLAN|PROVENANCE|DESCRIPTOR|MISMATCH"):
        workflow.journal.read()


def test_durable_archive_rejects_nested_capability_provenance_cross_binding(
    tmp_path, monkeypatch
):
    from tools.atlas_agent.journal import _hash_event, canonical

    _, workflow = _project(tmp_path)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="nested-provenance"))
    owner = workflow._state()["generations"]["1"]["execution"]
    archive = workflow.base / owner["capability_archive_path"]
    data = json.loads(archive.read_text())
    # Keep the archive and its own recorded digest internally coherent, while
    # binding its nested facts to a different plan than the owner claims.
    data["capability_provenance"]["capability_plan_sha256"] = "f" * 64
    data["capability_provenance"]["toolchains"][0]["qualification"] = "rust:tampered"
    canonical_archive = {
        key: data[key] for key in data if key != "archive_sha256"
    }
    data["archive_sha256"] = hashlib.sha256(json.dumps(
        canonical_archive, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    archive.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    rows = [json.loads(line) for line in workflow.journal.path.read_text().splitlines()]
    started = next(row for row in rows if row["event"] == "RUN_STARTED")
    started["payload"]["execution"]["capability_archive_sha256"] = hashlib.sha256(
        archive.read_bytes()).hexdigest()
    for row in rows:
        other = (row.get("payload") or {}).get("execution")
        if isinstance(other, dict):
            other["capability_archive_sha256"] = started["payload"]["execution"][
                "capability_archive_sha256"
            ]
    previous = "0" * 64
    for row in rows:
        row["previous_event_sha256"] = previous
        row["event_sha256"] = _hash_event(row)
        previous = row["event_sha256"]
    workflow.journal.path.write_text(
        "".join(canonical(row) + "\n" for row in rows)
    )
    with pytest.raises(Exception, match="PROVENANCE|CAPABILITY|TAMPER|PLAN"):
        workflow.rebuild()


def test_controller_reuse_uses_production_capability_compatibility(tmp_path, monkeypatch):
    _, workflow = _project(tmp_path)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="thread-1"))
    execution_id = workflow._state()["generations"]["1"]["execution"]["execution_id"]
    _accept(workflow, 2, session="reuse", target=execution_id)
    workflow.execute(2, FakeExecutor(observed_thread_id="thread-1"))
    second = next(
        event["payload"] for event in _events(workflow)
        if event["event"] == "RUN_STARTED" and event["payload"]["generation"] == 2
    )
    assert second["execution"]["policy_snapshot"]["session_mode_resolved"] == "reuse"

    # Change only the valid immutable capability identity.  Content in the
    # mutable cache namespace is intentionally not part of this comparison.
    cache_plan = workflow.resolve_capabilities({"toolchains": ["rust"], "caches": ["cargo"]})
    cache_plan.caches[0].backing.parent.mkdir(parents=True, exist_ok=True)
    cache_plan.caches[0].backing.write_text("mutable fixture content")
    manifest = (tmp_path / "machine-capabilities.toml").read_text()
    (tmp_path / "machine-capabilities.toml").write_text(
        manifest.replace('qualification = "rust:1"', 'qualification = "rust:2"', 1)
    )
    _accept(workflow, 3, session="reuse",
            target=workflow._state()["generations"]["2"]["execution"]["execution_id"])
    workflow.execute(3, FakeExecutor(observed_thread_id="thread-1"))
    third = next(
        event["payload"] for event in _events(workflow)
        if event["event"] == "RUN_STARTED" and event["payload"]["generation"] == 3
    )
    assert third["execution"]["policy_snapshot"]["session_mode_resolved"] == "fresh"
    assert third["execution"]["policy_snapshot"]["reuse_fallback_reason"] == "incompatible_capabilities"
    workflow._preflight()
    assert workflow.rebuild()["generations"]["3"]["status"] == "COMPLETED"


@pytest.mark.parametrize(
    ("session", "observed"),
    [("fresh", "history-thread-1"), ("reuse", "wrong-thread")],
)
def test_interrupted_invalid_session_observation_rebuilds_as_history(
    tmp_path, session, observed
):
    _, workflow = _project(tmp_path, capabilities=False)
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="history-thread-1"))
    first = workflow._state()["generations"]["1"]["execution"]
    if session == "reuse":
        _accept(workflow, 2, session="reuse", target=first["execution_id"])
    else:
        _accept(workflow, 2, session="fresh")
    generation = 2
    if session == "fresh":
        with pytest.raises(Exception, match="FRESHNESS_VIOLATION"):
            workflow.execute(generation, FakeExecutor(observed_thread_id=observed))
    else:
        with pytest.raises(Exception, match="REUSE_THREAD_MISMATCH"):
            workflow.execute(generation, FakeExecutor(observed_thread_id=observed))
    interrupted = workflow._state()["generations"][str(generation)]
    assert interrupted["status"] == "INTERRUPTED"
    workflow._preflight()
    assert workflow.rebuild()["generations"][str(generation)]["status"] == "INTERRUPTED"


def test_historical_validation_does_not_consult_current_assets(tmp_path, monkeypatch):
    _, workflow = _project(tmp_path, capabilities=False)
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="asset-history"))

    def current_assets_are_unavailable(*args, **kwargs):
        raise AssertionError("historical validation consulted current assets")

    monkeypatch.setattr(
        "tools.atlas_agent.policy.asset_set_identity",
        current_assets_are_unavailable,
    )
    monkeypatch.setattr(
        "tools.atlas_agent.policy.prompt_set_identity",
        current_assets_are_unavailable,
    )
    workflow._preflight()
    assert workflow.rebuild()["generations"]["1"]["status"] == "COMPLETED"


def test_historical_capability_validation_uses_archive_and_detects_tamper(tmp_path, monkeypatch):
    repo, workflow = _project(tmp_path)
    monkeypatch.setenv("ATLAS_AGENT_CAPABILITIES_FILE", str(
        tmp_path / "machine-capabilities.toml"
    ))
    _accept(workflow)
    workflow.execute(1, FakeExecutor(observed_thread_id="history-thread-1"))
    state = workflow._state()
    owner = state["generations"]["1"]["execution"]
    archive = workflow.base / "reports" / "capabilities" / (
        owner["execution_id"] + ".json"
    )
    assert archive.is_file(), "PRODUCT: dedicated capability archive missing"
    original = archive.read_bytes()
    (repo / "atlas-agent-policy.toml").unlink()
    assert workflow.rebuild()["generations"]["1"]["status"] == "COMPLETED"
    archive.write_bytes(original.replace(b"rust:1", b"rust:9"))
    with pytest.raises(Exception, match="PROVENANCE|HISTORICAL|TAMPER"):
        workflow.rebuild()


def test_pre_run_failure_preserves_p05_resource_ownership(tmp_path):
    _, workflow = _project(tmp_path)
    _accept(workflow)
    executor = AtlasBubblewrapExecutor(scratch_root=tmp_path / "scratch")
    with pytest.raises(Exception) as caught:
        workflow.execute(1, executor)
    assert "ATLAS_" in str(caught.value), "P05 ownership failure was not injected at production boundary"
    assert workflow._state()["generations"]["1"]["status"] == "ACCEPTED"
    assert not any(event["event"] == "RUN_STARTED" for event in _events(workflow))
    assert not executor._run_lock.locked(), "P05 ownership was not released"
