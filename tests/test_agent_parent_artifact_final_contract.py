import hashlib

import pytest

from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionSpec, ExecutorError
from tests.codex_test_support import pinned_codex


def _spec(tmp_path, **updates):
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes(b"pathname bytes")
    values = dict(
        generation=1, prompt_sha256="0" * 64, action="implementation",
        prompt_path=prompt, repository_root=tmp_path, execution_id="e",
        report_dir=tmp_path / "report",
    )
    values.update(updates)
    return ExecutionSpec(**values)


def test_unspecified_input_mode_fails_closed(tmp_path):
    with pytest.raises(ExecutorError, match="INVALID_EXECUTION_INPUT_MODE"):
        CodexExecutor(executable="/bin/sh").prepare_execution(_spec(tmp_path))


def test_modern_mode_binds_bytes_and_digest(tmp_path):
    data = b"effective bytes"
    executor,snapshot = pinned_codex(tmp_path,"/bin/true")
    prepared = executor.prepare_execution(
        _spec(
            tmp_path,
            input_mode="bytes-v1",
            prompt_bytes=data,
            expected_input_sha256=hashlib.sha256(data).hexdigest(),
            policy_snapshot=snapshot,
        )
    )
    assert prepared.spec.prompt_bytes == data
    assert prepared.spec.prompt_path.read_bytes() != data
