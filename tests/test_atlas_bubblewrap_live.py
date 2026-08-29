"""Capability-gated tests of the actual bubblewrap boundary."""
import os
import select
import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest

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
