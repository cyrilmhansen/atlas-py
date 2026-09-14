import hashlib
import subprocess

import pytest

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import (
    ExecutionResult, PreparedExecution, utc_now,
)
from tools.atlas_agent.review import ReviewPackageError, build_review_package
from tools.atlas_agent.pvc_context import _stage_pvc_context
from tools.atlas_agent.workflow import Workflow


def git(path, *args):
    return subprocess.check_output(["git", *args], cwd=path).decode().strip()


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "tracked.txt").write_text("one\n")
    (tmp_path / "context.txt").write_text(
        "line1\nline2\nline3\nOLD\nline5\nline6\nline7\n"
    )
    (tmp_path / "removed.txt").write_text("gone\n")
    (tmp_path / "rename.txt").write_text("rename\n")
    (tmp_path / "binary.bin").write_bytes(b"\x00old\xff\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


def package(repo, task="inspect"):
    root, head = repo
    return build_review_package(root, head, task,
                                ["tracked.txt", "removed.txt", "rename.txt",
                                 "binary.bin", "context.txt", "added.txt",
                                 "new.txt", "renamed.txt"])


def test_real_git_clean_matrix_case(repo):
    root, _ = repo
    result = package(repo)
    assert result.diff.content == b""


def test_real_git_unstaged_and_staged_matrix_cases(repo):
    root, _ = repo
    (root / "tracked.txt").write_text("two\n")
    assert b"-one\n+two" in package(repo).diff.content

    subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
    (root / "tracked.txt").write_text("three\n")
    assert b"-one\n+three" in package(repo).diff.content


def test_real_git_isolated_staged_change_is_head_to_index(repo):
    root, _ = repo
    (root / "tracked.txt").write_text("two\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
    diff = package(repo).diff.content
    assert b"-one\n+two" in diff


def test_real_git_staged_and_unstaged_same_file_is_head_to_worktree(repo):
    root, _ = repo
    (root / "tracked.txt").write_text("two\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
    (root / "tracked.txt").write_text("three\n")
    diff = package(repo).diff.content
    assert b"-one\n+three" in diff
    assert b"-one\n+two" not in diff


def test_real_git_add_delete_rename_and_binary_matrix_cases(repo):
    root, _ = repo
    (root / "added.txt").write_text("added\n")
    subprocess.run(["git", "add", "added.txt"], cwd=root, check=True)
    diff = package(repo).diff.content
    assert b"new file mode" in diff and b"+added" in diff

    (root / "removed.txt").unlink()
    diff = package(repo).diff.content
    assert b"deleted file mode" in diff and b"-gone" in diff

    subprocess.run(["git", "mv", "rename.txt", "renamed.txt"],
                   cwd=root, check=True)
    diff = package(repo).diff.content
    assert b"similarity index 100%" in diff
    assert b"rename from rename.txt" in diff
    assert b"rename to renamed.txt" in diff

    (root / "binary.bin").write_bytes(b"\x00new\xfe\n")
    diff = package(repo).diff.content
    assert b"GIT binary patch" in diff
    assert b"-one" not in diff


def test_real_git_authorized_untracked_and_multiple_paths_have_coordinates(repo):
    root, _ = repo
    (root / "tracked.txt").write_text("one\nchanged\n")
    (root / "new.txt").write_text("new\n")
    diff = package(repo).diff.content
    assert b"+changed" in diff and b"+new" in diff
    assert diff.index(b"a/tracked.txt") < diff.index(b"a/new.txt")
    assert b"@@ -1 +1,2 @@" in diff


def test_multiple_paths_are_stable_and_hunks_are_preserved(repo):
    root, _ = repo
    (root / "tracked.txt").write_text("one\nchanged\n")
    (root / "new.txt").write_text("new\n")
    first = package(repo)
    second = package(repo)
    assert first.bytes == second.bytes
    assert first.digests == second.digests
    assert first.diff.content.index(b"a/tracked.txt") < first.diff.content.index(
        b"a/new.txt")
    assert b"@@ -1 +1,2 @@" in first.diff.content


def test_digest_independence_and_fail_closed_boundaries(repo):
    root, head = repo
    first = package(repo, "one")
    changed_task = package(repo, "two")
    assert changed_task.task_digest != first.task_digest
    assert changed_task.diff_digest == first.diff_digest
    (root / "tracked.txt").write_text("patch\n")
    changed_diff = package(repo, "one")
    assert changed_diff.diff_digest != first.diff_digest
    with pytest.raises(ReviewPackageError, match="HEAD"):
        build_review_package(root, "0" * 40, "one", ["tracked.txt"])
    (root / "unauthorized.txt").write_text("no\n")
    with pytest.raises(ReviewPackageError, match="UNAUTHORIZED"):
        build_review_package(root, head, "one", ["tracked.txt"])


def test_tracked_paths_outside_authority_fail_closed(repo):
    root, head = repo
    (root / "removed.txt").write_text("leaked\n")
    with pytest.raises(ReviewPackageError, match="UNAUTHORIZED"):
        build_review_package(root, head, "one", ["tracked.txt"])


def test_ambient_git_configuration_cannot_change_package(repo, tmp_path,
                                                         monkeypatch):
    root, _ = repo
    (root / "tracked.txt").write_text("two\n")
    first = package(repo, "task")
    config = tmp_path.parent / "conflicting.gitconfig"
    config.write_text(
        "[diff]\n"
        "\tnoprefix = true\n"
        "\talgorithm = patience\n"
        "\tindentHeuristic = true\n"
        "\trenames = false\n"
        "[core]\n\tquotePath = false\n"
        "[color]\n\tui = always\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "diff.noprefix")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    second = package(repo, "task")
    assert second.bytes == first.bytes
    assert second.digests == first.digests
    assert second.witness == first.witness


def test_git_diff_opts_cannot_change_package(repo, monkeypatch):
    root, _ = repo
    # The unchanged lines make -U3 and ambient --unified=0 emit different
    # patch bytes.  Thus this public-boundary comparison would fail if
    # production stopped removing GIT_DIFF_OPTS before invoking Git.
    (root / "context.txt").write_text(
        "line1\nline2\nline3\nNEW\nline5\nline6\nline7\n"
    )
    first = package(repo, "task")
    monkeypatch.setenv("GIT_DIFF_OPTS", "--unified=0")
    second = package(repo, "task")
    assert second.diff.content == first.diff.content
    assert second.diff_digest == first.diff_digest
    assert b" line1\n line2\n line3\n-OLD\n+NEW\n line5" in first.diff.content


@pytest.mark.parametrize(
    ("allowed", "authorized"),
    [
        (["rename.txt", "renamed.txt"], True),
        (["renamed.txt"], False),
        (["rename.txt"], False),
    ],
)
def test_rename_authorization_covers_both_endpoints(repo, allowed, authorized):
    root, head = repo
    subprocess.run(["git", "mv", "rename.txt", "renamed.txt"],
                   cwd=root, check=True)
    if authorized:
        result = build_review_package(root, head, "rename", allowed)
        assert b"rename from rename.txt" in result.diff.content
        assert b"rename to renamed.txt" in result.diff.content
    else:
        with pytest.raises(ReviewPackageError, match="UNAUTHORIZED"):
            build_review_package(root, head, "rename", allowed)


def test_repository_witness_change_fails_closed(repo, monkeypatch):
    root, _ = repo
    import tools.atlas_agent.review as review
    original = review.witness(root, ["tracked.txt"], None)
    changed = dict(original, tracked_worktree_sha256="f" * 64)
    calls = iter((original, changed))
    monkeypatch.setattr(review, "witness", lambda *args: next(calls))
    with pytest.raises(ReviewPackageError, match="WITNESS_CHANGED"):
        build_review_package(root, original["head"], "one", ["tracked.txt"])


def test_review_package_uses_authoritative_pvc_context(repo):
    result = package(repo, "review task")
    selection = result.pvc_context()
    staged = _stage_pvc_context(selection)
    try:
        assert selection.tablet_ids == (
            f"review-task-{result.task_digest[:16]}",
            f"review-diff-{result.diff_digest[:16]}",
        )
        assert not staged.image_authorities
        assert len(staged.text_authorities) == 2
        assert staged.text_authorities[0].payload == result.task.content
        assert staged.text_authorities[1].payload == result.diff.content
        context = staged.framing.encode("utf-8")
        assert result.task.content in context
        assert result.diff.content in context
        assert "expectedHead" in staged.framing
        assert result.diff_digest in staged.framing
    finally:
        staged.cleanup()


def test_workflow_pvc_boundary_delivers_review_text_as_effective_context(
        tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "test")
    (root / "atlas-agent.toml").write_text(
        'schema = "atlas-agent-project/1"\n'
        'allowed_untracked = ["corpus_miner/"]\n'
    )
    (root / "tracked.txt").write_text("one\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    head = git(root, "rev-parse", "HEAD")
    (root / "tracked.txt").write_text("two\n")
    workflow = Workflow(root)
    workflow.init()
    prompt = (
        "+++\n"
        'schema = "atlas-agent-prompt/1"\n'
        "generation = 1\nparent = \"genesis\"\n"
        'checkpoint = "typed-pvc"\naction = "implementation"\n'
        f'expected_head = "{head}"\nsession_mode = "fresh"\n'
        "+++\nrun review\n"
    ).encode()
    (workflow.base / "inbox" / "prompt.txt").write_bytes(prompt)
    workflow.ingest()
    package_result = build_review_package(root, head, "caller task",
                                          ["tracked.txt"])
    selection = package_result.pvc_context()

    class Capture(CodexExecutor):
        supports_authoritative_pvc_context = True

        def __init__(self):
            super().__init__(executable="/bin/true")
            self.supplied = None
            self.argv = None

        def prepare_execution(self, spec):
            return PreparedExecution(
                spec, "capture", ("capture",), "capture/1", self._envelope(),
                spec.policy_snapshot,
            )

        def run_execution(self, prepared):
            self.supplied = prepared.spec.prompt_bytes
            self.argv = prepared.command
            spec = prepared.spec
            spec.report_dir.mkdir(parents=True, exist_ok=True)
            (spec.report_dir / "stdout.log").write_bytes(b"")
            (spec.report_dir / "stderr.log").write_bytes(b"")
            now = utc_now()
            return ExecutionResult(
                str(spec.execution_id), "capture", list(prepared.command),
                "capture/1", now, now, 0,
                str((spec.report_dir / "stdout.log").relative_to(root)),
                str((spec.report_dir / "stderr.log").relative_to(root)),
                None, "success",
                str((spec.report_dir / "result.json").relative_to(root)),
                prepared.permission_envelope, execution_input_sha256=__import__(
                    "hashlib").sha256(self.supplied).hexdigest(),
            )

    capture = Capture()
    workflow.execute(1, capture, pvc_context=selection)
    assert package_result.task.content in capture.supplied
    assert package_result.diff.content
    assert package_result.diff.content in capture.supplied
    assert "--image" not in capture.argv
    assert "--image-detail" not in capture.argv
    execution = workflow._state()["generations"]["1"]["execution"]
    assert execution["effective_prompt_sha256"] == hashlib.sha256(
        capture.supplied).hexdigest()
