"""A small, hermetic rust-analyzer semantic query boundary.

This module deliberately does not contain an editor abstraction.  An authority
is an executable selected by the caller and every invocation is a new process.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import selectors
import subprocess
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse


class SemanticQueryError(Exception):
    """A terminal, stable failure from the semantic-query boundary."""
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class RustAnalyzerAuthority:
    executable: str
    version: str | None = None

    def __post_init__(self):
        p = Path(self.executable)
        if not p.is_absolute():
            raise SemanticQueryError("tool_identity_unavailable",
                                     "rust-analyzer authority must be absolute")
        if not p.is_file() or not os.access(p, os.X_OK):
            raise SemanticQueryError("tool_identity_unavailable")


@dataclass(frozen=True, slots=True)
class SemanticQuery:
    kind: str
    path: str
    line: int
    character: int

    def __post_init__(self):
        if self.kind not in {"definition", "references", "hover"}:
            raise SemanticQueryError("invalid_query")
        if type(self.path) is not str or not self.path or Path(self.path).is_absolute():
            raise SemanticQueryError("invalid_query")
        if type(self.line) is not int or type(self.character) is not int or self.line < 0 or self.character < 0:
            raise SemanticQueryError("invalid_query")
        posix = PurePosixPath(self.path.replace("\\", "/"))
        if ".." in posix.parts or str(posix) in {".", ""}:
            raise SemanticQueryError("unauthorized_path")
        if "\\" in self.path or str(posix) != self.path:
            raise SemanticQueryError("invalid_query")


def repository_witness(root: str | os.PathLike[str]) -> str:
    """Return a deterministic digest of regular repository bytes (not .git)."""
    base = Path(root).resolve(strict=True)
    h = hashlib.sha256()
    files = []
    for p in base.rglob("*"):
        if ".git" in p.relative_to(base).parts or not p.is_file() or p.is_symlink():
            continue
        files.append(p)
    for p in sorted(files, key=lambda x: x.relative_to(base).as_posix()):
        rel = p.relative_to(base).as_posix().encode()
        data = p.read_bytes()
        h.update(len(rel).to_bytes(8, "big")); h.update(rel)
        h.update(len(data).to_bytes(8, "big")); h.update(data)
    return h.hexdigest()


def _error(code: str, detail: str = "") -> SemanticQueryError:
    return SemanticQueryError(code, detail)


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
        except (TypeError, ValueError):
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
            if "id" not in msg:
                # Notifications are valid traffic while waiting for a
                # response, but a response-shaped object must be strict.
                continue
            response_id = msg["id"]
            if type(response_id) is not int:
                raise _error("malformed_lsp")
            if response_id != ident:
                continue
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
            length = next(int(x.split(":", 1)[1].strip()) for x in headers[:-4].decode("ascii").split("\r\n")
                          if x.lower().startswith("content-length:"))
        except (ValueError, StopIteration, UnicodeDecodeError):
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
            value = json.loads(data, parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError("non-finite JSON number")))
        except (ValueError, UnicodeDecodeError):
            raise _error("malformed_lsp")
        if (not isinstance(value, dict) or type(value.get("jsonrpc")) is not str
                or value.get("jsonrpc") != "2.0"):
            raise _error("malformed_lsp")
        # A message without an id is only a notification.  All response
        # messages must carry an exact integer id; in particular bool is not
        # an integer id for JSON-RPC purposes.
        if "id" not in value:
            if (type(value.get("method")) is not str
                    or "result" in value or "error" in value):
                raise _error("malformed_lsp")
        elif (type(value["id"]) is not int or "method" in value
              or ("result" not in value and "error" not in value)):
            raise _error("malformed_lsp")
        return value


def _uri_location(root: Path, value: dict) -> dict:
    uri = value.get("uri")
    parsed = urlparse(uri) if isinstance(uri, str) else None
    if parsed is None or parsed.scheme != "file" or parsed.netloc:
        raise _error("result_uri_outside_repository")
    raw = Path(unquote(parsed.path))
    try:
        path = raw.resolve(strict=False).relative_to(root)
    except ValueError:
        raise _error("result_uri_outside_repository")
    if raw.exists() and raw.is_symlink():
        raise _error("result_uri_outside_repository")
    rg = value.get("range")
    if not isinstance(rg, dict):
        raise _error("malformed_lsp")
    def point(x):
        if not isinstance(x, dict) or type(x.get("line")) is not int or type(x.get("character")) is not int:
            raise _error("malformed_lsp")
        return {"line": x["line"], "character": x["character"]}
    return {"path": path.as_posix(), "start": point(rg.get("start")), "end": point(rg.get("end"))}


def _locations(root: Path, result: Any) -> list[dict]:
    if result is None: return []
    if isinstance(result, dict): result = [result]
    if not isinstance(result, list): raise _error("malformed_lsp")
    out = []
    for item in result:
        if not isinstance(item, dict): raise _error("malformed_lsp")
        if "targetUri" in item: item = {"uri": item.get("targetUri"), "range": item.get("targetSelectionRange", item.get("range"))}
        out.append(_uri_location(root, item))
    unique = {(json.dumps(x, sort_keys=True, separators=(",", ":"))): x for x in out}
    return [unique[k] for k in sorted(unique, key=lambda k: (unique[k]["path"], unique[k]["start"]["line"],
             unique[k]["start"]["character"], unique[k]["end"]["line"], unique[k]["end"]["character"]))]


def _hover(value: Any) -> dict:
    if value is None: return {"contents": None, "range": None}
    if not isinstance(value, dict): raise _error("malformed_lsp")
    contents = value.get("contents")
    # Keep content verbatim structurally, while making arrays and absent range explicit.
    if not isinstance(contents, (str, dict, list)):
        raise _error("malformed_lsp")
    hrange = value.get("range")
    if hrange is not None:
        if not isinstance(hrange, dict):
            raise _error("malformed_lsp")
        def hp(name):
            p = hrange.get(name)
            if not isinstance(p, dict) or type(p.get("line")) is not int or type(p.get("character")) is not int:
                raise _error("malformed_lsp")
            return {"line": p["line"], "character": p["character"]}
        hrange = {"start": hp("start"), "end": hp("end")}
    return {"contents": contents, "range": hrange}


def query_rust_semantics(root: str | os.PathLike[str], authority: RustAnalyzerAuthority,
                         query: SemanticQuery, *, witness: str | None = None,
                         timeout: float = 10.0) -> bytes:
    """Execute exactly one fresh LSP session and return canonical JSON bytes."""
    deadline = time.monotonic() + timeout
    base = Path(root).resolve(strict=True)
    source = (base / query.path)
    try: source.relative_to(base)
    except ValueError: raise _error("unauthorized_path")
    try:
        resolved_source = source.resolve(strict=True)
        resolved_source.relative_to(base)
    except (OSError, ValueError):
        raise _error("unauthorized_path" if source.exists() else "missing_file")
    if source.is_symlink() or not source.is_file(): raise _error("missing_file")
    before = repository_witness(base)
    if witness is not None and witness != before: raise _error("witness_mismatch")
    try:
        # TextIOWrapper would translate newlines; didOpen must contain the
        # exact witnessed document bytes.
        text = source.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise _error("missing_file")
    version = authority.version
    proc = None
    lsp = None
    try:
        if version is None:
            try:
                remaining = max(0, deadline - time.monotonic())
                if not remaining:
                    raise _error("timeout")
                version = subprocess.check_output([authority.executable, "--version"], text=True,
                                                   stderr=subprocess.STDOUT, timeout=remaining).strip()
            except SemanticQueryError:
                raise
            except Exception:
                raise _error("tool_identity_unavailable")
        proc = subprocess.Popen([authority.executable], cwd=str(base), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Drain stderr in a bounded reader so a noisy tool cannot deadlock the
        # protocol.  Stderr is diagnostic only and is never semantic output.
        def drain_stderr():
            remaining = 64 * 1024
            while remaining:
                chunk = proc.stderr.read(min(4096, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            while proc.stderr.read(4096):
                pass
        threading.Thread(target=drain_stderr, daemon=True).start()
        lsp = _Lsp(proc, deadline)
        init = lsp.request("initialize", {"processId": None, "rootUri": base.as_uri(),
             "capabilities": {"general": {"positionEncodings": ["utf-8"]}},
             "workspaceFolders": [{"uri": base.as_uri(), "name": base.name}]})
        enc = (init.get("capabilities", {}) if isinstance(init, dict) else {}).get("positionEncoding")
        if enc != "utf-8": raise _error("unsupported_position_encoding")
        lsp.notify("initialized", {})
        lsp.notify("textDocument/didOpen", {"textDocument": {"uri": source.as_uri(), "languageId": "rust",
                    "version": 1, "text": text}})
        params = {"textDocument": {"uri": source.as_uri()}, "position": {"line": query.line, "character": query.character}}
        result = lsp.request({"definition": "textDocument/definition", "references": "textDocument/references",
                              "hover": "textDocument/hover"}[query.kind],
                             params | ({"context": {"includeDeclaration": True}} if query.kind == "references" else {}))
        payload = _locations(base, result) if query.kind != "hover" else _hover(result)
        if repository_witness(base) != before: raise _error("witness_mismatch")
        doc = {"schema": "atlas-rust-semantic/1", "query": {"kind": query.kind, "path": query.path,
               "line": query.line, "character": query.character}, "authority": {"executable": str(Path(authority.executable)),
               "version": version}, "repositoryWitness": before, "positionEncoding": "utf-8",
               "result": {"kind": query.kind, "value": payload}}
        try:
            encoded = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            raise _error("malformed_lsp")
        return (encoded + "\n").encode("utf-8")
    except SemanticQueryError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise _error("startup_failure")
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    try:
                        # shutdown is best effort; the query result is already validated.
                        lsp.request("shutdown", None)
                        lsp.notify("exit", None)
                    except Exception: proc.kill()
                    proc.wait(timeout=1)
            except Exception:
                try: proc.kill(); proc.wait()
                except Exception: pass
