"""Large execution input and bounded lifecycle provenance are separate contracts."""
import copy
import hashlib

import pytest

from test_agent_parent_artifact_contract import _rehash
from test_agent_semantic_pvc import semantic_bytes
from test_agent_workflow_w221 import accepted, make_repo
from tools.atlas_agent.codex_executor import CodexExecutor
from tools.atlas_agent.executor import ExecutionResult, PreparedExecution, utc_now
from tools.atlas_agent.journal import JournalError, canonical
from tools.atlas_agent.pvc_context import _stage_pvc_context
from tools.atlas_agent.semantic import build_semantic_tablet
from tools.atlas_agent.workflow import WorkflowError


class Capture(CodexExecutor):
    supports_authoritative_pvc_context = True

    def __init__(self):
        super().__init__(executable='/bin/true')

    def prepare_execution(self, spec):
        return PreparedExecution(spec, 'capture', ('capture',), 'capture/1',
                                 self._envelope(), spec.policy_snapshot)

    def run_execution(self, prepared):
        self.input = prepared.spec.prompt_bytes
        assert prepared.spec.prompt_path.read_bytes() == self.input
        now = utc_now()
        return ExecutionResult(str(prepared.spec.execution_id), 'capture',
            list(prepared.command), 'capture/1', now, now, 0,
            'reports/x/stdout.log', 'reports/x/stderr.log', None, 'success',
            'reports/x/result.json', prepared.permission_envelope,
            execution_input_sha256=hashlib.sha256(self.input).hexdigest())


def setup(tmp_path, size=8232):
    _, w = make_repo(tmp_path, policy=False)
    prompt = accepted(w, schema=1)
    marker = 'UNIQUE-LARGE-PVC-CONTEXT-☃'
    selection = build_semantic_tablet(semantic_bytes(
        result={'kind': 'hover', 'value': marker + 'x' * size})).pvc_context('q')
    staged = _stage_pvc_context(selection)
    try:
        derived = staged.framing.encode('utf-8')
    finally:
        staged.cleanup()
    return w, prompt, selection, derived, marker


def run(tmp_path, size=8232):
    w, prompt, selection, derived, marker = setup(tmp_path, size)
    executor = Capture()
    w.execute(1, executor, pvc_context=selection)
    return w, prompt, derived, marker, executor


def starts(w):
    return [e for e in w.journal.read() if e['event'] == 'RUN_STARTED' or
            (e['event'] == 'TRANSITION_PREPARED' and
             e['payload']['logical_event'] == 'RUN_STARTED')]


def test_large_exact_input_bounded_journal_and_recovery(tmp_path):
    sizes = []
    for size in (8232, 100000):
        w, prompt, derived, marker, executor = run(tmp_path / str(size), size)
        rows = starts(w)
        payload = rows[-1]['payload']
        parent = payload['context_supplement'].encode()
        assert len(derived) > size
        assert executor.input == prompt + derived + parent
        assert executor.input.count(derived) == 1
        execution = payload['execution']
        assert execution['execution_input_sha256'] == hashlib.sha256(executor.input).hexdigest()
        assert execution['effective_prompt_sha256'] == execution['execution_input_sha256']
        for row in rows:
            assert marker not in canonical(row)
            assert 'derived_context_supplement' not in row['payload']
            assert len(canonical(row).encode()) < 6000
        sizes.append([len(canonical(row).encode()) for row in rows])
        assert (w.base / payload['derived_context']['path']).read_bytes() == derived
        for key in ('context_path', 'effective_prompt_path'):
            (w.base / execution[key]).unlink()
        w._recover_context_artifacts(w._state())
        assert (w.base / execution['context_path']).read_bytes() == derived + parent
        assert (w.base / execution['effective_prompt_path']).read_bytes() == executor.input
        w._replayed()
    assert all(abs(a-b) < 20 for a, b in zip(*sizes))


@pytest.mark.parametrize('field,value', [
    ('sha256', '0'*64), ('byte_length', 1), ('path', 'derived-contexts/wrong.txt'),
    ('execution_id', 'different'), ('prompt_sha256', '0'*64),
    ('context_sha256', '0'*64), ('schema', 'atlas-derived-context/2'),
])
def test_rehashed_descriptor_tamper_rejected(tmp_path, field, value):
    w, *_ = run(tmp_path)
    def mutate(rows):
        for row in rows:
            if 'derived_context' in row['payload']:
                row['payload']['derived_context'][field] = value
    _rehash(w.journal.path, mutate)
    with pytest.raises(JournalError):
        w.journal.read()


def test_archive_tamper_and_missing_fail_closed(tmp_path):
    w, *_ = run(tmp_path)
    payload = starts(w)[-1]['payload']
    archive = w.base / payload['derived_context']['path']
    original = archive.read_bytes()
    archive.write_bytes(b'z' + original[1:])
    with pytest.raises(JournalError, match='archive mismatch'):
        w.journal.read()
    archive.unlink()
    with pytest.raises(JournalError, match='archive unavailable'):
        w._recover_context_artifacts(w._state())


def test_invalid_append_is_byte_identical_and_sequence_not_consumed(tmp_path):
    w, *_ = run(tmp_path)
    before = w.journal.path.read_bytes()
    count = len(w.journal.read())
    payload = copy.deepcopy(starts(w)[0]['payload'])
    payload.pop('derived_context')
    payload['derived_context_supplement'] = 'x' * 8232
    with pytest.raises(JournalError, match='derived context supplement invalid'):
        w.journal.append('TRANSITION_PREPARED', **payload)
    assert w.journal.path.read_bytes() == before
    with pytest.raises(JournalError):
        w.journal.append('RECOVERY_PERFORMED', bogus=True)
    assert w.journal.path.read_bytes() == before
    assert w.journal.append('RECOVERY_PERFORMED', repaired=[])['seq'] == count + 1
    assert len(w.journal.read()) == count + 1


@pytest.mark.parametrize('failure', ['publication', 'provenance', 'append'])
def test_failure_before_start_leaves_accepted_and_no_archive(tmp_path, monkeypatch, failure):
    w, prompt, selection, *_ = setup(tmp_path)
    before = w.journal.path.read_bytes()
    if failure == 'publication':
        original = w._publish_missing_execution_file
        def fail(path, data):
            original(path, data)
            raise OSError('injected after publication')
        monkeypatch.setattr(w, '_publish_missing_execution_file', fail)
    elif failure == 'provenance':
        def fail(*args):
            raise WorkflowError('injected provenance')
        monkeypatch.setattr(w, '_validate_authoritative_provenance', fail)
    else:
        original = w.journal.append
        def fail(event, **fields):
            if event == 'TRANSITION_PREPARED':
                fields['derived_context']['byte_length'] += 1
            return original(event, **fields)
        monkeypatch.setattr(w.journal, 'append', fail)
    with pytest.raises((WorkflowError, JournalError, OSError)):
        w.execute(1, Capture(), pvc_context=selection)
    assert w.journal.path.read_bytes() == before
    assert w._state()['generations']['1']['status'] == 'ACCEPTED'
    assert next((w.base / 'accepted').glob('*.txt')).read_bytes() == prompt
    assert not list((w.base / 'derived-contexts').glob('*.txt'))
    w.journal.read()


def test_legacy_replay_recovery_and_mixed_form_rejection(tmp_path):
    w, _, derived, _, executor = run(tmp_path, 1)
    assert len(derived) < 4096
    def legacy(rows):
        for row in rows:
            if 'derived_context' in row['payload']:
                row['payload'].pop('derived_context')
                row['payload']['derived_context_supplement'] = derived.decode()
    _rehash(w.journal.path, legacy)
    w.journal.read()
    w._replayed()
    execution = starts(w)[-1]['payload']['execution']
    (w.base / execution['context_path']).unlink()
    (w.base / execution['effective_prompt_path']).unlink()
    w._recover_context_artifacts(w._state())
    assert (w.base / execution['effective_prompt_path']).read_bytes() == executor.input
    def mixed(rows):
        for row in rows:
            if 'derived_context_supplement' in row['payload']:
                row['payload']['derived_context'] = {}
    _rehash(w.journal.path, mixed)
    with pytest.raises(JournalError, match='mixed'):
        w.journal.read()


def test_prepared_transaction_retains_archive_for_exact_recovery(tmp_path, monkeypatch):
    w, prompt, selection, derived, _ = setup(tmp_path)
    def fail(*args):
        raise OSError('owner publication failed after durable prepare')
    with monkeypatch.context() as patch:
        patch.setattr(w, '_prepare_execution_publication', fail)
        with pytest.raises(OSError):
            w.execute(1, Capture(), pvc_context=selection)
    prepared = starts(w)[0]['payload']
    assert (w.base / prepared['derived_context']['path']).read_bytes() == derived
    w.recover()
    execution = prepared['execution']
    context = derived + prepared['context_supplement'].encode()
    assert (w.base / execution['context_path']).read_bytes() == context
    assert (w.base / execution['effective_prompt_path']).read_bytes() == prompt + context
    w.journal.read()


def test_context_cross_binding_cannot_claim_parent_only(tmp_path):
    w, *_ = run(tmp_path)
    def mutate(rows):
        for row in rows:
            p = row['payload']
            if 'derived_context' in p:
                digest = hashlib.sha256(p['context_supplement'].encode()).hexdigest()
                p['derived_context']['context_sha256'] = digest
                p['execution']['context_sha256'] = digest
    _rehash(w.journal.path, mutate)
    with pytest.raises(JournalError, match='derived context provenance'):
        w.journal.read()


@pytest.mark.parametrize('alias', ['file', 'directory', 'fifo'])
def test_secure_archive_rejects_matching_aliases_and_fifo(tmp_path, monkeypatch, alias):
    import os
    from pathlib import Path
    w, _, derived, *_ = run(tmp_path)
    payload = starts(w)[-1]['payload']
    archive = w.base / payload['derived_context']['path']
    if alias == 'directory':
        external = tmp_path / 'external-directory'
        archive.parent.rename(external)
        archive.parent.symlink_to(external, target_is_directory=True)
        assert archive.read_bytes() == derived
    else:
        archive.unlink()
        if alias == 'file':
            external = tmp_path / 'external.txt'
            external.write_bytes(derived)
            archive.symlink_to(external)
            assert archive.read_bytes() == derived
        else:
            os.mkfifo(archive)
    # No payload-consumption operation is permitted for these objects. In
    # particular fdopen must not be reached for a nonblocking-opened FIFO.
    def forbidden(*args, **kwargs):
        pytest.fail('alias/non-regular object reached payload consumption')
    monkeypatch.setattr(os, 'fdopen', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    with pytest.raises(JournalError, match='archive unavailable'):
        w.journal.derived_context_bytes(payload)


def test_archive_hash_and_return_use_one_secure_descriptor(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    from tools.atlas_agent import journal
    w, _, derived, *_ = run(tmp_path)
    payload = starts(w)[-1]['payload']
    archive = w.base / payload['derived_context']['path']
    opened = []
    hashed = []
    original_open, original_hash = os.open, hashlib.sha256
    def tracked_open(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        opened.append((path, flags, kwargs.get('dir_fd'), fd))
        return fd
    def tracked_hash(data):
        hashed.append(data)
        return original_hash(data)
    def no_path_read(*args):
        pytest.fail('archive pathname reopened for payload')
    monkeypatch.setattr(os, 'open', tracked_open)
    monkeypatch.setattr(Path, 'read_bytes', no_path_read)
    monkeypatch.setattr(journal.hashlib, 'sha256', tracked_hash)
    result = w.journal.derived_context_bytes(payload)
    assert result == derived
    assert hashed == [result] and hashed[0] is result
    assert len(opened) == 2
    directory, final = opened
    assert directory[0] == archive.parent
    assert directory[1] & os.O_DIRECTORY and directory[1] & os.O_NOFOLLOW
    assert final[0] == archive.name and final[2] == directory[3]
    assert final[1] & os.O_NOFOLLOW and final[1] & os.O_NONBLOCK


def test_archive_detects_name_replacement_after_open(tmp_path, monkeypatch):
    import os
    w, _, derived, *_ = run(tmp_path)
    payload = starts(w)[-1]['payload']
    archive = w.base / payload['derived_context']['path']
    original_open = os.open
    def replace_after_open(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if path == archive.name:
            archive.unlink()
            archive.write_bytes(derived)
        return fd
    monkeypatch.setattr(os, 'open', replace_after_open)
    with pytest.raises(JournalError, match='identity changed'):
        w.journal.derived_context_bytes(payload)


@pytest.mark.parametrize('existing', ['matching', 'symlink', 'fifo', 'conflicting'])
def test_publication_race_securely_validates_and_syncs_accepted_inode(
        tmp_path, monkeypatch, existing):
    import os
    import stat
    from pathlib import Path
    _, w = make_repo(tmp_path)
    directory = w.base / 'derived-contexts'
    directory.mkdir()
    data = b'exact authoritative bytes\n'
    path = directory / ('owner-' + hashlib.sha256(data).hexdigest() + '.txt')
    original_open, original_fsync = os.open, os.fsync
    synced, opened, order = [], [], []
    def sync(fd):
        st = os.fstat(fd)
        identity = (st.st_dev, st.st_ino)
        synced.append(identity)
        order.append(('sync', identity, stat.S_ISDIR(st.st_mode)))
        original_fsync(fd)
    def secure_open(name, flags, *args, **kwargs):
        fd = original_open(name, flags, *args, **kwargs)
        if name == path.name:
            st = os.fstat(fd)
            opened.append((fd, flags, kwargs.get('dir_fd'), (st.st_dev, st.st_ino)))
            order.append(('open-existing', opened[-1][-1], False))
        return fd
    def lose_race(source, destination, **kwargs):
        # The private candidate has crossed its fsync boundary before this
        # concurrent canonical object exists at all.
        st = source.stat()
        assert (st.st_dev, st.st_ino) in synced
        assert source.read_bytes() == data
        assert destination in (path, path.name)
        if destination == path.name:
            assert kwargs['dst_dir_fd'] is not None
        if existing == 'symlink':
            target = tmp_path / 'matching-external.txt'
            target.write_bytes(data)
            path.symlink_to(target)
        elif existing == 'fifo':
            os.mkfifo(path)
        else:
            path.write_bytes(data if existing == 'matching' else b'conflict')
        order.append(('race', None, False))
        raise FileExistsError('injected publication race')
    monkeypatch.setattr(os, 'open', secure_open)
    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'link', lose_race)
    if existing == 'matching':
        w._publish_missing_execution_file(path, data)
        st = path.stat()
        identity = (st.st_dev, st.st_ino)
        assert len(opened) == 1
        fd, flags, dir_fd, opened_identity = opened[0]
        assert opened_identity == identity
        assert flags & os.O_NOFOLLOW and dir_fd is not None
        assert order[-3:] == [('open-existing', identity, False),
                              ('sync', identity, False),
                              ('sync', (directory.stat().st_dev,
                                        directory.stat().st_ino), True)]
        assert path.read_bytes() == data
    else:
        # FIFO opens are nonblocking; fstat rejects before fdopen/read.
        # Guard the old Path.read_bytes implementation too, so this regression
        # fails rather than hanging when run against the pre-repair code.
        original_read_bytes = Path.read_bytes
        def no_fifo_read(candidate):
            assert not stat.S_ISFIFO(candidate.stat().st_mode)
            return original_read_bytes(candidate)
        monkeypatch.setattr(Path, 'read_bytes', no_fifo_read)
        original_fdopen = os.fdopen
        def regular_only(fd, *args, **kwargs):
            assert stat.S_ISREG(os.fstat(fd).st_mode)
            return original_fdopen(fd, *args, **kwargs)
        monkeypatch.setattr(os, 'fdopen', regular_only)
        with pytest.raises(WorkflowError, match='RECOVERY_FALLBACK_ARTIFACT_CONFLICT'):
            w._publish_missing_execution_file(path, data)
        if existing == 'conflicting':
            assert path.read_bytes() == b'conflict'
        elif existing == 'symlink':
            assert path.is_symlink()
        else:
            assert stat.S_ISFIFO(path.lstat().st_mode)
    assert not list(w.base.glob('recovery-artifact-*'))


def test_publication_rejects_archive_directory_alias(tmp_path):
    _, w = make_repo(tmp_path)
    external = tmp_path / 'external-directory'
    external.mkdir()
    (w.base / 'derived-contexts').symlink_to(external, target_is_directory=True)
    path = w.base / 'derived-contexts' / 'candidate.txt'
    with pytest.raises(WorkflowError, match='RECOVERY_FALLBACK_ARTIFACT_CONFLICT'):
        w._publish_missing_execution_file(path, b'payload')
    assert not list(external.iterdir())
    assert not list(w.base.glob('recovery-artifact-*'))
