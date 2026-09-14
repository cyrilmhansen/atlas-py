"""Hermetic protocol/coordinate qualification; no host Pyright dependency."""
import json
import os
from pathlib import Path
import sys
import time

import pytest

from atlas.python_semantic_query import (
    PyrightAuthority, PythonSemanticQuery, PythonSemanticQueryError,
    query_python_semantics, repository_witness,
)

FAKE = r'''
import json, os, sys, time
from pathlib import Path
assert sys.argv[1:] == ['--stdio']
mode = os.environ.get('PY_FAKE', '')
if os.environ.get('PY_FAKE_PID'): Path(os.environ['PY_FAKE_PID']).write_text(str(os.getpid()))
def send(v):
    b = json.dumps(v).encode()
    sys.stdout.buffer.write(b'Content-Length: '+str(len(b)).encode()+b'\r\n\r\n'+b)
    sys.stdout.buffer.flush()
def read():
    h = sys.stdin.buffer.readline()
    if not h: sys.exit()
    n = int(h.split(b':')[1]); assert sys.stdin.buffer.readline() == b'\r\n'
    return json.loads(sys.stdin.buffer.read(n))
def rg(a=5, b=11):
    if mode == 'utf8': a,b = 8,14
    if mode == 'surrogate': a=2
    if mode == 'range_oob': b=100
    if mode == 'reversed': a,b=b,a
    return {'start': {'line': 0, 'character': a}, 'end': {'line': 0, 'character': b}}
while True:
    m=read(); method=m.get('method'); ident=m.get('id')
    if method == 'initialize':
        assert m['params']['capabilities']['general']['positionEncodings'] == ['utf-8','utf-16']
        assert m['params']['rootUri'] == Path.cwd().as_uri()
        if mode == 'timeout': time.sleep(20)
        if mode in ('config','unsupported'):
            send({'jsonrpc':'2.0','id':90,'method': 'workspace/configuration' if mode=='config' else 'workspace/applyEdit', 'params':{'items':[{'section':'python'},{'section':'python.analysis'}]}})
            assert read() == {'jsonrpc':'2.0','id':90,'result':[{},{}]}
        if mode in ('badjson','nan','inf','overflow','duplicate','servererror','boolid','both','noid','baderror','wrongid','oversize','header'):
            raw = {'badjson':b'{', 'nan':b'{"jsonrpc":"2.0","id":1,"result":NaN}',
                   'inf':b'{"jsonrpc":"2.0","id":1,"result":Infinity}',
                   'overflow':b'{"jsonrpc":"2.0","id":1,"result":1e999}',
                   'duplicate':b'{"jsonrpc":"2.0","id":1,"id":1,"result":{}}',
                   'servererror':b'{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"private tool details"}}',
                   'boolid':b'{"jsonrpc":"2.0","id":true,"result":{}}',
                   'both':b'{"jsonrpc":"2.0","id":1,"result":{},"error":{}}',
                   'noid':b'{"jsonrpc":"2.0","result":{}}',
                   'baderror':b'{"jsonrpc":"2.0","id":1,"error":{"code":true,"message":"x"}}',
                   'wrongid':b'{"jsonrpc":"2.0","id":2,"result":{}}'}.get(mode,b'')
            if mode=='oversize': sys.stdout.buffer.write(b'Content-Length: 99999999\r\n\r\n')
            elif mode=='header': sys.stdout.buffer.write(b'x'*8193)
            else: sys.stdout.buffer.write(b'Content-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw)
            sys.stdout.buffer.flush(); time.sleep(20)
        caps = {} if mode=='default' else {'positionEncoding':'utf-8' if mode=='utf8' else 'utf-32' if mode=='encoding' else 'utf-16'}
        send({'jsonrpc':'2.0','id':ident,'result':{'capabilities':caps}})
        if mode=='blocked': time.sleep(20)
    elif method=='textDocument/didOpen':
        d=m['params']['textDocument']; uri=d['uri']
        assert d['languageId']=='python'
        assert d['text'].encode()==Path('a.py').read_bytes()
    elif method in ('textDocument/definition','textDocument/references','textDocument/hover'):
        assert m['params']['position']=={'line':0,'character':8 if mode=='utf8' else 5}
        if method.endswith('references'): assert m['params']['context']=={'includeDeclaration':True}
        location={'uri':uri,'range':rg()}
        if mode=='external': location['uri']='file:///outside.py'
        if mode=='nonfile': location['uri']='https://example.com/a.py'
        if mode=='symlink_result': location['uri']=(Path.cwd()/'alias.py').as_uri()
        if mode=='otherfile': location={'uri':(Path.cwd()/'b.py').as_uri(),'range':{'start':{'line':0,'character':3},'end':{'line':0,'character':4}}}
        if mode=='link': location={'targetUri':uri,'targetRange':rg(),'targetSelectionRange':rg()}
        value={'contents':{'kind':'markdown','value':'```python\ntarget: int\n```'},'range':rg()} if method.endswith('hover') else [location,location]
        if mode=='sort': value=[location,{'uri':uri,'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':1}}},location]
        if mode=='null': value=None
        if mode=='badhover': value={'contents':{'arbitrary':1}}
        if mode=='mutation': Path('a.py').write_text('changed')
        send({'jsonrpc':'2.0','method':'textDocument/publishDiagnostics','params':{'diagnostics':[]}})
        send({'jsonrpc':'2.0','id':ident,'result':value})
    elif method=='shutdown':
        if mode=='shutdown_mutation': Path('a.py').write_text('changed')
        send({'jsonrpc':'2.0','id':ident,'result':None})
    elif method=='exit': sys.exit()
'''

@pytest.fixture
def setup(tmp_path, monkeypatch):
    tool = tmp_path / 'server'
    tool.write_text('#!' + sys.executable + '\n' + FAKE)
    tool.chmod(0o755)
    root = tmp_path / 'repo'
    root.mkdir()
    (root / 'a.py').write_bytes('é😀 target = 1\r\nprint(target)\r\n'.encode())
    authority = PyrightAuthority(str(tool), 'fake 1')
    def run(kind='definition', mode='', **kwargs):
        monkeypatch.setenv('PY_FAKE', mode)
        return query_python_semantics(root, authority, PythonSemanticQuery(kind, 'a.py', 0, 8), **kwargs)
    return root, authority, run

@pytest.mark.parametrize('kind', ['definition','references','hover'])
@pytest.mark.parametrize('mode', ['', 'default', 'utf8', 'config'])
def test_coordinates_and_canonical(setup, kind, mode):
    root, authority, run = setup
    raw = run(kind, mode)
    assert raw == run(kind, mode)
    doc = json.loads(raw)
    assert raw == (json.dumps(doc, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',',':'))+'\n').encode()
    assert doc['schema']=='atlas-python-semantic/1'
    assert doc['query']['character']==8
    assert doc['repositoryWitness']==repository_witness(root)
    assert doc['positionEncoding']=='utf-8'
    value=doc['result']['value']
    rg=value['range'] if kind=='hover' else value[0]
    assert rg['start']=={'line':0,'character':8}
    assert rg['end']=={'line':0,'character':14}
    if kind!='hover': assert len(value)==1

@pytest.mark.parametrize('mode,code', [
    ('external','result_uri_outside_repository'),('nonfile','result_uri_outside_repository'),
    ('badjson','malformed_lsp'),('nan','malformed_lsp'),('inf','malformed_lsp'),
    ('overflow','malformed_lsp'),('duplicate','malformed_lsp'),('servererror','server_error'),
    ('boolid','malformed_lsp'),('both','malformed_lsp'),('noid','malformed_lsp'),
    ('baderror','malformed_lsp'),('wrongid','malformed_lsp'),('header','malformed_lsp'),
    ('oversize','response_too_large'),('encoding','unsupported_position_encoding'),
    ('unsupported','unsupported_server_request'),('mutation','witness_mismatch'),
    ('shutdown_mutation','witness_mismatch'),('surrogate','malformed_lsp'),
    ('range_oob','malformed_lsp'),('reversed','malformed_lsp'),('badhover','malformed_lsp'),
])
def test_failures(setup, mode, code):
    with pytest.raises(PythonSemanticQueryError) as e:
        setup[2]('hover' if mode=='badhover' else 'definition',mode)
    assert e.value.code==code

@pytest.mark.parametrize('mode', ['timeout','blocked'])
def test_deadline(setup, mode, monkeypatch):
    pid_file = setup[0].parent / 'pid'
    monkeypatch.setenv('PY_FAKE_PID', str(pid_file))
    if mode=='blocked':
        with (setup[0]/'a.py').open('ab') as f: f.write(b'x'*300000)
    start=time.monotonic()
    with pytest.raises(PythonSemanticQueryError) as e: setup[2](mode=mode,timeout=.2)
    assert e.value.code=='timeout'
    assert time.monotonic()-start<2
    with pytest.raises(ProcessLookupError): os.kill(int(pid_file.read_text()), 0)

@pytest.mark.parametrize('kind,path,line,char,code', [
    ('symbols','a.py',0,0,'invalid_query'),('hover','../a.py',0,0,'unauthorized_path'),
    ('hover','/a.py',0,0,'unauthorized_path'),('hover','a\\b.py',0,0,'invalid_query'),
    ('hover','a.py',True,0,'invalid_query'),('hover','a.py',0,True,'invalid_query'),
    ('hover','a.py',-1,0,'invalid_query'),('hover','a.py',0,-1,'invalid_query'),
    ('hover','a.py',0,1,'invalid_query'),('hover','a.py',0,3,'invalid_query'),
    ('hover','a.py',99,0,'invalid_query'),('hover','a.py',0,99,'invalid_query'),
    ('hover','missing.py',0,0,'missing_file'),('hover','.',0,0,'invalid_query'),
])
def test_invalid_queries(setup, kind,path,line,char,code):
    with pytest.raises(PythonSemanticQueryError) as e:
        query_python_semantics(setup[0],setup[1],PythonSemanticQuery(kind,path,line,char))
    assert e.value.code==code

@pytest.mark.parametrize('version', ['', ' ', None, True])
def test_version_required(setup, version):
    with pytest.raises(PythonSemanticQueryError) as e: PyrightAuthority(setup[1].executable,version)
    assert e.value.code=='tool_identity_unavailable'

@pytest.mark.parametrize('path',['pyright-langserver','/nonexistent-pyright','/tmp'])
def test_explicit_executable(path):
    with pytest.raises(PythonSemanticQueryError) as e: PyrightAuthority(path,'1')
    assert e.value.code=='tool_identity_unavailable'


def test_witness_and_utf8(setup):
    with pytest.raises(PythonSemanticQueryError) as e: setup[2](witness='0'*64)
    assert e.value.code=='witness_mismatch'
    (setup[0]/'a.py').write_bytes(b'\xff')
    with pytest.raises(PythonSemanticQueryError) as e: setup[2]()
    assert e.value.code=='invalid_query'

@pytest.mark.parametrize('result', [False,True])
def test_symlink_escape(setup, result):
    root,a,run=setup
    (root/'alias.py').symlink_to(root.parent/'server')
    with pytest.raises(PythonSemanticQueryError) as e:
        if result: run(mode='symlink_result')
        else: query_python_semantics(root,a,PythonSemanticQuery('hover','alias.py',0,0))
    assert e.value.code==('result_uri_outside_repository' if result else 'unauthorized_path')


def test_other_file_conversion(setup):
    (setup[0]/'b.py').write_text('😀éx\n')
    value=json.loads(setup[2](mode='otherfile'))['result']['value'][0]
    assert value=={'path':'b.py','start':{'line':0,'character':6},'end':{'line':0,'character':7}}


def test_sort_link_and_absence(setup):
    run=setup[2]
    assert json.loads(run(mode='link'))['result']['value']==json.loads(run())['result']['value']
    values=json.loads(run('references','sort'))['result']['value']
    assert [v['start']['character'] for v in values]==[0,8]
    assert json.loads(run(mode='null'))['result']['value']==[]
    assert json.loads(run('hover','null'))['result']['value']=={'contents':None,'range':None}
