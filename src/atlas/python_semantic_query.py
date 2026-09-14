"""Isolated, one-shot Pyright LSP boundary with canonical UTF-8 coordinates.

Only repository_witness is shared with the qualified Rust boundary. Transport
is intentionally local: this is not a backend registry or an editor client.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import selectors
import subprocess
import time
from typing import Any
from urllib.parse import unquote, urlparse

from .semantic_query import repository_witness


class PythonSemanticQueryError(Exception):
    """Terminal backend failure; ``code`` is the stable API authority."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _error(code):
    return PythonSemanticQueryError(code)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('non-finite JSON number')
    return number


@dataclass(frozen=True, slots=True)
class PyrightAuthority:
    executable: str
    version: str

    def __post_init__(self):
        if (type(self.executable) is not str or not Path(self.executable).is_absolute()
                or not Path(self.executable).is_file()
                or not os.access(self.executable, os.X_OK)
                or type(self.version) is not str or not self.version.strip()):
            raise _error("tool_identity_unavailable")


@dataclass(frozen=True, slots=True)
class PythonSemanticQuery:
    kind: str
    path: str
    line: int
    character: int

    def __post_init__(self):
        if (type(self.kind) is not str or self.kind not in {"definition", "references", "hover"}
                or type(self.path) is not str or not self.path
                or type(self.line) is not int or type(self.character) is not int
                or self.line < 0 or self.character < 0):
            raise _error("invalid_query")
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts:
            raise _error("unauthorized_path")
        if "\\" in self.path or "\x00" in self.path or str(path) != self.path or self.path == ".":
            raise _error("invalid_query")


class _Lsp:
    def __init__(self, proc, deadline: float, max_message: int = 4 * 1024 * 1024):
        self.p = proc
        self.deadline = deadline
        self.max_message = max_message
        self.next_id = 1
        # File objects use blocking writes by default.  The LSP payload can
        # include an arbitrarily large didOpen, so use the pipe fd directly.
        os.set_blocking(self.p.stdin.fileno(), False)

    def send(self, obj: dict):
        try:
            raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False).encode()
        except (TypeError, ValueError, UnicodeError):
            raise _error("malformed_lsp")
        if len(raw) > self.max_message:
            raise _error("response_too_large")
        data = b"Content-Length: " + str(len(raw)).encode() + b"\r\n\r\n" + raw
        offset = 0
        try:
            while offset < len(data):
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise _error("timeout")
                sel = selectors.DefaultSelector()
                try:
                    sel.register(self.p.stdin, selectors.EVENT_WRITE)
                    try:
                        ready = sel.select(remaining)
                    except InterruptedError:
                        continue
                    if not ready:
                        raise _error("timeout")
                finally:
                    sel.close()
                try:
                    offset += os.write(self.p.stdin.fileno(), data[offset:])
                except InterruptedError:
                    continue
                except BlockingIOError:
                    continue
        except (BrokenPipeError, OSError):
            raise _error("startup_failure")

    def request(self, method: str, params: Any):
        ident = self.next_id; self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        while True:
            msg = self.read()
            if "method" in msg:
                if "id" in msg:
                    self.server_request(msg)
                continue
            response_id = msg["id"]
            if type(response_id) is not int:
                raise _error("malformed_lsp")
            if response_id != ident:
                raise _error("malformed_lsp")
            if "error" in msg and "result" in msg:
                raise _error("malformed_lsp")
            if "error" in msg:
                if not isinstance(msg["error"], dict):
                    raise _error("malformed_lsp")
                raise _error("server_error")
            if "result" not in msg:
                raise _error("malformed_lsp")
            return msg["result"]

    def notify(self, method, params):
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def read(self):
        # select plus byte reads avoids unbounded readline/header buffering.
        out = self.p.stdout
        headers = b""
        while b"\r\n\r\n" not in headers:
            if time.monotonic() >= self.deadline:
                raise _error("timeout")
            r, _, _ = selectors.SelectSelector(), None, None
            sel = r
            sel.register(out, selectors.EVENT_READ)
            try:
                try:
                    ready = sel.select(max(0, self.deadline - time.monotonic()))
                except InterruptedError:
                    continue
                if not ready:
                    raise _error("timeout")
                try:
                    chunk = os.read(out.fileno(), 1)
                except InterruptedError:
                    continue
            finally:
                sel.close()
            if not chunk:
                raise _error("malformed_lsp")
            headers += chunk
            if len(headers) > 8192:
                raise _error("malformed_lsp")
        try:
            fields = headers[:-4].decode('ascii').split('\r\n')
            if any(':' not in x for x in fields):
                raise ValueError()
            lengths = [x.split(':', 1)[1].strip() for x in fields
                       if x.lower().startswith('content-length:')]
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                raise ValueError()
            length = int(lengths[0])
        except (ValueError, UnicodeDecodeError):
            raise _error("malformed_lsp")
        if length < 0 or length > self.max_message:
            raise _error("response_too_large")
        data = bytearray()
        while len(data) < length:
            if time.monotonic() >= self.deadline:
                raise _error("timeout")
            sel = selectors.DefaultSelector(); sel.register(out, selectors.EVENT_READ)
            try:
                ready = sel.select(max(0, self.deadline - time.monotonic()))
            except InterruptedError:
                sel.close()
                continue
            sel.close()
            if not ready: raise _error("timeout")
            try:
                chunk = os.read(out.fileno(), min(65536, length - len(data)))
            except InterruptedError:
                continue
            if not chunk: raise _error("malformed_lsp")
            data.extend(chunk)
        try:
            value = json.loads(data.decode('utf-8'), object_pairs_hook=_json_object,
                               parse_float=_json_float,
                               parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError("non-finite JSON number")))
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise _error("malformed_lsp")
        if (not isinstance(value, dict) or type(value.get("jsonrpc")) is not str
                or value.get("jsonrpc") != "2.0"):
            raise _error("malformed_lsp")
        if "method" in value:
            if (type(value["method"]) is not str or "result" in value or "error" in value
                    or set(value) - {'jsonrpc', 'id', 'method', 'params'}
                    or ("id" in value and type(value["id"]) is not int)
                    or ("params" in value and not isinstance(value["params"], (dict, list)))):
                raise _error("malformed_lsp")
        elif (set(value) - {'jsonrpc', 'id', 'result', 'error'}
              or type(value.get("id")) is not int
              or ("result" in value) == ("error" in value)):
            raise _error("malformed_lsp")
        if "error" in value:
            err = value["error"]
            if (not isinstance(err, dict) or type(err.get("code")) is not int
                    or type(err.get("message")) is not str):
                raise _error("malformed_lsp")
        return value

    def server_request(self, msg):
        if msg["method"] != "workspace/configuration":
            raise _error("unsupported_server_request")
        params = msg.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("items"), list):
            raise _error("malformed_lsp")
        for item in params["items"]:
            if (not isinstance(item, dict)
                    or ("section" in item and type(item["section"]) is not str)
                    or ("scopeUri" in item and type(item["scopeUri"]) is not str)):
                raise _error("malformed_lsp")
        # No interpreter/PATH discovery, client commands, or mutable settings.
        self.send({"jsonrpc": "2.0", "id": msg["id"],
                   "result": [{} for _ in params["items"]]})


def _file(root: Path, path: Path, code: str) -> Path:
    try:
        relative = path.relative_to(root)
        if '.git' in relative.parts:
            raise _error(code)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise _error(code)
        path.resolve(strict=False).relative_to(root)
        if not path.is_file():
            raise _error("missing_file")
        return path.resolve(strict=True)
    except (ValueError, OSError):
        raise _error(code)


def _text(path: Path, code: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        raise _error(code)


def _lines(text: str) -> list[str]:
    # LSP recognizes CRLF, CR and LF, not Python's broader splitlines set.
    return text.replace('\r\n', '\n').replace('\r', '\n').split('\n')


def _convert(text: str, line: int, character: int, source: str, target: str,
             code: str) -> int:
    if type(line) is not int or type(character) is not int or line < 0 or character < 0:
        raise _error(code)
    lines = _lines(text)
    if line >= len(lines):
        raise _error(code)
    codec = 'utf-16-le' if source == 'utf-16' else 'utf-8'
    width = 2 if source == 'utf-16' else 1
    raw = lines[line].encode(codec)
    if character * width > len(raw):
        raise _error(code)
    try:
        prefix = raw[:character * width].decode(codec)
    except UnicodeError:
        raise _error(code)
    return len(prefix.encode('utf-16-le')) // 2 if target == 'utf-16' else len(prefix.encode('utf-8'))


def _range(text: str, value: Any, encoding: str) -> dict:
    if not isinstance(value, dict):
        raise _error('malformed_lsp')
    out = {}
    for key in ('start', 'end'):
        point = value.get(key)
        if not isinstance(point, dict):
            raise _error('malformed_lsp')
        line, character = point.get('line'), point.get('character')
        out[key] = {'line': line, 'character': _convert(
            text, line, character, encoding, 'utf-8', 'malformed_lsp')}
    if (out['start']['line'], out['start']['character']) > (out['end']['line'], out['end']['character']):
        raise _error('malformed_lsp')
    return out


def _locations(root: Path, value: Any, encoding: str, source_text: str) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise _error('malformed_lsp')
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise _error('malformed_lsp')
        link = 'targetUri' in item
        uri = item.get('targetUri' if link else 'uri')
        try:
            parsed = urlparse(uri) if type(uri) is str else None
            if (parsed is None or parsed.scheme != 'file' or parsed.netloc
                    or parsed.query or parsed.fragment or not parsed.path.startswith('/')
                    or '\x00' in unquote(parsed.path) or '\\' in unquote(parsed.path)):
                raise ValueError()
            path = _file(root, Path(unquote(parsed.path)), 'result_uri_outside_repository')
        except ValueError:
            raise _error('result_uri_outside_repository')
        text = _text(path, 'malformed_lsp')
        rg = _range(text, item.get('targetSelectionRange' if link else 'range'), encoding)
        if link:
            target = _range(text, item.get('targetRange'), encoding)
            if 'originSelectionRange' in item:
                _range(source_text, item['originSelectionRange'], encoding)
            key = lambda p: (p['line'], p['character'])
            if not key(target['start']) <= key(rg['start']) <= key(rg['end']) <= key(target['end']):
                raise _error('malformed_lsp')
        out.append({'path': path.relative_to(root).as_posix(), **rg})
    def key(x):
        return (x['path'], x['start']['line'], x['start']['character'],
                x['end']['line'], x['end']['character'])
    return sorted({key(x): x for x in out}.values(), key=key)


def _hover(text: str, value: Any, encoding: str) -> dict:
    if value is None:
        return {'contents': None, 'range': None}
    if not isinstance(value, dict):
        raise _error('malformed_lsp')
    contents = value.get('contents')
    def marked(v):
        return isinstance(v, str) or (isinstance(v, dict) and set(v) == {'language', 'value'}
                                     and all(type(x) is str for x in v.values()))
    if not (marked(contents) or (isinstance(contents, list) and all(marked(v) for v in contents))
            or (isinstance(contents, dict) and set(contents) == {'kind', 'value'}
                and contents['kind'] in ('plaintext', 'markdown') and type(contents['value']) is str)):
        raise _error('malformed_lsp')
    rg = value.get('range')
    return {'contents': contents, 'range': None if rg is None else _range(text, rg, encoding)}


def query_python_semantics(root: str | os.PathLike[str], authority: PyrightAuthority,
                           query: PythonSemanticQuery, *, witness: str | None = None,
                           timeout: float = 10.0) -> bytes:
    """Return atlas-python-semantic/1 JSON bytes from one fresh --stdio process.

    All input/output coordinates are zero-based UTF-8 byte offsets. ``timeout``
    is one operation deadline, not a timeout renewed for each protocol message.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise _error('invalid_query')
    deadline = time.monotonic() + timeout
    authority.__post_init__()
    query.__post_init__()
    proc = None
    lsp = None
    try:
        base = Path(root).resolve(strict=True)
        source = _file(base, base / query.path, 'unauthorized_path')
        before = repository_witness(base)
        if witness is not None and witness != before:
            raise _error('witness_mismatch')
        text = _text(source, 'invalid_query')
        _convert(text, query.line, query.character, 'utf-8', 'utf-8', 'invalid_query')
        if time.monotonic() >= deadline:
            raise _error('timeout')
        # Stderr is intentionally discarded: zero retained bytes, no reader
        # thread or unbounded diagnostic buffer, and no pipe-backpressure.
        proc = subprocess.Popen([authority.executable, '--stdio'], cwd=base,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        lsp = _Lsp(proc, deadline)
        init = lsp.request('initialize', {
            'processId': None, 'rootUri': base.as_uri(),
            'capabilities': {'general': {'positionEncodings': ['utf-8', 'utf-16']},
                             'workspace': {'configuration': True}},
            'workspaceFolders': [{'uri': base.as_uri(), 'name': base.name}]})
        if not isinstance(init, dict) or not isinstance(init.get('capabilities'), dict):
            raise _error('malformed_lsp')
        encoding = init['capabilities'].get('positionEncoding', 'utf-16')
        if encoding not in ('utf-8', 'utf-16'):
            raise _error('unsupported_position_encoding')
        character = _convert(text, query.line, query.character, 'utf-8', encoding, 'invalid_query')
        lsp.notify('initialized', {})
        lsp.notify('textDocument/didOpen', {'textDocument': {
            'uri': source.as_uri(), 'languageId': 'python', 'version': 1, 'text': text}})
        params = {'textDocument': {'uri': source.as_uri()},
                  'position': {'line': query.line, 'character': character}}
        if query.kind == 'references':
            params['context'] = {'includeDeclaration': True}
        result = lsp.request('textDocument/' + query.kind, params)
        if repository_witness(base) != before:
            raise _error('witness_mismatch')
        payload = (_hover(text, result, encoding) if query.kind == 'hover'
                   else _locations(base, result, encoding, text))
        # Shutdown cannot extend the deadline, and mutations during shutdown
        # must also be witnessed before acceptance.
        try:
            lsp.request('shutdown', None)
            lsp.notify('exit', None)
            proc.wait(timeout=max(0, deadline - time.monotonic()))
        except PythonSemanticQueryError as exc:
            if exc.code != 'timeout':
                raise
        except subprocess.TimeoutExpired:
            pass
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if repository_witness(base) != before:
            raise _error('witness_mismatch')
        if time.monotonic() >= deadline:
            raise _error('timeout')
        doc = {'schema': 'atlas-python-semantic/1',
               'query': {'kind': query.kind, 'path': query.path, 'line': query.line,
                         'character': query.character},
               'authority': {'executable': authority.executable, 'version': authority.version},
               'repositoryWitness': before, 'positionEncoding': 'utf-8',
               'result': {'kind': query.kind, 'value': payload}}
        try:
            encoded = (json.dumps(doc, sort_keys=True, separators=(',', ':'),
                                  ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        except (ValueError, TypeError, UnicodeError):
            raise _error('malformed_lsp')
        if time.monotonic() >= deadline:
            raise _error('timeout')
        return encoded
    except (OSError, subprocess.SubprocessError):
        raise _error('startup_failure')
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdin.close()
            proc.stdout.close()
