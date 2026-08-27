from __future__ import annotations
import hashlib, os, stat, subprocess
from pathlib import Path
class RepositoryError(RuntimeError): pass
def _run(root,*args,input_data=None):
    p=subprocess.run(["git",*args],cwd=root,input=input_data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
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
def _untracked_record(root,name,content=None,symlink=None):
    path=root/os.fsdecode(name)
    if content is None:
        mode=path.lstat().st_mode
        if stat.S_ISLNK(mode): content=os.fsencode(os.readlink(path)); symlink=True
        elif stat.S_ISREG(mode): content=path.read_bytes(); symlink=False
        else: raise RepositoryError("UNSUPPORTED_UNTRACKED_FILE_TYPE")
    kind=b"symlink\0" if symlink else b"file\0"
    return {"path":name.hex(),"content_sha256":hashlib.sha256(kind+content).hexdigest()}
def _staged_untracked(root,names):
    if not names: return []
    records=[x for x in _run(root,"--literal-pathspecs","ls-files","--stage","-z","--",*names).split(b"\0") if x]
    result=[]
    for rec in records:
        metadata,name=rec.split(b"\t",1); mode,oid,stage_number=metadata.split(b" ")
        if stage_number!=b"0": raise RepositoryError("CHECKPOINT_STAGED_CONTENT_MISMATCH")
        result.append(_untracked_record(root,name,_run(root,"cat-file","blob",oid.decode("ascii")),mode==b"120000"))
    return sorted(result,key=lambda x:x["path"])
def witness(root:Path,allowed:list[str],ownership=None)->dict:
    head=_run(root,"rev-parse","HEAD").strip().decode("ascii")
    branch=_run(root,"symbolic-ref","--quiet","--short","HEAD").strip().decode("utf-8","replace") if _ok(root,"symbolic-ref","--quiet","--short","HEAD") else None
    records=[x for x in _run(root,"status","--porcelain=v2","--untracked-files=all","--ignored","-z").split(b"\0") if x]
    index=[]; work=[]; unexpected=[]
    for rec in records:
        if rec.startswith((b"? ", b"! ")):
            name=rec[2:]; text=name.decode("utf-8","surrogateescape")
            owned=(ownership or {}).get("patch_owned_untracked",[])
            protected=[x["path"] for x in (ownership or {}).get("protected_untracked",[])]
            if name.hex() in set(owned)|set(protected): unexpected.append(_untracked_record(root,name))
            elif rec.startswith(b"? ") and not _allowed(text,allowed): unexpected.append(_untracked_record(root,name))
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
    known={x["path"] for x in unexpected}
    for encoded in set((ownership or {}).get("patch_owned_untracked",[])) | {x["path"] for x in (ownership or {}).get("protected_untracked",[])}:
        if encoded in known: continue
        name=bytes.fromhex(encoded); path=root/os.fsdecode(name)
        if _ok(root,"--literal-pathspecs","ls-files","--error-unmatch","--",name): continue
        if path.exists() or path.is_symlink(): unexpected.append(_untracked_record(root,name))
    unexpected.sort(key=lambda x:x["path"])
    return {"head":head,"branch":branch,"index_semantic_sha256":digest(index),"tracked_worktree_sha256":digest(work),"tracked_worktree_content_sha256":hashlib.sha256(content).hexdigest(),"unexpected_untracked":sorted(unexpected,key=lambda x:x["path"])}
def same_witness(a,b): return a==b

def _rollback_checkpoint(root,allowed,expected,original):
    try:
        if git(root,"rev-parse","HEAD")!=expected["head"]:
            raise RepositoryError("CHECKPOINT_ROLLBACK_HEAD_MISMATCH")
        _run(root,"reset","--mixed",expected["head"],"--")
        if witness(root,allowed,{"protected_untracked":expected.get("unexpected_untracked",[])})!=expected:
            raise RepositoryError("CHECKPOINT_ROLLBACK_WITNESS_MISMATCH")
    except RepositoryError as error:
        raise RepositoryError(f"CHECKPOINT_ROLLBACK_FAILED: {error}") from original

def rollback_checkpoint(root:Path,allowed:list[str],expected:dict,original:Exception):
    """Restore the reviewed unstaged state or surface a distinct recovery error."""
    _rollback_checkpoint(root,allowed,expected,original)

def _commit_object(root,commit):
    raw=_run(root,"cat-file","commit",commit)
    headers=raw.split(b"\n\n",1)[0].splitlines(); trees=[]; parents=[]
    for line in headers:
        if line.startswith(b"tree "): trees.append(line[5:].decode("ascii"))
        elif line.startswith(b"parent "): parents.append(line[7:].decode("ascii"))
    if len(trees)!=1 or len(parents)!=1: raise RepositoryError("CHECKPOINT_COMMIT_OBJECT_MISMATCH")
    return parents[0],trees[0]

def verify_checkpoint_commit(root:Path,intent:dict):
    parent,tree=_commit_object(root,intent["commit_sha"])
    if parent!=intent["parent_head"] or tree!=intent["tree_sha"]:
        raise RepositoryError("CHECKPOINT_COMMIT_OBJECT_MISMATCH")

def _active_commit_hooks(root):
    hooks=Path(_run(root,"rev-parse","--git-path","hooks").rstrip(b"\r\n").decode("utf-8","surrogateescape"))
    if not hooks.is_absolute(): hooks=root/hooks
    names=("pre-commit","prepare-commit-msg","commit-msg","post-commit","post-rewrite")
    return [name for name in names if (hooks/name).is_file() and os.access(hooks/name,os.X_OK)]

def prepare_checkpoint(root:Path,allowed:list[str],expected:dict,message:str,owned_paths=None,protected_paths=None)->dict:
    """Stage and create the exact reviewed commit object without changing HEAD."""
    if type(message) is not str or not message.strip() or "\0" in message:
        raise RepositoryError("CHECKPOINT_COMMIT_MESSAGE_REQUIRED")
    if witness(root,allowed,{"protected_untracked":[{"path":x} for x in (protected_paths or [])],"patch_owned_untracked":owned_paths or []})!=expected:
        raise RepositoryError("REPOSITORY_WITNESS_MISMATCH")
    if _active_commit_hooks(root):
        raise RepositoryError("CHECKPOINT_REPOSITORY_HOOKS_PRESENT")

    owned_paths=set(owned_paths) if owned_paths is not None else {x["path"] for x in expected["unexpected_untracked"]}
    protected_paths=set(protected_paths or [])
    owned_names={bytes.fromhex(path) for path in owned_paths}
    records=[x for x in _run(root,"status","--porcelain=v2","--untracked-files=all","--ignored","-z").split(b"\0") if x]
    tracked_paths=[]; new_paths=[]
    for rec in records:
        if rec.startswith((b"? ",b"! ")):
            name=rec[2:]
            if not _allowed(name.decode("utf-8","surrogateescape"),allowed) and name in owned_names: new_paths.append(name)
            continue
        if not rec.startswith(b"1 "):
            raise RepositoryError("CHECKPOINT_UNHANDLED_REPOSITORY_CONTENT")
        parts=rec.split(b" ",8)
        if len(parts)!=9 or parts[1]!=b".M" or parts[2]!=b"N...":
            raise RepositoryError("CHECKPOINT_UNHANDLED_REPOSITORY_CONTENT")
        tracked_paths.append(parts[8])
    paths=tracked_paths+new_paths
    if not paths:
        raise RepositoryError("CHECKPOINT_NO_TRACKED_MODIFICATIONS")

    try:
        _run(root,"--no-pager","diff","--check","--")
    except RepositoryError as error:
        raise RepositoryError(f"CHECKPOINT_DIFF_CHECK_FAILED: {error}") from error

    staged=False
    try:
        _run(root,"--literal-pathspecs","add","-f","--",*paths)
        staged=True
        cached=_run(root,"--no-pager","--literal-pathspecs","diff","--cached","--no-ext-diff","--no-textconv","--no-color","--binary","--",*tracked_paths) if tracked_paths else b""
        if hashlib.sha256(cached).hexdigest()!=expected["tracked_worktree_content_sha256"]:
            raise RepositoryError("CHECKPOINT_STAGED_CONTENT_MISMATCH")
        after_stage=[x for x in _run(root,"status","--porcelain=v2","--untracked-files=all","-z").split(b"\0") if x]
        staged_tracked=[]; staged_new=[]
        for rec in after_stage:
            if rec.startswith((b"? ",b"! ")):
                if not _allowed(rec[2:].decode("utf-8","surrogateescape"),allowed):
                    if rec[2:].hex() in protected_paths: continue
                    if rec[2:] in new_paths: raise RepositoryError("CHECKPOINT_STAGED_CONTENT_MISMATCH")
                    raise RepositoryError("CHECKPOINT_UNEXPECTED_UNTRACKED")
                continue
            parts=rec.split(b" ",8) if rec.startswith(b"1 ") else []
            if len(parts)!=9 or parts[2]!=b"N...":
                raise RepositoryError("CHECKPOINT_UNHANDLED_REPOSITORY_CONTENT")
            if parts[1]==b"M.": staged_tracked.append(parts[8])
            elif parts[1]==b"A.": staged_new.append(parts[8])
            else: raise RepositoryError("CHECKPOINT_UNHANDLED_REPOSITORY_CONTENT")
        if sorted(staged_tracked)!=sorted(tracked_paths) or sorted(staged_new)!=sorted(new_paths):
            raise RepositoryError("CHECKPOINT_STAGED_CONTENT_MISMATCH")
        expected_new=[x for x in expected["unexpected_untracked"] if x["path"] in owned_paths]
        if _staged_untracked(root,staged_new)!=expected_new:
            raise RepositoryError("CHECKPOINT_STAGED_CONTENT_MISMATCH")
        try:
            _run(root,"--no-pager","diff","--cached","--check","--")
        except RepositoryError as error:
            raise RepositoryError(f"CHECKPOINT_DIFF_CHECK_FAILED: {error}") from error
        tree=git(root,"write-tree")
        commit=_run(root,"commit-tree",tree,"-p",expected["head"],input_data=message.encode("utf-8")+b"\n").strip().decode("ascii")
        intent={"parent_head":expected["head"],"tree_sha":tree,"commit_sha":commit,"witness":expected}
        verify_checkpoint_commit(root,intent)
        return intent
    except Exception as original:
        if staged: _rollback_checkpoint(root,allowed,expected,original)
        raise

def advance_checkpoint(root:Path,allowed:list[str],intent:dict,ownership=None)->dict:
    """Advance HEAD to an already recorded exact commit, without invoking hooks."""
    verify_checkpoint_commit(root,intent)
    if git(root,"rev-parse","HEAD")!=intent["parent_head"]:
        raise RepositoryError("CHECKPOINT_HEAD_MISMATCH")
    _run(root,"update-ref","HEAD",intent["commit_sha"],intent["parent_head"])
    if git(root,"rev-parse","HEAD")!=intent["commit_sha"]:
        raise RepositoryError("CHECKPOINT_HEAD_MISMATCH")
    return verify_checkpoint_boundary(root,allowed,intent,ownership)

def verify_checkpoint_boundary(root:Path,allowed:list[str],intent:dict,ownership=None)->dict:
    """Verify the repository state after an exact checkpoint commit."""
    verify_checkpoint_commit(root,intent)
    ownership=ownership or {}
    expected_protected=ownership.get("protected_untracked",[])
    result=witness(root,allowed,ownership); empty=hashlib.sha256(b"").hexdigest()
    if (result["head"]!=intent["commit_sha"] or result["index_semantic_sha256"]!=empty or
        result["tracked_worktree_sha256"]!=empty or
        result["tracked_worktree_content_sha256"]!=empty or
        result["unexpected_untracked"] != expected_protected):
        raise RepositoryError("CHECKPOINT_POST_COMMIT_REPOSITORY_MISMATCH")
    return result

def checkpoint_commit(root:Path,allowed:list[str],expected:dict,message:str)->tuple[str,dict]:
    """Compatibility helper for repository-only callers; workflows record intent first."""
    intent=prepare_checkpoint(root,allowed,expected,message)
    try: result=advance_checkpoint(root,allowed,intent)
    except Exception as original:
        try: head=git(root,"rev-parse","HEAD")
        except RepositoryError as error: raise RepositoryError(f"CHECKPOINT_ROLLBACK_FAILED: {error}") from original
        if head==expected["head"]: _rollback_checkpoint(root,allowed,expected,original)
        raise
    return intent["commit_sha"],result
