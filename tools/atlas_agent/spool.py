from __future__ import annotations
import hashlib, os, uuid
from contextlib import contextmanager
from pathlib import Path
from .journal import Journal
try: import fcntl
except ImportError: fcntl=None
DIRS=("inbox","accepted","running/implementation","running/patch_review","running/state_audit","running/checkpoint","completed","rejected","interrupted","prompts","reports")
@contextmanager
def lock(path):
    if fcntl is None: raise RuntimeError("UNSUPPORTED_PLATFORM: W1 requires POSIX fcntl locking")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a+") as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(f.fileno(),fcntl.LOCK_UN)
def fsync_dir(path):
    fd=os.open(path,os.O_RDONLY); os.fsync(fd); os.close(fd)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def _sync_dirs(a,b):
    fsync_dir(a)
    if b.resolve()!=a.resolve(): fsync_dir(b)
def move_transaction(root,journal,source,destination,prompt_sha,logical_event,payload=None,hook=None):
    tx=str(uuid.uuid4()); data={"transaction_id":tx,"logical_event":logical_event,"source":str(source.relative_to(root)),"destination":str(destination.relative_to(root)),"prompt_sha256":prompt_sha}
    if payload: data.update(payload)
    journal.append("TRANSITION_PREPARED",**data)
    if hook: hook("prepared",data)
    destination.parent.mkdir(parents=True,exist_ok=True)
    os.replace(source,destination); _sync_dirs(source.parent,destination.parent)
    if hook: hook("renamed",data)
    terminal=dict(data); terminal.pop("logical_event",None)
    journal.append(logical_event,**terminal)
    return tx
def validate_spool(root,canonical_state):
    """Fail closed unless every owned prompt is in exactly its lifecycle location."""
    errors=[]; seen=set(); base=Path(root); expected_archives=set(); expected_reports=set()
    for g,rec in canonical_state.get("generations",{}).items():
        expected={"ACCEPTED":base/"accepted","RUNNING":base/"running"/rec["action"],"COMPLETED":base/"completed","INTERRUPTED":base/"interrupted"}.get(rec["status"])
        if expected is None: errors.append(f"g{g}: unknown lifecycle"); continue
        matches=[]
        for d in (base/"accepted",base/"running",base/"completed",base/"interrupted"):
            dirs=[d/rec["action"]] if d.name=="running" else [d]
            for dd in dirs:
                for p in dd.glob(f"g{int(g):06d}-*.txt"):
                    if p.is_file(): matches.append(p)
        canonical=f"g{int(g):06d}-{rec['prompt_sha256']}.txt"
        good=[p for p in matches if p.name==canonical and sha(p)==rec["prompt_sha256"] and p.parent==expected]
        if len(matches)!=1 or len(good)!=1: errors.append(f"g{g}: expected one valid file in {expected}")
        if good: seen.add(good[0])
        expected_archives.add(rec["prompt_sha256"]+".txt")
        result=rec.get("result")
        if result and result.get("report_path") is not None:
            report=result.get("report_path")
            if type(report) is not str or report.startswith("/") or "\\" in report or ".." in Path(report).parts or not report or Path(report).name in {".",".."}: errors.append(f"invalid report path g{g}")
            else: expected_reports.add(report.removeprefix("reports/"))
    for d in (base/"accepted",base/"completed",base/"interrupted"):
        for p in d.glob("*.txt"):
            if p not in seen: errors.append(f"orphan or corrupt spool file: {p.name}")
    for d in (base/"running").glob("*") if (base/"running").exists() else []:
        for p in d.glob("*.txt"):
            if p not in seen: errors.append(f"orphan or corrupt running file: {p.name}")
    for g,rec in canonical_state.get("generations",{}).items():
        archive=base/"prompts"/(rec["prompt_sha256"]+".txt")
        if rec["status"]!="REJECTED" and (not archive.exists() or sha(archive)!=rec["prompt_sha256"]): errors.append(f"prompt archive mismatch g{g}")
    archives={p.name for p in (base/"prompts").iterdir() if p.is_file()} if (base/"prompts").exists() else set()
    if archives!=expected_archives: errors.append("ORPHAN_PROMPT_ARCHIVE")
    actual_reports={str(p.relative_to(base/"reports")) for p in (base/"reports").rglob("*") if p.is_file()} if (base/"reports").exists() else set()
    if actual_reports!=expected_reports: errors.append("ORPHAN_REPORT")
    if errors: raise RuntimeError("SPOOL_CORRUPT: "+"; ".join(errors))
