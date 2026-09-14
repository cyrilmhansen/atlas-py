import json
import os
import stat
import sys

import pytest

from atlas.semantic_query import (RustAnalyzerAuthority, SemanticQuery,
                                  SemanticQueryError, query_rust_semantics,
                                  repository_witness)


FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
def read():
 h=b""
 while b"\r\n\r\n" not in h:
  x=sys.stdin.buffer.read(1)
  if not x: return None
  h+=x
 n=int([x.split(":",1)[1] for x in h[:-4].decode().split("\r\n")
        if x.lower().startswith("content-length")][0])
 return json.loads(sys.stdin.buffer.read(n))
def send(x):
 b=json.dumps(x).encode(); sys.stdout.buffer.write(
  b"Content-Length: "+str(len(b)).encode()+b"\r\n\r\n"+b); sys.stdout.buffer.flush()
while True:
 x=read()
 if x is None: break
 if "id" not in x:
  if x.get("method")=="exit": break
  continue
 m=x["method"]; i=x["id"]
 if m=="initialize":
  enc = "utf-16" if os.environ.get("FAKE_MODE")=="wrong_encoding" else "utf-8"
  if os.environ.get("FAKE_MODE")=="boolean_id":
   send({"jsonrpc":"2.0","id":True,"result":{"capabilities":{"positionEncoding":enc}}})
  elif os.environ.get("FAKE_MODE") in ("nan", "infinity", "negative_infinity"):
   token = {"nan":"NaN", "infinity":"Infinity", "negative_infinity":"-Infinity"}[os.environ["FAKE_MODE"]]
   b = ('{"jsonrpc":"2.0","id":' + str(i) + ',"result":' + token + '}').encode()
   sys.stdout.buffer.write(b"Content-Length: "+str(len(b)).encode()+b"\r\n\r\n"+b); sys.stdout.buffer.flush()
  else:
   send({"jsonrpc":"2.0","id":i,"result":{"capabilities":{"positionEncoding":enc}}})
  if os.environ.get("FAKE_MODE")=="blocked_write":
   if os.environ.get("PID_FILE"):
    open(os.environ["PID_FILE"], "w").write(str(os.getpid()))
   time.sleep(60)
 elif m=="shutdown": send({"jsonrpc":"2.0","id":i,"result":None})
 elif m=="textDocument/hover":
  send({"jsonrpc":"2.0","id":i,"result":{"contents":{"kind":"markdown","value":"x"},
       "range":{"start":{"line":0,"character":0},"end":{"line":0,"character":2}}}})
 elif os.environ.get("FAKE_MODE")=="outside":
  send({"jsonrpc":"2.0","id":i,"result":[{"uri":"file:///outside.rs","range":{"start":{"line":0,"character":0},"end":{"line":0,"character":1}}}]})
 elif os.environ.get("FAKE_MODE")=="malformed_json":
  sys.stdout.buffer.write(b"Content-Length: 1\r\n\r\n{"); sys.stdout.buffer.flush()
 elif os.environ.get("FAKE_MODE")=="malformed_header":
  sys.stdout.buffer.write(b"Not-LSP\r\n\r\nx"); sys.stdout.buffer.flush()
 elif os.environ.get("FAKE_MODE")=="bad": sys.stdout.write("bad"); sys.stdout.flush(); os._exit(0)
 elif os.environ.get("FAKE_MODE")=="error": send({"jsonrpc":"2.0","id":i,"error":{"code":-1}})
 elif os.environ.get("FAKE_MODE")=="hang":
  if os.environ.get("PID_FILE"):
   open(os.environ["PID_FILE"], "w").write(str(os.getpid()))
  time.sleep(60)
 elif os.environ.get("FAKE_MODE")=="race":
  with open(os.environ["RACE_FILE"], "a") as f: f.write("changed")
  u=x["params"]["textDocument"]["uri"]
  send({"jsonrpc":"2.0","id":i,"result":[]})
 else:
  u=x["params"]["textDocument"]["uri"]
  a={"uri":u,"range":{"start":{"line":2,"character":1},"end":{"line":2,"character":2}}}
  b={"uri":u,"range":{"start":{"line":1,"character":3},"end":{"line":1,"character":4}}}
  values=[b,a,a] if os.environ.get("ORDER")=="reverse" else [a,a,b]
  send({"jsonrpc":"2.0","id":i,"result":values if m.endswith("references") else [a]})
'''


@pytest.fixture
def authority(tmp_path):
    p = tmp_path / "fake-ra"
    p.write_text(FAKE)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def repo(tmp_path):
    (tmp_path / "a.rs").write_text("fn main() {}\n")


def test_canonical_locations_hover_and_identity(authority, tmp_path, monkeypatch):
    repo(tmp_path)
    a = RustAnalyzerAuthority(str(authority), "fake 1")
    q = SemanticQuery("references", "a.rs", 0, 0)
    one = query_rust_semantics(tmp_path, a, q)
    two = query_rust_semantics(tmp_path, a, q)
    assert one == two
    doc = json.loads(one)
    assert len(doc["result"]["value"]) == 2
    assert doc["repositoryWitness"] == repository_witness(tmp_path)
    assert doc["authority"]["version"] == "fake 1"
    assert query_rust_semantics(tmp_path, a, SemanticQuery("hover", "a.rs", 0, 0)) != one


@pytest.mark.parametrize(("mode", "code"), [
    ("bad", "malformed_lsp"), ("error", "server_error"), ("hang", "timeout")
])
def test_protocol_failures_are_stable(authority, tmp_path, monkeypatch, mode, code):
    repo(tmp_path)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0), timeout=.15)
    assert exc.value.code == code


def test_paths_and_external_results_fail_closed(authority, tmp_path):
    repo(tmp_path)
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0),
                             witness="wrong")
    assert exc.value.code == "witness_mismatch"
    with pytest.raises(SemanticQueryError) as exc:
        SemanticQuery("definition", "../a.rs", 0, 0)
    assert exc.value.code == "unauthorized_path"


def test_definition_result_canonicalization(authority, tmp_path):
    repo(tmp_path)
    result = json.loads(query_rust_semantics(
        tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
        SemanticQuery("definition", "a.rs", 0, 0)))
    assert result["result"]["value"] == [{
        "path": "a.rs",
        "start": {"line": 2, "character": 1},
        "end": {"line": 2, "character": 2},
    }]


def test_references_server_order_has_byte_identical_canonical_output(
    authority, tmp_path, monkeypatch
):
    repo(tmp_path)
    a = RustAnalyzerAuthority(str(authority), "fake")
    q = SemanticQuery("references", "a.rs", 0, 0)
    monkeypatch.setenv("ORDER", "reverse")
    reverse = query_rust_semantics(tmp_path, a, q)
    monkeypatch.delenv("ORDER")
    forward = query_rust_semantics(tmp_path, a, q)
    assert reverse == forward


def test_duplicate_reference_locations_collapse_deterministically(authority, tmp_path):
    repo(tmp_path)
    doc = json.loads(query_rust_semantics(
        tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
        SemanticQuery("references", "a.rs", 0, 0)))
    values = doc["result"]["value"]
    assert len(values) == 2
    key = lambda x: (x["path"], x["start"]["line"], x["start"]["character"],
                     x["end"]["line"], x["end"]["character"])
    assert values == sorted(values, key=key)


def test_hover_result_canonicalization(authority, tmp_path):
    repo(tmp_path)
    doc = json.loads(query_rust_semantics(
        tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
        SemanticQuery("hover", "a.rs", 0, 0)))
    assert doc["result"]["value"] == {
        "contents": {"kind": "markdown", "value": "x"},
        "range": {"start": {"line": 0, "character": 0},
                  "end": {"line": 0, "character": 2}},
    }


def test_path_escape_is_rejected_before_lsp_execution(authority, tmp_path):
    repo(tmp_path)
    with pytest.raises(SemanticQueryError) as exc:
        SemanticQuery("definition", "../a.rs", 0, 0)
    assert exc.value.code == "unauthorized_path"


def test_external_lsp_result_uri_is_rejected(authority, tmp_path, monkeypatch):
    repo(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "outside")
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0))
    assert exc.value.code == "result_uri_outside_repository"


@pytest.mark.parametrize("mode", ["malformed_json", "malformed_header"])
def test_malformed_lsp_fails_closed_with_stable_error(authority, tmp_path, monkeypatch, mode):
    repo(tmp_path)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0))
    assert exc.value.code == "malformed_lsp"


def test_json_rpc_server_error_fails_closed(authority, tmp_path, monkeypatch):
    repo(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "error")
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0))
    assert exc.value.code == "server_error"


def test_timeout_terminalizes_subprocess(authority, tmp_path, monkeypatch):
    repo(tmp_path)
    pid_file = tmp_path / "pid"
    monkeypatch.setenv("FAKE_MODE", "hang")
    monkeypatch.setenv("PID_FILE", str(pid_file))
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0), timeout=.1)
    assert exc.value.code == "timeout"
    pid = int(pid_file.read_text())
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        import time
        time.sleep(.02)
    else:
        pytest.fail("fake rust-analyzer subprocess retained after timeout")


def test_repository_witness_change_during_query_fails_closed(authority, tmp_path, monkeypatch):
    repo(tmp_path)
    changed = tmp_path / "changed.txt"
    changed.write_text("before")
    monkeypatch.setenv("FAKE_MODE", "race")
    monkeypatch.setenv("RACE_FILE", str(changed))
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0))
    assert exc.value.code == "witness_mismatch"


def test_tool_identity_is_provenance_and_result_identity(authority, tmp_path):
    repo(tmp_path)
    q = SemanticQuery("definition", "a.rs", 0, 0)
    one = query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "one"), q)
    two = query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "two"), q)
    assert json.loads(one)["authority"]["version"] == "one"
    assert one != two


def test_identical_repository_authority_query_is_byte_and_digest_stable(authority, tmp_path):
    import hashlib
    repo(tmp_path)
    a = RustAnalyzerAuthority(str(authority), "fake")
    q = SemanticQuery("hover", "a.rs", 0, 0)
    one = query_rust_semantics(tmp_path, a, q)
    two = query_rust_semantics(tmp_path, a, q)
    assert one == two
    assert hashlib.sha256(one).digest() == hashlib.sha256(two).digest()


def test_semantic_query_path_and_position_change_query_identity(authority, tmp_path):
    repo(tmp_path)
    (tmp_path / "b.rs").write_text("fn other() {}\n")
    a = RustAnalyzerAuthority(str(authority), "fake")
    base = json.loads(query_rust_semantics(
        tmp_path, a, SemanticQuery("definition", "a.rs", 0, 0)))
    path = json.loads(query_rust_semantics(
        tmp_path, a, SemanticQuery("definition", "b.rs", 0, 0)))
    position = json.loads(query_rust_semantics(
        tmp_path, a, SemanticQuery("definition", "a.rs", 1, 0)))
    assert base["query"] != path["query"]
    assert base["query"] != position["query"]


def test_non_utf8_position_encoding_fails_closed(authority, tmp_path, monkeypatch):
    repo(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "wrong_encoding")
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("hover", "a.rs", 0, 0))
    assert exc.value.code == "unsupported_position_encoding"


def test_blocked_stdin_write_is_bounded_and_reaped(authority, tmp_path, monkeypatch):
    # initialize is acknowledged, then the fake server deliberately stops
    # reading.  didOpen therefore has to exercise the real pipe write path.
    (tmp_path / "a.rs").write_text("fn main() {\n" + ("x" * 300_000) + "\n}\n")
    pid_file = tmp_path / "pid"
    monkeypatch.setenv("FAKE_MODE", "blocked_write")
    monkeypatch.setenv("PID_FILE", str(pid_file))
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("hover", "a.rs", 0, 0), timeout=.15)
    assert exc.value.code == "timeout"
    pid = int(pid_file.read_text())
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        import time
        time.sleep(.02)
    else:
        pytest.fail("blocked fake rust-analyzer was not reaped")


def test_boolean_json_rpc_id_is_rejected(authority, tmp_path, monkeypatch):
    repo(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "boolean_id")
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0))
    assert exc.value.code == "malformed_lsp"


@pytest.mark.parametrize("mode", ["nan", "infinity", "negative_infinity"])
def test_non_finite_json_is_rejected(authority, tmp_path, monkeypatch, mode):
    repo(tmp_path)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("definition", "a.rs", 0, 0))
    assert exc.value.code == "malformed_lsp"


def test_canonical_atlas_serialization_rejects_non_finite_internal_data(
    authority, tmp_path, monkeypatch
):
    repo(tmp_path)
    import atlas.semantic_query as module
    monkeypatch.setattr(module, "_hover",
                        lambda value: {"contents": float("nan"), "range": None})
    with pytest.raises(SemanticQueryError) as exc:
        query_rust_semantics(tmp_path, RustAnalyzerAuthority(str(authority), "fake"),
                             SemanticQuery("hover", "a.rs", 0, 0))
    assert exc.value.code == "malformed_lsp"
