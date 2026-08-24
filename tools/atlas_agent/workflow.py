from __future__ import annotations
import copy, hashlib, json, os, re, tempfile, uuid, tomllib
from dataclasses import replace
from pathlib import Path
from .model import Prompt
from .prompt import parse_prompt, PromptError
from .journal import Journal, JournalError
from .repository import find_root,runtime_path,witness
from .spool import DIRS,lock,move_transaction,sha,validate_spool,fsync_dir
from .executor import ExecutionSpec,ExecutorError,FakeExecutor,new_execution_id,utc_now,_write_json
from .codex_executor import CodexExecutor
from .telemetry import collect_usage
class WorkflowError(RuntimeError): pass
def replay_journal(events):
    state={"initialized":False,"last_seq":0,"generations":{},"parentage":{},"prompt_hashes":{},"lifecycle":{},"checkpoint_action":{},"repository_witnesses":[],"latest_repository_witness":None,"outstanding_transactions":{},"committed_transactions":[],"results":{},"reports":{}}
    for e in events:
        p=e["payload"]; state["last_seq"]=e["seq"]
        if e["event"]=="WORKFLOW_INITIALIZED": state["initialized"]=True; state["latest_repository_witness"]=p["witness"]; state["repository_witnesses"].append(p["witness"])
        elif e["event"]=="TRANSITION_PREPARED":
            tx=p["transaction_id"]
            if tx in state["outstanding_transactions"] or tx in state["committed_transactions"]: raise WorkflowError("JOURNAL_DUPLICATE_TRANSACTION")
            state["outstanding_transactions"][tx]=p
        elif e["event"] in {"PROMPT_ACCEPTED","PROMPT_REJECTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"}:
            tx=p["transaction_id"]; prepared=state["outstanding_transactions"].get(tx)
            if prepared is None: raise WorkflowError("JOURNAL_TERMINAL_WITHOUT_PREPARE")
            expected=dict(prepared); expected.pop("logical_event",None)
            if expected!=p or prepared["logical_event"]!=e["event"]: raise WorkflowError("JOURNAL_TERMINAL_PREPARE_MISMATCH")
            state["outstanding_transactions"].pop(tx); state["committed_transactions"].append(tx)
            if e["event"]=="PROMPT_REJECTED": continue
            if e["event"]=="PROMPT_ACCEPTED":
                if not state["initialized"]: raise WorkflowError("JOURNAL_INITIALIZATION_ORDER")
                if type(p.get("generation")) is not int or p["generation"] != max([int(x) for x in state["generations"]],default=0)+1: raise WorkflowError("JOURNAL_GENERATION_SEQUENCE")
                if (p["generation"]==1 and p["parent"]!="genesis") or (p["generation"]>1 and p["parent"]!=p["generation"]-1): raise WorkflowError("JOURNAL_PARENTAGE")
                g=str(p["generation"]); state["generations"][g]={"generation":p["generation"],"parent":p["parent"],"prompt_sha256":p["prompt_sha256"],"checkpoint":p["checkpoint"],"action":p["action"],"session_mode":p.get("session_mode"),"expected_head":p.get("expected_head"),"witness":p["witness"],"status":"ACCEPTED"}; state["parentage"][g]=p["parent"]; state["prompt_hashes"][g]=p["prompt_sha256"]; state["lifecycle"][g]="ACCEPTED"; state["checkpoint_action"][g]={"checkpoint":p["checkpoint"],"action":p["action"]}; state["latest_repository_witness"]=p["witness"]; continue
            if e["event"]=="RUN_STARTED":
                g=str(p["generation"]); rec=state["generations"].get(g)
                if not rec or rec["status"]!="ACCEPTED" or rec["prompt_sha256"]!=p["prompt_sha256"] or rec["action"]!=p["action"]: raise WorkflowError("JOURNAL_LIFECYCLE")
                rec["status"]="RUNNING"
                if "execution" in p: rec["execution"]=p["execution"]
                state["lifecycle"][g]="RUNNING"; continue
            if e["event"] in {"RUN_COMPLETED","RUN_INTERRUPTED"}:
                g=str(p["generation"]); rec=state["generations"].get(g)
                if not rec or rec["status"]!="RUNNING" or rec["prompt_sha256"]!=p["prompt_sha256"] or rec["action"]!=p["action"]: raise WorkflowError("JOURNAL_LIFECYCLE")
                status="COMPLETED" if e["event"]=="RUN_COMPLETED" else "INTERRUPTED"; rec["status"]=status; state["lifecycle"][g]=status
                if e["event"]=="RUN_COMPLETED": rec["result"]=p["result"]; state["results"][g]=p["result"]
                if p.get("witness"): state["latest_repository_witness"]=p["witness"]
                continue
    return state
def projection_equal(a,b): return a==b
def witness_matches_policy(current, expected, action, running=False):
    if running and action=="implementation":
        return all(current.get(k)==expected.get(k) for k in ("head","index_semantic_sha256","unexpected_untracked"))
    return current==expected
class Workflow:
    def __init__(self,start="."):
        self.root=find_root(Path(start).resolve()); self.base=runtime_path(self.root); self.journal=Journal(self.base/"events.jsonl"); self.config=self.root/"atlas-agent.toml"; self.allowed=self._config()["allowed_untracked"]
    def _config(self):
        if not self.config.exists(): raise WorkflowError("CONFIG_REQUIRED")
        try: data=tomllib.loads(self.config.read_text(encoding="utf-8"))
        except (OSError,UnicodeError,tomllib.TOMLDecodeError) as e: raise WorkflowError(f"BAD_CONFIG: {e}")
        if set(data)!={"schema","allowed_untracked"} or data["schema"]!="atlas-agent-project/1" or type(data["allowed_untracked"]) is not list: raise WorkflowError("BAD_CONFIG_SCHEMA")
        for x in data["allowed_untracked"]:
            if type(x) is not str or not x.endswith("/") or "\\" in x or x.startswith("/") or x.startswith("./") or "/../" in "/"+x or x.startswith("../") or "//" in x or x=="./": raise WorkflowError("BAD_ALLOWED_UNTRACKED")
            if str(Path(x[:-1]))!=x[:-1]: raise WorkflowError("BAD_ALLOWED_UNTRACKED")
        return data
    def _state_file(self): return self.base/"state.json"
    def _state(self):
        if not self._state_file().exists(): raise WorkflowError("STATE_MISSING: run rebuild-state")
        try: return json.loads(self._state_file().read_text(encoding="utf-8"))
        except Exception as e: raise WorkflowError(f"STATE_INVALID: {e}")
    def _save(self,state):
        self.base.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix="state-",dir=self.base); os.close(fd); p=Path(tmp)
        try:
            with p.open("w",encoding="utf-8") as f: json.dump(state,f,sort_keys=True,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
            os.replace(p,self._state_file()); fsync_dir(self.base)
        finally:
            if p.exists(): p.unlink()
    def _replayed(self):
        events=self.journal.read(); s=replay_journal(events)
        if s["outstanding_transactions"]: raise WorkflowError("INCOMPLETE_TRANSACTION: run recover")
        return events,s
    def _preflight(self,require_state=True):
        events,s=self._replayed()
        if require_state:
            try: current=self._state()
            except WorkflowError: raise
            if not projection_equal(current,s): raise WorkflowError("STATE_STALE_OR_TAMPERED: run rebuild-state")
        validate_spool(self.base,s)
        return events,s
    def init(self):
        with lock(self.base/"lock"):
            if self.journal.path.exists(): raise WorkflowError("workflow already initialized")
            self.base.mkdir(parents=True,exist_ok=True)
            for d in DIRS: (self.base/d).mkdir(parents=True,exist_ok=True)
            w=witness(self.root,self.allowed); self.journal.append("WORKFLOW_INITIALIZED",repository_root=str(self.root),head=w["head"],branch=w["branch"],witness=w); self._save(replay_journal(self.journal.read()))
    def rebuild(self):
        with lock(self.base/"lock"):
            events,s=self._replayed()
            if not s["initialized"]: raise WorkflowError("WORKFLOW_NOT_INITIALIZED")
            validate_spool(self.base,s); self._save(s); return s
    def _archive(self,raw,digest):
        p=self.base/"prompts"/(digest+".txt")
        if p.exists() and sha(p)!=digest: raise WorkflowError("PROMPT_ARCHIVE_CORRUPT")
        if not p.exists():
            with p.open("wb") as f: f.write(raw); f.flush(); os.fsync(f.fileno())
            fsync_dir(p.parent)
    def ingest(self):
        with lock(self.base/"lock"):
            _,state=self._preflight(); current=witness(self.root,self.allowed); expected=state["latest_repository_witness"]
            files=sorted(p for p in (self.base/"inbox").iterdir() if p.is_file())
            parsed=[]
            for source in files:
                raw=source.read_bytes(); digest=hashlib.sha256(raw).hexdigest(); self.journal.append("PROMPT_RECEIVED",prompt_sha256=digest,source=source.name)
                try:
                    p=parse_prompt(raw); parsed.append((p,raw,digest,source))
                except PromptError as e: self._reject(source,digest,e.code,str(e))
            parsed.sort(key=lambda x:(x[0].generation,x[2],x[3].name))
            for p,raw,digest,source in parsed:
                try:
                    old=state["generations"].get(str(p.generation))
                    if old: raise WorkflowError("DUPLICATE_PROMPT" if old["prompt_sha256"]==digest else "GENERATION_COLLISION")
                    if p.generation!=max([int(x) for x in state["generations"]],default=0)+1: raise WorkflowError("BAD_GENERATION")
                    if p.parent!="genesis" and str(p.parent) not in state["generations"]: raise WorkflowError("UNKNOWN_PARENT")
                    if p.generation==1 and p.parent!="genesis": raise WorkflowError("BAD_PARENT")
                    if p.generation>1 and p.parent!=p.generation-1: raise WorkflowError("BAD_PARENT")
                    if p.expected_head!=current["head"]: raise WorkflowError("HEAD_MISMATCH")
                    if current!=expected: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH")
                    self._archive(raw,digest); payload={"generation":p.generation,"parent":p.parent,"prompt_sha256":digest,"checkpoint":p.checkpoint,"action":p.action,"session_mode":p.session_mode,"expected_head":p.expected_head,"witness":current}
                    move_transaction(self.base,self.journal,source,self.base/"accepted"/p.canonical_name,digest,"PROMPT_ACCEPTED",payload)
                    state=replay_journal(self.journal.read())
                except (PromptError,WorkflowError) as e: self._reject(source,digest,getattr(e,"code",str(e)),str(e)); state=replay_journal(self.journal.read())
            self._save(state); validate_spool(self.base,state); return state
    def _reject(self,source,digest,code,message):
        dest=self.base/"rejected"/(digest[:12]+".txt"); move_transaction(self.base,self.journal,source,dest,digest,"PROMPT_REJECTED",{"reason_code":code,"reason":message}); (dest.with_name(dest.name+".reason.json")).write_text(json.dumps({"code":code,"message":message})+"\n",encoding="utf-8")
    def _record(self,g):
        s=self._preflight()[1]; x=s["generations"].get(str(g));
        if not x: raise WorkflowError("UNKNOWN_GENERATION")
        return s,x
    def _find(self,folder,g,digest):
        hits=[p for p in folder.glob(f"g{g:06d}-*.txt") if p.is_file()]
        if len(hits)!=1 or sha(hits[0])!=digest: raise WorkflowError("SPOOL_CORRUPT")
        return hits[0]
    def start_run(self,generation,hook=None,execution=None):
        with lock(self.base/"lock"):
            s,x=self._record(generation)
            if x["status"]!="ACCEPTED": raise WorkflowError("generation is not accepted")
            if witness(self.root,self.allowed)!=x["witness"]: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH")
            if execution is not None:
                execution_id=execution.get("execution_id")
                report_dir=Path(execution.get("report_dir",""))
                if type(execution_id) is not str or not execution_id or report_dir.is_absolute() or ".." in report_dir.parts or not str(report_dir).startswith("reports/executions/"):
                    raise WorkflowError("BAD_EXECUTION_METADATA")
                if any(r.get("execution",{}).get("execution_id")==execution_id for r in s["generations"].values()):
                    raise WorkflowError("EXECUTION_ID_COLLISION")
                if (self.base/report_dir).exists(): raise WorkflowError("EXECUTION_REPORT_COLLISION")
            src=self._find(self.base/"accepted",generation,x["prompt_sha256"]); payload={"generation":generation,"action":x["action"]}
            if execution is not None: payload["execution"]=execution
            move_transaction(self.base,self.journal,src,self.base/"running"/x["action"]/src.name,x["prompt_sha256"],"RUN_STARTED",payload,hook); s=replay_journal(self.journal.read()); self._save(s); return s
    def complete_run(self,generation,result,hook=None):
        with lock(self.base/"lock"):
            s,x=self._record(generation)
            if x["status"]!="RUNNING": raise WorkflowError("generation is not running")
            r=result if isinstance(result,dict) else result.as_dict()
            if r.get("generation")!=generation or r.get("prompt_sha256")!=x["prompt_sha256"] or r.get("action")!=x["action"]: raise WorkflowError("RESULT_PROMPT_MISMATCH")
            owner=x.get("execution")
            if owner is not None:
                executor_result=r.get("executor_result")
                if not isinstance(executor_result,dict) or executor_result.get("execution_id")!=owner.get("execution_id"):
                    raise WorkflowError("RESULT_EXECUTION_MISMATCH")
            before=x["witness"]; now=witness(self.root,self.allowed); violation=not witness_matches_policy(now,before,x["action"],running=True)
            src=self._find(self.base/"running"/x["action"],generation,x["prompt_sha256"])
            if violation:
                payload={"generation":generation,"action":x["action"],"reason":"REPOSITORY_POLICY_VIOLATION"};
                if x.get("execution") is not None: payload["execution"]=x["execution"]
                move_transaction(self.base,self.journal,src,self.base/"interrupted"/src.name,x["prompt_sha256"],"RUN_INTERRUPTED",payload,hook); s=replay_journal(self.journal.read()); self._save(s); raise WorkflowError("REPOSITORY_POLICY_VIOLATION")
            payload={"generation":generation,"action":x["action"],"result":r,"witness":now};
            if x.get("execution") is not None: payload["execution"]=x["execution"]
            move_transaction(self.base,self.journal,src,self.base/"completed"/src.name,x["prompt_sha256"],"RUN_COMPLETED",payload,hook); s=replay_journal(self.journal.read()); self._save(s); return s
    def interrupt_run(self,generation,reason):
        with lock(self.base/"lock"):
            s,x=self._record(generation)
            if x["status"]!="RUNNING": raise WorkflowError("generation is not running")
            src=self._find(self.base/"running"/x["action"],generation,x["prompt_sha256"]); payload={"generation":generation,"action":x["action"],"reason":reason};
            if x.get("execution") is not None: payload["execution"]=x["execution"]
            move_transaction(self.base,self.journal,src,self.base/"interrupted"/src.name,x["prompt_sha256"],"RUN_INTERRUPTED",payload); s=replay_journal(self.journal.read()); self._save(s); return s
    def execute(self,generation,executor=None):
        """Explicitly execute one accepted generation through W1 lifecycle."""
        s,x=self._record(generation)
        if x["status"]!="ACCEPTED": raise WorkflowError("generation is not accepted")
        executor=executor or CodexExecutor()
        execution_id=new_execution_id(); report_dir=self.base/"reports"/"executions"/execution_id
        accepted=self._find(self.base/"accepted",generation,x["prompt_sha256"])
        spec=ExecutionSpec(generation,x["prompt_sha256"],x["action"],accepted,self.root,execution_id,report_dir,self.base,x.get("checkpoint"))
        prepared=executor.prepare_execution(spec)
        metadata={"execution_id":execution_id,"executor":prepared.executor,"started_at":utc_now(),"pid":None,"report_dir":str(report_dir.relative_to(self.base)),"permission_envelope":prepared.permission_envelope}
        self.start_run(generation,execution=metadata)
        running= self.base/"running"/x["action"]/accepted.name
        started=True; telemetry_failed=False
        try:
            report_dir.parent.mkdir(parents=True,exist_ok=True)
            report_dir.mkdir(parents=False,exist_ok=False)
            _write_json(report_dir/"execution.json",{**metadata,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"command":list(prepared.command),"version":prepared.version,"permission_envelope":prepared.permission_envelope})
            prepared=getattr(executor,"post_start_prepare",lambda value: value)(prepared)
            _write_json(report_dir/"execution.json",{**metadata,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"command":list(prepared.command),"version":prepared.version,"permission_envelope":prepared.permission_envelope})
            prepared=replace(prepared,spec=replace(prepared.spec,prompt_path=running))
            result=executor.run_execution(prepared)
            result_payload={**result.__dict__,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"]}
            _write_json(report_dir/"result.json",result_payload)
            try:
                collect_usage(prepared.spec,result,report_dir,requested_model=getattr(executor,"model",None),requested_reasoning=getattr(executor,"reasoning_effort",None))
            except OSError as error:
                telemetry_failed=True
                _write_json(report_dir/"result.json",{**result_payload,"telemetry_status":"failed","telemetry_error":str(error)})
                self.interrupt_run(generation,"TELEMETRY_WRITE_FAILURE")
                started=False
                raise WorkflowError(f"TELEMETRY_WRITE_FAILURE: {error}") from error
            if result.timed_out:
                self.interrupt_run(generation,"EXECUTOR_TIMEOUT")
                raise WorkflowError("EXECUTOR_TIMEOUT")
            if result.exit_code != 0:
                self.interrupt_run(generation,f"EXECUTOR_EXIT_{result.exit_code}")
                raise WorkflowError(f"EXECUTOR_EXIT_{result.exit_code}")
            envelope={"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"outcome":result.outcome,"classification":"executor_process","report_path":result.report_path,"executor_result":result.__dict__}
            return self.complete_run(generation,envelope)
        except Exception as error:
            if isinstance(error, WorkflowError) and (str(error).startswith("EXECUTOR_EXIT_") or str(error)=="EXECUTOR_TIMEOUT"): raise
            stdout=report_dir/"stdout.log"; stderr=report_dir/"stderr.log"
            if started:
                try: self.interrupt_run(generation,f"EXECUTOR_FAILURE: {error}")
                finally: started=False
            if not telemetry_failed:
                try: collect_usage(prepared.spec,type("Result",(),{"session_id":None,"version":prepared.version})(),report_dir,requested_model=getattr(executor,"model",None))
                except OSError: pass
                try:
                    stdout.touch(exist_ok=True); stderr.touch(exist_ok=True)
                    _write_json(report_dir/"result.json",{"execution_id":execution_id,"executor":prepared.executor,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"outcome":"exception","error":str(error),"permission_envelope":prepared.permission_envelope,"permission_observation_status":"unavailable","permission_failures":None})
                except OSError: pass
            raise WorkflowError(f"EXECUTOR_FAILURE: {error}") from error
    def recover(self):
        with lock(self.base/"lock"):
            events=self.journal.read()
            s=replay_journal(events)
            if s["outstanding_transactions"]:
                first_prepare=min(p["_seq"] if "_seq" in p else next(e["seq"] for e in events if e["event"]=="TRANSITION_PREPARED" and e["payload"]["transaction_id"]==tx) for tx,p in s["outstanding_transactions"].items())
                prior=replay_journal([e for e in events if e["seq"]<first_prepare])
            else: prior=copy.deepcopy(s)
            if not self._state_file().exists() or self._state()!=prior: raise WorkflowError("STATE_STALE_OR_TAMPERED: run rebuild-state")
            if not s["outstanding_transactions"]:
                validate_spool(self.base,s)
                return s
            for tx,p in list(s["outstanding_transactions"].items()):
                src=self.base/p["source"]; dst=self.base/p["destination"]
                se=src.exists(); de=dst.exists()
                if se and sha(src)!=p["prompt_sha256"]: raise WorkflowError("RECOVERY_SOURCE_HASH_MISMATCH")
                if de and sha(dst)!=p["prompt_sha256"]: raise WorkflowError("RECOVERY_DESTINATION_HASH_MISMATCH")
                if se and de: raise WorkflowError("RECOVERY_AMBIGUOUS")
                if not se and not de: raise WorkflowError("RECOVERY_MISSING_BOTH")
                if se: os.replace(src,dst); fsync_dir(src.parent); fsync_dir(dst.parent)
                terminal=dict(p); terminal.pop("logical_event",None); self.journal.append(p["logical_event"],**terminal)
            s=replay_journal(self.journal.read()); validate_spool(self.base,s); self._save(s); return s
