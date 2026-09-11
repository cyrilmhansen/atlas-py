import hashlib
import io
import json
import subprocess

import pytest

from tools.atlas_agent import cli
from tools.atlas_agent import workflow as workflow_module
from tools.atlas_agent.prompt import parse_prompt
from tools.atlas_agent.workflow import Workflow, WorkflowError, replay_journal


def git(path, *args):
    return subprocess.check_output(["git", *args], cwd=path, text=True).strip()


@pytest.fixture
def workflow(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\nallowed_untracked = []\n'
    )
    (root / "tracked").write_text("content\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "initial")
    result = Workflow(root)
    result.init()
    return result


def test_prompt_create_derives_metadata_and_preserves_body(workflow):
    journal = workflow.journal.path.read_bytes()
    state = workflow._state_file().read_bytes()
    body = b"line one\n\nutf-8: \xc3\xa9\n"

    path, prompt = workflow.prompt_create(
        "pvc-a21b-validation", "implementation", body, network_access=True
    )

    assert path.name.startswith("g000001-pvc-a21b-validation-")
    assert prompt.generation == 1
    assert prompt.parent == "genesis"
    assert prompt.expected_head == git(workflow.root, "rev-parse", "HEAD")
    assert prompt.session_mode == "fresh"
    assert prompt.network_access is True
    assert prompt.body == body.decode("utf-8")
    assert parse_prompt(path.read_bytes()).raw == path.read_bytes()
    assert workflow.journal.path.read_bytes() == journal
    assert workflow._state_file().read_bytes() == state

    workflow.ingest()
    next_path, next_prompt = workflow.prompt_create(
        "second", "state_audit", b"body"
    )
    assert next_path.exists()
    assert next_prompt.generation == 2
    assert next_prompt.parent == 1
    assert next_prompt.network_access is False


def test_prompt_create_reuse_contract_and_validation(workflow):
    _, prompt = workflow.prompt_create(
        "reuse", "patch_review", b"body",
        session_mode="reuse", reuse_execution_id="execution-1"
    )
    assert prompt.reuse_execution_id == "execution-1"

    with pytest.raises(WorkflowError, match="REUSE_TARGET_MISSING"):
        workflow.prompt_create("missing", "implementation", b"", session_mode="reuse")
    with pytest.raises(WorkflowError, match="REUSE_TARGET_FORBIDDEN"):
        workflow.prompt_create(
            "fresh-id", "implementation", b"", reuse_execution_id="execution-1"
        )
    with pytest.raises(WorkflowError, match="UNKNOWN_ACTION"):
        workflow.prompt_create("bad-action", "not-an-action", b"")
    with pytest.raises(WorkflowError, match="MISSING_FIELD"):
        workflow.prompt_create("../outside", "implementation", b"")


def test_prompt_create_never_overwrites_existing_inbox_file(workflow):
    head = git(workflow.root, "rev-parse", "HEAD")
    raw = (
        '+++\nschema = "atlas-agent-prompt/2"\ngeneration = 1\n'
        'parent = "genesis"\ncheckpoint = "collision"\n'
        'action = "implementation"\nexpected_head = "' + head + '"\n'
        'session_mode = "fresh"\nnetwork_access = false\n+++\nbody'
    ).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = workflow.base / "inbox" / f"g000001-collision-{digest}.txt"
    path.write_bytes(b"do not replace")
    original = path.read_bytes()
    with pytest.raises(WorkflowError, match="INBOX_FILE_EXISTS"):
        workflow.prompt_create("collision", "implementation", b"body")
    assert path.read_bytes() == original


def test_prompt_create_publishes_only_after_complete_staging(workflow, monkeypatch):
    seen = {}
    original_link = workflow_module.os.link

    def link(staged, final):
        seen["final_existed"] = final.exists()
        seen["staged_bytes"] = staged.read_bytes()
        return original_link(staged, final)

    monkeypatch.setattr(workflow_module.os, "link", link)
    path, prompt = workflow.prompt_create("atomic", "implementation", b"body")

    assert seen["final_existed"] is False
    assert seen["staged_bytes"] == path.read_bytes()
    assert parse_prompt(path.read_bytes()).sha256 == prompt.sha256
    assert not list(path.parent.glob(".prompt-create-*"))


def test_prompt_create_staging_failure_leaves_no_final_prompt(workflow, monkeypatch):
    original_fsync = workflow_module.os.fsync

    def fail_fsync(fd):
        raise OSError("injected staging failure")

    monkeypatch.setattr(workflow_module.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="injected staging failure"):
        workflow.prompt_create("staging-failure", "implementation", b"body")

    assert not list((workflow.base / "inbox").glob("g*.txt"))
    assert not list((workflow.base / "inbox").glob(".prompt-create-*"))
    monkeypatch.setattr(workflow_module.os, "fsync", original_fsync)


@pytest.mark.parametrize("interrupt_after_publication", [False, True])
def test_prompt_create_keyboard_interrupt_cleans_staging(
    workflow, monkeypatch, interrupt_after_publication
):
    captured = {}
    original_link = workflow_module.os.link

    def interrupt_boundary(*args):
        if not interrupt_after_publication:
            raise KeyboardInterrupt
        return workflow._revalidate_prompt_create_boundary(*args)

    if not interrupt_after_publication:
        monkeypatch.setattr(
            workflow, "_revalidate_prompt_create_boundary", interrupt_boundary
        )
    else:
        def capture_link(staged, final):
            captured["staged"] = staged
            return original_link(staged, final)

        monkeypatch.setattr(workflow_module.os, "link", capture_link)
        monkeypatch.setattr(
            workflow_module, "fsync_dir",
            lambda directory: (_ for _ in ()).throw(KeyboardInterrupt()),
        )

    with pytest.raises(KeyboardInterrupt):
        workflow.prompt_create("interrupted", "implementation", b"body")

    assert not list((workflow.base / "inbox").glob(".prompt-create-*"))
    prompts = list((workflow.base / "inbox").glob("g*.txt"))
    if interrupt_after_publication:
        assert len(prompts) == 1
        assert not captured["staged"].exists()
        final_bytes = prompts[0].read_bytes()
        assert final_bytes.endswith(b"body")
        # Reusing the removed staging pathname cannot mutate the published
        # inode (it is no longer a hard-link alias).
        captured["staged"].write_bytes(b"abandoned replacement")
        assert prompts[0].read_bytes() == final_bytes
    else:
        assert prompts == []


def test_prompt_create_rejects_repository_change_at_publication_boundary(
    workflow, monkeypatch
):
    original = workflow._revalidate_prompt_create_boundary

    def mutate_then_revalidate(*args):
        (workflow.root / "tracked").write_text("changed\n")
        return original(*args)

    monkeypatch.setattr(
        workflow, "_revalidate_prompt_create_boundary", mutate_then_revalidate
    )
    with pytest.raises(WorkflowError, match="REPOSITORY_WITNESS_MISMATCH_BOUNDARY"):
        workflow.prompt_create("changed", "implementation", b"body")
    assert not list((workflow.base / "inbox").glob("g*.txt"))


def test_prompt_create_rejects_workflow_state_change_at_publication_boundary(
    workflow, monkeypatch
):
    original = workflow._revalidate_prompt_create_boundary

    def mutate_then_revalidate(*args):
        workflow.journal.append(
            "PROMPT_RECEIVED",
            prompt_sha256="0" * 64,
            source="boundary-test.txt",
        )
        workflow._save(replay_journal(workflow.journal.read()))
        return original(*args)

    monkeypatch.setattr(
        workflow, "_revalidate_prompt_create_boundary", mutate_then_revalidate
    )
    with pytest.raises(WorkflowError, match="WORKFLOW_BOUNDARY_CHANGED"):
        workflow.prompt_create("state-changed", "implementation", b"body")
    assert not list((workflow.base / "inbox").glob("g*.txt"))


def test_prompt_create_cli_reads_body_from_binary_stdin(workflow, monkeypatch, capsys):
    class BinaryStdin:
        def __init__(self, data):
            self.buffer = io.BytesIO(data)

    monkeypatch.chdir(workflow.root)
    body = "stdin body: café\n".encode("utf-8")
    monkeypatch.setattr(cli.sys, "stdin", BinaryStdin(body))

    assert (
        cli.main(
            ["prompt-create", "--checkpoint", "cli", "--action", "implementation"]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "g1 · prompt created" in output
    path = next((workflow.base / "inbox").glob("g*.txt"))
    parsed = parse_prompt(path.read_bytes())
    assert parsed.body == body.decode("utf-8")
