from __future__ import annotations
import hashlib, json, os, uuid
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
    errors=[]; seen=set(); base=Path(root); expected_archives=set(); expected_reports=set(); expected_execution_files=set(); required_execution_files=set()
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
        execution=rec.get("execution")
        if execution:
            report_dir=Path(execution["report_dir"])
            if report_dir.is_absolute() or ".." in report_dir.parts or not str(report_dir).startswith("reports/executions/"): errors.append(f"invalid execution report dir g{g}")
            else:
                # actual_reports is relative to ``base/reports``; normalize the
                # journal's runtime-relative reports/... path before comparing.
                execution_rel=report_dir.relative_to("reports")
                for name in ("execution.json","stdout.log","stderr.log","result.json","usage.json"): expected_execution_files.add(str(execution_rel/name))
                required_execution_files.add(str(execution_rel/"execution.json"))
                if rec["status"]!="RUNNING": required_execution_files.update(str(execution_rel/name) for name in ("stdout.log","stderr.log","result.json","usage.json"))
                execution_file=base/"reports"/execution_rel/"execution.json"
                result_file=base/"reports"/execution_rel/"result.json"
                try: execution_data=json.loads(execution_file.read_text(encoding="utf-8"))
                except (OSError,UnicodeError,json.JSONDecodeError): execution_data=None; errors.append(f"invalid execution artifact g{g}")
                envelope=execution.get("permission_envelope")
                owner={"execution_id":execution.get("execution_id"),"generation":rec.get("generation"),"prompt_sha256":rec.get("prompt_sha256"),"action":rec.get("action")}
                if envelope is not None:
                    owner["permission_envelope"]=envelope
                if execution.get("owner_schema") is not None:
                    owner.update({"owner_schema":execution.get("owner_schema"),"policy_snapshot":execution.get("policy_snapshot")})
                elif envelope is None and execution.get("executor") in {"fake","codex"}:
                    errors.append(f"missing canonical permission envelope g{g}")
                if isinstance(execution_data,dict):
                    for key,value in owner.items():
                        if execution_data.get(key)!=value: errors.append(f"execution owner mismatch g{g}: {key}")
                    if execution_data.get("executor")!=execution.get("executor"): errors.append(f"execution metadata mismatch g{g}")
                    if envelope is not None and execution_data.get("permission_envelope")!=envelope: errors.append(f"execution permission envelope mismatch g{g}")
                try: result_data=json.loads(result_file.read_text(encoding="utf-8"))
                except (OSError,UnicodeError,json.JSONDecodeError): result_data=None
                if result_data is not None and rec["status"]!="RUNNING":
                    if not isinstance(result_data,dict): errors.append(f"result artifact invalid g{g}"); result_data=None
                if isinstance(result_data,dict) and rec["status"]!="RUNNING":
                    for key,value in owner.items():
                        if result_data.get(key)!=value: errors.append(f"result owner mismatch g{g}: {key}")
                    exit_code=result_data.get("exit_code"); outcome=result_data.get("outcome")
                    if outcome=="success" and exit_code!=0: errors.append(f"result success/exit mismatch g{g}")
                    if outcome=="failed" and exit_code==0: errors.append(f"result failed/exit mismatch g{g}")
                    if outcome=="timeout" and result_data.get("timed_out") is not True: errors.append(f"result timeout mismatch g{g}")
                    if rec["status"]=="COMPLETED" and (outcome!="success" or exit_code!=0): errors.append(f"completed result mismatch g{g}")
                if rec["status"]!="RUNNING" and isinstance(result_data,dict) and result_data.get("telemetry_status")=="failed":
                    required_execution_files.discard(str(execution_rel/"usage.json"))
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
    if not expected_reports.issubset(actual_reports): errors.append("MISSING_REPORT")
    if (actual_reports-expected_reports-expected_execution_files) or not actual_reports.issubset(expected_reports|expected_execution_files): errors.append("ORPHAN_REPORT")
    for required in required_execution_files:
        if not (base/"reports"/required).is_file(): errors.append("MISSING_EXECUTION_ARTIFACT")
    if errors: raise RuntimeError("SPOOL_CORRUPT: "+"; ".join(errors))
