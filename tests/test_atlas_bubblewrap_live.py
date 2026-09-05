"""Capability-gated tests of the actual bubblewrap boundary."""
import os
import base64
import json
import select
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
import pytest

from tools.atlas_agent.bubblewrap import AtlasBubblewrapExecutor, AtlasSandboxError, _native_codex
from tools.atlas_agent.executor import ExecutionSpec
from tools.atlas_agent.policy import load_policy, resolve_policy
from tools.atlas_agent.prompt import parse_prompt


def _current_policy_snapshot():
    """Resolve the live fixture through the current policy authority."""
    raw = b"""+++
schema = "atlas-agent-prompt/2"
generation = 1
parent = "genesis"
checkpoint = "live"
action = "patch_review"
expected_head = "0000000000000000000000000000000000000000"
session_mode = "fresh"
network_access = false
+++
live bubblewrap fixture
"""
    prompt = parse_prompt(raw)
    policy = load_policy(Path(__file__).parents[1] / "atlas-agent-policy.toml")
    return resolve_policy(policy, prompt)


def _ws_send(sock, value):
    payload = json.dumps(value, separators=(",", ":")).encode()
    mask = os.urandom(4)
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126); header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127); header.extend(length.to_bytes(8, "big"))
    sock.sendall(header + mask + bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload)))


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
        opcode = first & 0x0f
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
        if opcode == 0x9:
            sock.sendall(bytes([0x8a, len(payload)]) + payload)
            continue
        if opcode == 0x8:
            raise AssertionError("exec-server websocket closed")
        if opcode == 0x1:
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

def _command(tmp_path, script, writable=False, scratch=None):
    repo=tmp_path/"repo"; repo.mkdir(exist_ok=True)
    (repo/"tracked").write_text("before")
    git=repo/".git"; git.mkdir(exist_ok=True)
    (git/"index").write_text("index"); (git/"config").write_text("config")
    (git/"atlas-agent").mkdir(exist_ok=True); (git/"atlas-agent"/"state").write_text("state")
    (git/"refs"/"heads").mkdir(parents=True,exist_ok=True); (git/"refs"/"heads"/"main").write_text("ref")
    (git/"hooks").mkdir(exist_ok=True); (git/"hooks"/"pre-commit").write_text("hook")
    scratch=scratch or tmp_path/"scratch"; scratch.mkdir(exist_ok=True)
    mode="--bind" if writable else "--ro-bind"
    cmd=["bwrap","--die-with-parent","--new-session","--unshare-pid","--unshare-ipc","--ro-bind","/usr","/usr","--ro-bind","/lib","/lib","--ro-bind","/lib64","/lib64","--symlink","usr/bin","/bin","--proc","/proc","--dev","/dev","--tmpfs","/tmp","--tmpfs","/dev/shm","--tmpfs","/home","--dir","/home/atlas","--dir","/home/atlas/.codex","--dir","/var","--bind",str(scratch),"/var/tmp",mode,str(repo),"/workspace","--ro-bind",str(git),"/workspace/.git","--clearenv","--setenv","HOME","/home/atlas","--setenv","CODEX_HOME","/home/atlas/.codex","--chdir","/workspace","--","/bin/sh","-c",script]
    return cmd

def _run(tmp_path, script, writable=False, scratch=None, pass_fds=()):
    result=subprocess.run(_command(tmp_path, script, writable, scratch),text=True,
                          capture_output=True,timeout=5,pass_fds=pass_fds)
    if result.returncode and any(x in result.stderr.lower() for x in ("user namespace","operation not permitted","permission denied")):
        pytest.skip(result.stderr.strip()[:200])
    return result

def test_live_effective_filesystem_permissions(tmp_path):
    script="""
set -eu
printf changed > /workspace/tracked
: > /workspace/created
for p in .git/index .git/config .git/atlas-agent/state .git/refs/heads/main .git/hooks/pre-commit; do
  printf denied > /workspace/$p 2>/dev/null && exit 12 || :
done
test "$(cat /workspace/tracked)" = changed
"""
    # This is one implementation-mode namespace: the outer worktree is
    # writable, while the nested .git mount remains read-only.
    assert _run(tmp_path,script,True).returncode==0
    repo=tmp_path/"repo"; assert (repo/"tracked").read_text()=="changed" and (repo/"created").is_file()
    assert (repo/".git"/"index").read_text()=="index" and (repo/".git"/"config").read_text()=="config"
    assert (repo/".git"/"atlas-agent"/"state").read_text()=="state"
    assert (repo/".git"/"refs"/"heads"/"main").read_text()=="ref"
    assert (repo/".git"/"hooks"/"pre-commit").read_text()=="hook"

def test_live_storage_home_and_privacy(tmp_path):
    host=tmp_path/"host-only"/".codex"; host.mkdir(parents=True); (host/"sentinel").write_text("secret")
    marker="atlas-private-marker"; first=Path(tempfile.mkdtemp(prefix="atlas-live-one-",dir="."))
    script=f"""
set -eu
test \"$HOME\" = /home/atlas; test \"$CODEX_HOME\" = /home/atlas/.codex
test -w /home/atlas; test -w /home/atlas/.codex; test ! -e /home/atlas/.codex/sentinel
test \"$(stat -f -c %T /tmp)\" = tmpfs; test \"$(stat -f -c %T /dev/shm)\" = tmpfs
test \"$(stat -f -c %T /var/tmp)\" != tmpfs
printf x >/tmp/{marker}; printf x >/dev/shm/{marker}; printf x >/var/tmp/{marker}
"""
    second=Path(tempfile.mkdtemp(prefix="atlas-live-two-",dir="."))
    try:
        assert _run(tmp_path,script,scratch=first).returncode==0 and (first/marker).exists()
        assert _run(tmp_path,f"test ! -e /tmp/{marker}; test ! -e /dev/shm/{marker}; test ! -e /var/tmp/{marker}",scratch=second).returncode==0
    finally:
        shutil.rmtree(first,ignore_errors=True); shutil.rmtree(second,ignore_errors=True)

def test_live_pid_namespace_reaps_setsid_descendant(tmp_path):
    ready_read,ready_write=os.pipe()
    held_read,held_write=os.pipe()
    control_read,control_write=os.pipe()
    script=(f"(setsid sh -c 'printf READY >&3; while :; do sleep 1; done' "
            f"3>&{ready_write} 4>&{held_write}) & read -r _ <&{control_read}")
    process=subprocess.Popen(_command(tmp_path,script),stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             pass_fds=(ready_write,held_write,control_read))
    try:
        for fd in (ready_write,held_write,control_read): os.close(fd)
        assert select.select([ready_read],[],[],2)[0]
        assert os.read(ready_read,5)==b"READY"
        # READY precedes teardown, and the second inherited descriptor proves
        # the setsid descendant is still alive at this point.
        assert not select.select([held_read],[],[],.2)[0]
        process.kill()  # trigger bwrap namespace teardown
        process.wait(timeout=3)
        assert select.select([held_read],[],[],2)[0]
        assert os.read(held_read,1)==b""
    finally:
        for fd in (ready_read,held_read,control_read,ready_write,held_write,control_write):
            try: os.close(fd)
            except OSError: pass
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)


def test_live_sealed_codex_exec_server_uses_opt_runtime(tmp_path):
    """The real server must create its sandbox launcher from /opt/atlas-codex."""
    if shutil.which("bwrap") is None:
        pytest.skip("bubblewrap unavailable")
    executable = os.environ.get("ATLAS_CODEX_EXECUTABLE", "codex")
    executor = AtlasBubblewrapExecutor(executable=executable, scratch_root=tmp_path / "scratch")
    native = _native_codex(executor.executable)
    if native is None:
        pytest.skip("installed native Codex unavailable")

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    snapshot = _current_policy_snapshot()
    spec = ExecutionSpec(1, "0" * 64, "patch_review", repo / "prompt", repo,
                        "live-runtime", tmp_path / "report", tmp_path / "runtime",
                        policy_snapshot=snapshot)

    fd = executor._sealed_runtime_fd(snapshot)
    runtime = tmp_path / "scratch" / "control" / "live-runtime.runtime"
    try:
        try:
            executor._start_server(spec, fd)
        except AtlasSandboxError as error:
            if any(token in str(error).lower() for token in
                   ("user namespace", "operation not permitted", "permission denied")):
                pytest.skip(str(error))
            raise
        # CODEX_HOME is the run-private scratch directory mounted by the
        # executor.  Do not replace that mount with the qualified canonical
        # home just to make the old observation path work.
        execution_home = executor._scratch
        assert execution_home is not None
        links = list(execution_home.glob("tmp/arg0/*/codex-linux-sandbox"))
        assert runtime.exists()
        assert links and links[0].is_symlink()
        assert os.readlink(links[0]) == "/opt/atlas-codex"
        assert "(deleted)" not in os.readlink(links[0])
    finally:
        try:
            executor._stop_server()
            assert not runtime.exists()
        finally:
            os.close(fd)


def test_live_exec_server_spawns_true_through_linux_sandbox(tmp_path):
    """Exercise process/start and process/read with no model or Codex turn."""
    if shutil.which("bwrap") is None:
        pytest.skip("bubblewrap unavailable")
    executor = AtlasBubblewrapExecutor(
        executable=os.environ.get("ATLAS_CODEX_EXECUTABLE", "codex"),
        scratch_root=tmp_path / "scratch",
    )
    native = _native_codex(executor.executable)
    if native is None:
        pytest.skip("installed native Codex unavailable")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    snapshot = _current_policy_snapshot()
    spec = ExecutionSpec(1, "0" * 64, "patch_review", repo / "prompt", repo,
                        "live-process", tmp_path / "report", tmp_path / "runtime",
                        policy_snapshot=snapshot)
    fd = executor._sealed_runtime_fd(snapshot)
    sock = None
    try:
        try:
            executor._start_server(spec, fd)
        except AtlasSandboxError as error:
            if any(token in str(error).lower() for token in
                   ("user namespace", "operation not permitted", "permission denied")):
                pytest.skip(str(error))
            raise
        sock = _ws_connect(executor._server_url)

        def request(request_id, method, params):
            _ws_send(sock, {"id": request_id, "method": method, "params": params})
            while True:
                message = _ws_recv(sock)
                if message.get("id") == request_id:
                    assert "error" not in message, message
                    return message["result"]

        request(1, "initialize", {"clientName": "atlas-agent-test"})
        _ws_send(sock, {"method": "initialized", "params": {}})
        started = request(2, "process/start", {
            "processId": "true-zero-token",
            "argv": ["/bin/true"],
            "cwd": repo.as_uri(),
            "env": {},
            "tty": False,
            "arg0": "codex-linux-sandbox",
        })
        process_id = started["processId"]
        result = request(3, "process/read", {
            "processId": process_id,
            "afterSeq": None,
            "maxBytes": 4096,
            "waitMs": 5000,
        })
        assert result["exited"] is True
        assert result["exitCode"] == 0
    finally:
        if sock is not None:
            sock.close()
        try:
            executor._stop_server()
        finally:
            os.close(fd)
