from __future__ import annotations
import hashlib, subprocess
from pathlib import Path
class RepositoryError(RuntimeError): pass
def _run(root,*args):
    p=subprocess.run(["git",*args],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise RepositoryError(p.stderr.decode("utf-8","replace").strip() or "git command failed")
    return p.stdout
def git(root:Path,*args:str)->str: return _run(root,*args).decode("utf-8").strip()
def find_root(start:Path)->Path: return Path(git(start,"rev-parse","--show-toplevel")).resolve()
def runtime_path(root:Path)->Path:
    raw=_run(root,"rev-parse","--git-path","atlas-agent").rstrip(b"\r\n"); p=Path(raw.decode("utf-8","surrogateescape"))
    return (root/p).resolve() if not p.is_absolute() else p.resolve()
def _allowed(path,allowed):
    return any(path==a[:-1] or path.startswith(a) for a in allowed if a.endswith("/")) or any(path==a for a in allowed if not a.endswith("/"))
def _ok(root,*args): return subprocess.run(["git",*args],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def witness(root:Path,allowed:list[str])->dict:
    head=_run(root,"rev-parse","HEAD").strip().decode("ascii")
    branch=_run(root,"symbolic-ref","--quiet","--short","HEAD").strip().decode("utf-8","replace") if _ok(root,"symbolic-ref","--quiet","--short","HEAD") else None
    records=[x for x in _run(root,"status","--porcelain=v2","--untracked-files=all","-z").split(b"\0") if x]
    index=[]; work=[]; unexpected=[]
    for rec in records:
        if rec.startswith(b"? "):
            name=rec[2:]; text=name.decode("utf-8","surrogateescape")
            if not _allowed(text,allowed): unexpected.append(name.hex())
        elif rec[:2] in (b"1 ",b"2 ",b"u "):
            parts=rec.split(b" ",3); xy=parts[1]; sub=parts[2] if len(parts)>2 else b""
            # Intent-to-add is reported as a worktree-side add with an N
            # submodule/status marker, even though cached diff is empty.
            if xy[:1]!=b"." or xy==b".A": index.append(rec)
            if xy[1:2]!=b".": work.append(rec)
    digest=lambda xs:hashlib.sha256(b"\0".join(sorted(xs))).hexdigest()
    # This is deliberately a Git byte stream. It contains the actual patch
    # bytes, not merely the porcelain status category.
    content=_run(root,"--no-pager","diff","--no-ext-diff","--no-textconv","--no-color","--binary","--")
    return {"head":head,"branch":branch,"index_semantic_sha256":digest(index),"tracked_worktree_sha256":digest(work),"tracked_worktree_content_sha256":hashlib.sha256(content).hexdigest(),"unexpected_untracked":sorted(unexpected)}
def same_witness(a,b): return a==b
