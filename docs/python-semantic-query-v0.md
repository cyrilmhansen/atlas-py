# Python semantic query v0

This isolated boundary does not change context-plan or select queries/backends.
Public API in `atlas.python_semantic_query`:

```python
PyrightAuthority(executable: str, version: str)  # frozen, explicit authority
PythonSemanticQuery(kind: str, path: str, line: int, character: int)  # frozen
PythonSemanticQueryError  # stable .code; no tool exception text
query_python_semantics(root, authority, query, *, witness=None, timeout=10.0) -> bytes
```

Only `definition`, `references`, and `hover` are supported. The existing public
`atlas.semantic_query.repository_witness` is reused unchanged. Symlink documents
(including symlink ancestors) and `.git` documents are not admitted.

Results use **`atlas-python-semantic/1`** with exactly `schema`, `query`,
`authority`, `repositoryWitness`, `positionEncoding`, and `result` at top level.
JSON is UTF-8, sorted-key, compact, non-ASCII-preserving, finite-only, with one
trailing newline. Coordinates in both query identity and results are zero-based
**UTF-8 byte offsets**, including for hover ranges. Definition and references
normalize to sorted/deduplicated `{path,start,end}` arrays, matching Rust v0;
location links use `targetSelectionRange`. Null locations become `[]`. Hover
preserves MarkupContent/MarkedString structure; absent result becomes
`{"contents":null,"range":null}` and absent range becomes null.

Each query starts the explicit executable with `--stdio`, rooted in the witnessed
repository, opens only the queried file without newline translation, and tears
the process down. The adapter advertises UTF-8 and UTF-16, honors either explicit
selection, defaults omission to UTF-16, and rejects other encodings. Exact
Unicode prefixes are converted between UTF-8 bytes and UTF-16 code units, with
out-of-file and split-code-point/split-surrogate positions rejected. Returned
ranges use repository file bytes, checked against the witness before acceptance.
External locations are failures, never silently filtered into repository results.

`workspace/configuration` is the sole supported server request; each requested
item receives `{}` (no client interpreter selection or mutable editor settings).
Other server requests fail closed. Valid irrelevant notifications are discarded
under the same deadline. There is no client file mutation or command execution
handler. Headers are bounded at 8192 bytes, each incoming/outgoing JSON body at
4 MiB, stderr goes to the null sink (zero retained bytes), and pipe writes as
well as reads share one deadline. Shutdown is best effort within that deadline;
expiry does not produce an accepted result. Process kill/reaping is mandatory
cleanup, not a fresh semantic-query timeout budget.

Stable error codes:

- `invalid_query`
- `unauthorized_path`
- `missing_file`
- `tool_identity_unavailable`
- `timeout`
- `startup_failure`
- `malformed_lsp`
- `unsupported_position_encoding`
- `result_uri_outside_repository`
- `witness_mismatch`
- `response_too_large`
- `unsupported_server_request`
- `server_error`

The explicit version is caller-provided provenance, not a version probe or a
binary digest. The adapter never discovers Pyright via PATH or another CLI.
As with the Rust witness, before/after byte witnessing is not an OS filesystem
snapshot: callers must supply a stable repository during the operation.

## Manual host smoke (not an automated test dependency)

From the Atlas checkout, run this exact command. It creates a separate small
repository root in a temporary directory; all queried/returned files are local
to that root. It performs no install, commit, activation, or boundary adoption.
The version is explicitly supplied, not queried through an ambient executable.

```bash
PYTHONPATH=src python - <<'PY'
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from atlas.python_semantic_query import (
    PyrightAuthority, PythonSemanticQuery, query_python_semantics,
    repository_witness,
)

authority = PyrightAuthority(
    executable="/usr/bin/pyright-langserver",
    version="pyright 1.1.412",
)
with TemporaryDirectory(prefix="atlas-python-smoke-") as directory:
    root = Path(directory)
    (root / "sample.py").write_bytes(
        'def greet(name: str) -> str:\n'
        '    return "héllo 😀 " + name\n'
        '\n'
        'message = greet("Atlas")\n'.encode("utf-8")
    )
    witness = repository_witness(root)
    for kind in ("hover", "definition", "references"):
        query = PythonSemanticQuery(kind, "sample.py", 3, 10)
        raw = query_python_semantics(
            root, authority, query, witness=witness, timeout=20.0,
        )
        assert raw == query_python_semantics(
            root, authority, query, witness=witness, timeout=20.0,
        )
        print(raw.decode("utf-8"), end="")
        assert json.loads(raw)["schema"] == "atlas-python-semantic/1"
PY
```
