"""Integrated staging semantics at the existing PVC authority boundary."""
from dataclasses import replace

import pytest

from tools.atlas_agent.pvc_context import (
    PvcContextComposition, PvcContextError, PvcContextSelection,
    _stage_integrated_context, _stage_pvc_composition,
)
from tools.atlas_agent.review import build_review_package
from test_agent_workflow_w221 import make_repo


def review(tmp_path):
    repo, workflow = make_repo(tmp_path)
    import subprocess
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo).decode().strip()
    task = 'Preserve exact TASK.\r\né😀\n\n'
    package = build_review_package(repo, head, task, workflow.allowed)
    return task, package.pvc_context()


def test_order_exact_empty_and_stable_rendering(tmp_path):
    task, selection = review(tmp_path)
    # Reverse authorized tablet order: category order still wins.
    selection = replace(selection, tablet_ids=tuple(reversed(selection.tablet_ids)))
    composition = PvcContextComposition((selection,))
    first = _stage_integrated_context(composition, task)
    second = _stage_integrated_context(composition, task)
    try:
        assert first.framing == second.framing
        assert [c.category for c in first.contributions] == ['TASK', 'DIFF']
        assert first.text_authorities[0].payload == task.encode()
        assert first.text_authorities[1].payload == b''
        assert '## SOURCE (not selected)' in first.framing
        assert '## SEMANTIC (not selected)' in first.framing
        assert 'payload-bytes=0' in first.framing
        assert 'expectedHead' in first.framing
        assert 'Selection reason: patch review package' in first.framing
    finally:
        first.cleanup()
        second.cleanup()
        import shutil
        shutil.rmtree(selection.result.scratch_path)


def test_duplicate_mismatch_and_bound_fail_closed(tmp_path, monkeypatch):
    task, selection = review(tmp_path)
    try:
        with pytest.raises(PvcContextError, match='DUPLICATE_CONTRIBUTION'):
            _stage_integrated_context(PvcContextComposition((selection, selection)), task)
        with pytest.raises(PvcContextError, match='TASK_MISMATCH'):
            _stage_integrated_context(PvcContextComposition((selection,)), 'different task')
        monkeypatch.setattr('tools.atlas_agent.pvc_context.MAX_CONTEXT_BYTES', 1)
        with pytest.raises(PvcContextError, match='COMPOSITION_BOUNDED'):
            _stage_integrated_context(PvcContextComposition((selection,)), task)
    finally:
        import shutil
        shutil.rmtree(selection.result.scratch_path)


def test_missing_task_uses_authorized_body_and_legacy_renderer_unchanged(tmp_path):
    task, selection = review(tmp_path)
    diff_only = replace(selection, tablet_ids=(selection.tablet_ids[1],))
    composition = PvcContextComposition((diff_only,))
    legacy = _stage_pvc_composition(composition)
    current = _stage_integrated_context(composition, task)
    try:
        assert legacy.framing.startswith('PVC context composition is explicit controller ordering.')
        assert 'Atlas integrated context' not in legacy.framing
        assert current.contributions[0].origin == 'accepted prompt body'
        assert task in current.contributions[0].framing
    finally:
        legacy.cleanup()
        current.cleanup()
        import shutil
        shutil.rmtree(selection.result.scratch_path)


def test_atlas_prompt_parser_change_reaches_execution_and_replay(tmp_path):
    """Dogfood subject is Atlas's real parser; server is deterministic test authority.

    No PVC rasterizer is run: SOURCE is honestly not selected. TASK, exact
    parser patch and a witnessed Python definition result cross dispatch.
    """
    import hashlib
    import json
    from pathlib import Path
    from test_agent_context_plan import _server, write_plan, python_member
    from test_python_semantic_query import FAKE
    from test_agent_workflow_w221 import prompt
    from test_agent_derived_context_journal import Capture
    from tools.atlas_agent.context_plan import (
        parse_context_plan, build_context_composition, cleanup_context_composition,
    )
    original = (Path(__file__).parents[1] / 'tools/atlas_agent/prompt.py').read_bytes()
    # Install actual Atlas source in the fixture's authorized patch path.
    repo, workflow = make_repo(tmp_path, policy=False)
    (repo / 'corpus_miner').mkdir()
    (repo / 'corpus_miner/parser.py').write_text(original.decode().replace(
        'def parse_prompt(raw: bytes) -> Prompt:',
        'def parse_prompt(raw: bytes) -> Prompt:\n    # Preserve authorized task bytes.'))
    raw = prompt(workflow, schema=1)
    task = 'Review the task-byte preservation comment in Atlas parse_prompt; verify it changes no parsing behavior.\n'
    raw = raw.replace(b'W2.2.1\n', task.encode())
    (workflow.base / 'inbox' / 'g1.txt').write_bytes(raw)
    workflow.ingest()
    server = _server(tmp_path / 'pyright', FAKE.replace('a.py', 'corpus_miner/parser.py').replace(
        "{'line':0,'character':8 if mode=='utf8' else 5}",
        "{'line':10,'character':4}").replace("def rg(a=5, b=11):", "def rg(a=4, b=16):").replace("'line': 0", "'line': 10"))
    member = python_member(server, path='corpus_miner/parser.py')
    member['query'].update(kind='definition', line=10, character=4)
    plan = parse_context_plan(write_plan(tmp_path / 'plan.json', [member, {'kind': 'REVIEW'}],
                                         schema='atlas-agent-context-plan/2'))
    from atlas.semantic_query import repository_witness
    expected_witness = repository_witness(repo)
    composition = build_context_composition(workflow, plan)
    capture = Capture()
    try:
        workflow.dispatch(capture, pvc_context=composition)
        text = capture.input.decode()
        assert text.index('## TASK') < text.index('## DIFF') < text.index('## SEMANTIC')
        assert task in text
        assert '+    # Preserve authorized task bytes.' in text
        assert '+def parse_prompt(raw: bytes) -> Prompt:' in text
        assert '## SOURCE (not selected)' in text
        semantic = composition.selections[0]
        artifact = semantic.result.validated_snapshot.document['artifacts'][0]
        payload = (semantic.result.bundle_path / artifact['relativePath']).read_bytes()
        observation = json.loads(payload)
        assert observation['query']['path'] == 'corpus_miner/parser.py'
        assert observation['query']['kind'] == 'definition'
        assert payload in capture.input
        assert observation['repositoryWitness'] == expected_witness
        assert observation['result']['value'][0]['start'] == {'line': 10, 'character': 4}
        execution = workflow._state()['generations']['1']['execution']
        assert (workflow.base / execution['effective_prompt_path']).read_bytes() == capture.input
        assert execution['effective_prompt_sha256'] == hashlib.sha256(capture.input).hexdigest()
        # Replay/recovery consumes archived input, never reruns semantic services.
        server.unlink()
        from tools.atlas_agent.workflow import replay_journal
        replayed = replay_journal(workflow.journal.read())
        assert replayed['generations']['1']['execution'] == execution
        (workflow.base / execution['effective_prompt_path']).unlink()
        workflow._recover_context_artifacts(replayed)
        assert (workflow.base / execution['effective_prompt_path']).read_bytes() == capture.input
        assert execution['effective_prompt_sha256'] == hashlib.sha256(capture.input).hexdigest()
    finally:
        cleanup_context_composition(composition)


def test_four_categories_stable_attachment_order_and_no_payload_rewrite(tmp_path):
    import os
    import shutil
    from test_agent_pvc_composition import _members
    review, source, semantic, payload = _members(tmp_path)
    first = _stage_integrated_context(
        PvcContextComposition((semantic, source, review)), 'TASK')
    second = _stage_integrated_context(
        PvcContextComposition((review, source, semantic)), 'TASK')
    try:
        assert first.framing == second.framing
        assert [c.category for c in first.contributions] == ['TASK', 'DIFF', 'SOURCE', 'SEMANTIC']
        assert first.text_authorities[-1].payload == payload
        assert first.image_authorities[0].ordinal == 2
        assert os.pread(first.image_authorities[0].fd, 100, 0) == b'PNG fixture'
        assert source.purpose in first.contributions[2].framing
        assert semantic.result.validated_snapshot.document['snapshotId'] in first.contributions[3].framing
    finally:
        first.cleanup()
        second.cleanup()
        for member in (review, source, semantic):
            shutil.rmtree(member.result.scratch_path)


def test_within_category_order_and_unavailable_not_empty(tmp_path):
    import shutil
    from test_agent_semantic_pvc import semantic_bytes
    from tools.atlas_agent.semantic import build_semantic_tablet
    a = build_semantic_tablet(semantic_bytes(result={'kind': 'hover', 'value': 'first'})).pvc_context('first query')
    b = build_semantic_tablet(semantic_bytes(result={'kind': 'hover', 'value': 'second'})).pvc_context('second query')
    staged = _stage_integrated_context(PvcContextComposition((b, a)), 'task')
    try:
        assert [c.purpose for c in staged.contributions] == ['exact authorized task', 'second query', 'first query']
        staged.cleanup()
        artifact = a.result.validated_snapshot.document['artifacts'][0]
        (a.result.bundle_path / artifact['relativePath']).unlink()
        with pytest.raises(PvcContextError, match='ARTIFACT_UNREADABLE'):
            _stage_integrated_context(PvcContextComposition((b, a)), 'task')
    finally:
        staged.cleanup()
        shutil.rmtree(a.result.scratch_path)
        shutil.rmtree(b.result.scratch_path)


def test_history_cli_exposes_existing_context_artifacts(tmp_path, monkeypatch, capsys):
    from tools.atlas_agent import cli
    _, workflow = make_repo(tmp_path)
    monkeypatch.setattr(cli, 'Workflow', lambda: workflow)
    monkeypatch.setattr(workflow, 'history', lambda: [{
        'generation': 1, 'action': 'implementation', 'status': 'COMPLETED',
        'report_available': True, 'context_path': 'reports/contexts/example.txt',
        'effective_prompt_path': 'reports/contexts/example-effective.txt',
        'effective_prompt_sha256': 'a' * 64,
    }])
    assert cli.main(['history']) == 0
    output = capsys.readouterr().out
    assert 'context: reports/contexts/example.txt' in output
    assert 'effective input: reports/contexts/example-effective.txt sha256=' + 'a' * 64 in output
