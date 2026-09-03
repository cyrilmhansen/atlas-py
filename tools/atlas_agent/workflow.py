from __future__ import annotations
import hashlib, json, os, re, tempfile, uuid, tomllib
from dataclasses import replace
from pathlib import Path
from .model import Prompt
from .prompt import parse_prompt, PromptError
from .journal import Journal, JournalError, encode_context_supplement, canonical_context_identifier, canonical_execution_result
from .repository import RepositoryError,advance_checkpoint,prepare_checkpoint,rollback_checkpoint,verify_checkpoint_boundary,find_root,runtime_path,witness
from .spool import DIRS,lock,move_transaction,sha,validate_spool,fsync_dir
from .executor import ExecutionSpec,ExecutorError,FakeExecutor,new_execution_id,utc_now,_write_json
from .codex_executor import CodexExecutor
from .bubblewrap import AtlasBubblewrapExecutor
from .telemetry import USAGE_SCHEMA,collect_usage,load_presentation_usage
from .policy import PolicyError, load_policy, policy_config_sha256, resolve_policy, validate_snapshot
class WorkflowError(RuntimeError): pass
class _RunTerminalError(WorkflowError):
    """A meaningful failure that already durably ended the run."""

SESSION_VALIDATION_ERRORS=frozenset({"FRESHNESS_UNVERIFIED","FRESHNESS_VIOLATION","REUSE_THREAD_UNVERIFIED","REUSE_THREAD_MISMATCH","OBSERVED_MODEL_MISMATCH","OBSERVED_REASONING_MISMATCH","REUSE_SESSION_UNAVAILABLE"})
SUPPLEMENT_MAX_BYTES=4096
_SAFE_CONTEXT_VALUE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")

def _context_value(value):
    """Return a bounded line-safe identifier, or None for optional metadata."""
    return canonical_context_identifier(value)
def replay_journal(events):
    state={"initialized":False,"last_seq":0,"generations":{},"parentage":{},"prompt_hashes":{},"lifecycle":{},"checkpoint_action":{},"repository_witnesses":[],"latest_repository_witness":None,"outstanding_transactions":{},"committed_transactions":[],"results":{},"reports":{}}
    for e in events:
        p=e["payload"]; state["last_seq"]=e["seq"]
        if e["event"]=="WORKFLOW_INITIALIZED":
            state["initialized"]=True
            if p.get("validation_epoch",1) >= 2: state["validation_epoch"]=p["validation_epoch"]
            state["latest_repository_witness"]=p["witness"]; state["repository_witnesses"].append(p["witness"])
            initial=p["witness"].get("unexpected_untracked",[])
            if initial or p.get("validation_epoch",1) >= 2: state["protected_untracked"]=initial
            if p.get("validation_epoch",1) >= 2: state["patch_owned_untracked"]=[]
        elif e["event"]=="CHECKPOINT_INTENT":
            g=str(p["generation"]); rec=state["generations"].get(g)
            outstanding=state.setdefault("outstanding_checkpoints",{})
            if not rec or rec["status"]!="ACCEPTED" or rec["action"]!="checkpoint" or rec["prompt_sha256"]!=p["prompt_sha256"] or g in outstanding: raise WorkflowError("JOURNAL_CHECKPOINT_INTENT")
            if p["parent_head"]!=rec["witness"]["head"] or p["witness"]!=rec["witness"]: raise WorkflowError("JOURNAL_CHECKPOINT_INTENT_MISMATCH")
            outstanding[g]=p
        elif e["event"]=="CHECKPOINT_ABORTED":
            g=str(p["generation"]); intent=state.get("outstanding_checkpoints",{}).get(g); rec=state["generations"].get(g)
            if not intent or not rec or rec["status"]!="ACCEPTED" or p["prompt_sha256"]!=intent["prompt_sha256"] or p["commit_sha"]!=intent["commit_sha"]: raise WorkflowError("JOURNAL_CHECKPOINT_ABORT")
            state["outstanding_checkpoints"].pop(g)
            if not state["outstanding_checkpoints"]: state.pop("outstanding_checkpoints")
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
                g=str(p["generation"]); rec={"generation":p["generation"],"parent":p["parent"],"prompt_sha256":p["prompt_sha256"],"checkpoint":p["checkpoint"],"action":p["action"],"session_mode":p.get("session_mode"),"expected_head":p.get("expected_head"),"witness":p["witness"],"status":"ACCEPTED"}
                for key in ("prompt_schema", "network_access", "reuse_execution_id"):
                    if key in p: rec[key]=p[key]
                state["generations"][g]=rec; state["parentage"][g]=p["parent"]; state["prompt_hashes"][g]=p["prompt_sha256"]; state["lifecycle"][g]="ACCEPTED"; state["checkpoint_action"][g]={"checkpoint":p["checkpoint"],"action":p["action"]}; state["latest_repository_witness"]=p["witness"]; continue
            if e["event"]=="RUN_STARTED":
                g=str(p["generation"]); rec=state["generations"].get(g)
                if not rec or rec["status"]!="ACCEPTED" or rec["prompt_sha256"]!=p["prompt_sha256"] or rec["action"]!=p["action"]: raise WorkflowError("JOURNAL_LIFECYCLE")
                if (rec.get("prompt_schema") == "atlas-agent-prompt/2" and rec["action"] != "checkpoint"
                        and "witness" not in p and "witness" in prepared):
                    raise WorkflowError("RUN_STARTED witness required")
                if "witness" in p and p["witness"] != rec["witness"]:
                    raise WorkflowError("JOURNAL_START_WITNESS_MISMATCH")
                rec["status"]="RUNNING"
                if "witness" in p: rec["start_witness"]=p["witness"]
                if "execution" in p: rec["execution"]=p["execution"]
                state["lifecycle"][g]="RUNNING"; continue
            if e["event"] in {"RUN_COMPLETED","RUN_INTERRUPTED"}:
                g=str(p["generation"]); rec=state["generations"].get(g)
                if not rec or rec["status"]!="RUNNING" or rec["prompt_sha256"]!=p["prompt_sha256"] or rec["action"]!=p["action"]: raise WorkflowError("JOURNAL_LIFECYCLE")
                if rec.get("execution") is not None and p.get("execution") != rec["execution"]:
                    raise WorkflowError("JOURNAL_TERMINAL_EXECUTION_MISMATCH")
                status="COMPLETED" if e["event"]=="RUN_COMPLETED" else "INTERRUPTED"; rec["status"]=status; state["lifecycle"][g]=status
                if e["event"]=="RUN_COMPLETED":
                    intent=state.get("outstanding_checkpoints",{}).get(g)
                    if rec["action"]=="checkpoint" and (not intent or p["result"].get("commit_sha")!=intent["commit_sha"] or p["witness"]["head"]!=intent["commit_sha"]): raise WorkflowError("JOURNAL_CHECKPOINT_COMPLETION_MISMATCH")
                    if intent:
                        state["outstanding_checkpoints"].pop(g)
                        if not state["outstanding_checkpoints"]: state.pop("outstanding_checkpoints")
                    rec["result"]=p["result"]; state["results"][g]=p["result"]
                    if rec["action"] == "checkpoint":
                        if "patch_owned_untracked" in state: state["patch_owned_untracked"]=[]
                    elif rec["action"] == "implementation":
                        existing=set(state.get("patch_owned_untracked",[]))
                        protected={x["path"] for x in state.get("protected_untracked",[])}
                        start={x["path"] for x in rec.get("start_witness",rec["witness"]).get("unexpected_untracked",[])}
                        terminal={x["path"] for x in p["witness"].get("unexpected_untracked",[])}
                        derived=terminal-start-protected-existing
                        if rec.get("prompt_schema") == "atlas-agent-prompt/2" and "acquired_untracked" not in p:
                            raise WorkflowError("JOURNAL_OWNERSHIP_DELTA")
                        acquired=set(p.get("acquired_untracked", sorted(derived)))
                        if acquired != derived or acquired & protected or acquired & existing:
                            raise WorkflowError("JOURNAL_OWNERSHIP_DELTA")
                        if existing or acquired or "patch_owned_untracked" in state:
                            state["patch_owned_untracked"]=sorted(existing | acquired)
                elif "result" in p:
                    rec["result"]=p["result"]; state["results"][g]=p["result"]
                if "executor_result" in p: rec["execution_result"]=p["executor_result"]
                if p.get("witness"): state["latest_repository_witness"]=p["witness"]
                continue
    return state
def projection_equal(a,b): return a==b
def witness_matches_policy(current, expected, action, running=False, ownership=None):
    if running and action=="implementation":
        stable=all(current.get(k)==expected.get(k) for k in ("head","index_semantic_sha256"))
        ownership=ownership or {}
        protected={x["path"]:x for x in ownership.get("protected_untracked",[])}
        current_records={x["path"]:x for x in current.get("unexpected_untracked",[])}
        if any(current_records.get(path)!=record for path,record in protected.items()): return False
        owned=set(ownership.get("patch_owned_untracked",[]))
        required=set(x["path"] for x in expected.get("unexpected_untracked",[]))-owned-set(protected)
        return stable and required <= set(current_records)
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
    def _publish_execution_artifact(self,path,value):
        """Atomically publish mandatory execution-owner metadata.

        Stage outside reports so spool validation cannot mistake the private
        file for a canonical report artifact.
        """
        fd,tmp=tempfile.mkstemp(prefix="execution-artifact-",dir=self.base); os.close(fd); staged=Path(tmp)
        try:
            with staged.open("w",encoding="utf-8") as f:
                json.dump(value,f,sort_keys=True,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
            os.replace(staged,path); fsync_dir(path.parent)
        finally:
            if staged.exists(): staged.unlink()
    def _execution_artifact(self,transaction):
        return {**transaction["execution"],"generation":transaction["generation"],"prompt_sha256":transaction["prompt_sha256"],"action":transaction["action"]}
    def _publish_missing_execution_file(self,path,data):
        """Publish or verify an exact journal-derived recovery artifact."""
        def accept_existing():
            try:
                current=path.read_bytes()
            except OSError as error:
                raise WorkflowError("RECOVERY_FALLBACK_ARTIFACT_CONFLICT") from error
            if current!=data:
                raise WorkflowError("RECOVERY_FALLBACK_ARTIFACT_CONFLICT")
            # A prior recovery may have crashed after publication but before
            # making the directory entry durable.  Retrying must close that
            # durability gap even though the bytes are already canonical.
            fsync_dir(path.parent)
        if path.exists() or path.is_symlink():
            accept_existing()
            return
        fd,tmp=tempfile.mkstemp(prefix="recovery-artifact-",dir=self.base); staged=Path(tmp)
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            try:
                # Linking a fully synced private inode publishes atomically
                # without ever replacing an artifact that raced into place.
                os.link(staged,path)
            except FileExistsError:
                accept_existing()
                return
            fsync_dir(path.parent)
        finally:
            if staged.exists(): staged.unlink()
    def _prepare_execution_publication(self,transaction,artifact=None):
        """Publish mandatory execution-owner metadata."""
        execution=transaction["execution"]
        report_rel=Path(execution.get("report_dir",""))
        if report_rel.is_absolute() or ".." in report_rel.parts or not str(report_rel).startswith("reports/executions/"):
            raise WorkflowError("BAD_EXECUTION_METADATA")
        report_dir=self.base/report_rel
        if report_dir.is_symlink() or report_dir.parent.is_symlink():
            raise WorkflowError("EXECUTION_REPORT_COLLISION")
        parent_created=not report_dir.parent.exists()
        report_dir.parent.mkdir(parents=True,exist_ok=True)
        if parent_created: fsync_dir(report_dir.parent.parent)
        if report_dir.exists():
            if not report_dir.is_dir(): raise WorkflowError("EXECUTION_REPORT_COLLISION")
        else:
            report_dir.mkdir(parents=False,exist_ok=False)
            fsync_dir(report_dir.parent)
        path=report_dir/"execution.json"
        expected=self._execution_artifact(transaction)
        children=list(report_dir.iterdir())
        if path.exists():
            if path.is_symlink() or any(child.name!="execution.json" for child in children):
                raise WorkflowError("RECOVERY_EXECUTION_ARTIFACT_CONFLICT")
            try: current=json.loads(path.read_text(encoding="utf-8"))
            except (OSError,UnicodeError,json.JSONDecodeError) as error:
                raise WorkflowError("RECOVERY_EXECUTION_ARTIFACT_CONFLICT") from error
            if not isinstance(current,dict) or any(current.get(key)!=value for key,value in expected.items()):
                raise WorkflowError("RECOVERY_EXECUTION_ARTIFACT_CONFLICT")
            fsync_dir(report_dir); fsync_dir(report_dir.parent)
        else:
            if children: raise WorkflowError("RECOVERY_EXECUTION_ARTIFACT_CONFLICT")
            self._publish_execution_artifact(path,artifact or expected)
    def _prepare_context_publication(self,transaction):
        """Publish informational context after authoritative owner handling."""
        execution=transaction["execution"]
        supplement=transaction.get("context_supplement")
        context_path_value=execution.get("context_path")
        effective_path_value=execution.get("effective_prompt_path")
        if supplement is not None:
            context_path=self.base / context_path_value
            effective_path=self.base / effective_path_value
            context=supplement.encode("utf-8")
            accepted=self.base/transaction["source"]
            if not accepted.is_file(): accepted=self.base/transaction["destination"]
            prompt_bytes=accepted.read_bytes()
            self._publish_context(context_path,context)
            self._publish_context(effective_path,prompt_bytes+context)

    def _validate_authoritative_provenance(self, transaction, state, prompt_bytes=None):
        """Validate journaled context before trusting or committing RUN_STARTED."""
        supplement=transaction.get("context_supplement")
        execution=transaction.get("execution")
        if supplement is None or not isinstance(execution,dict): return
        if state.get("validation_epoch", 1) >= 2 and "execution_input_sha256" in execution and execution.get("execution_input_sha256") != execution.get("effective_prompt_sha256"):
            raise WorkflowError("EXECUTION_INPUT_HASH_MISMATCH")
        context=supplement.encode("utf-8")
        if prompt_bytes is None:
            source=self.base/transaction["source"]
            destination=self.base/transaction["destination"]
            prompt_path=source if source.is_file() else destination
            if prompt_path.is_file():
                prompt_bytes=prompt_path.read_bytes()
            else:
                archive=self.base/"prompts"/(transaction["prompt_sha256"]+".txt")
                if not archive.is_file() or sha(archive)!=transaction["prompt_sha256"]:
                    raise WorkflowError("PROMPT_ARCHIVE_CORRUPT")
                prompt_bytes=archive.read_bytes()
        if hashlib.sha256(context).hexdigest()!=execution.get("context_sha256"):
            raise WorkflowError("EXECUTION_CONTEXT_HASH_MISMATCH")
        if hashlib.sha256(prompt_bytes+context).hexdigest()!=execution.get("effective_prompt_sha256"):
            raise WorkflowError("EXECUTION_CONTEXT_HASH_MISMATCH")
        expected,_=self._parent_context(state,transaction["generation"])
        if expected != context:
            raise WorkflowError("EXECUTION_CONTEXT_SEMANTICS_MISMATCH")
    def _replayed(self):
        try:
            events=self.journal.read(); s=replay_journal(events)
        except JournalError as error:
            raise WorkflowError(str(error)) from error
        if s["outstanding_transactions"] or s.get("outstanding_checkpoints"): raise WorkflowError("INCOMPLETE_TRANSACTION: run recover")
        return events,s
    def _validate_historical_provenance(self, events):
        for event in events:
            if event["event"] == "RUN_STARTED" and "context_supplement" in event["payload"]:
                before=replay_journal([e for e in events if e["seq"] < event["seq"]])
                self._validate_authoritative_provenance(event["payload"],before)
        for event in events:
            if event["event"] in {"RUN_COMPLETED", "RUN_INTERRUPTED"}:
                before=replay_journal([e for e in events if e["seq"] < event["seq"]])
                self._validate_terminal_transition(event["event"], event["payload"], before)

    def _validate_terminal_transition(self, event, payload, state):
        record=state["generations"].get(str(payload.get("generation")))
        execution=record.get("execution") if isinstance(record,dict) else None
        if not isinstance(execution,dict) or state.get("validation_epoch", 1) < 2:
            return
        if payload.get("execution") != execution:
            raise WorkflowError("TERMINAL_EXECUTION_MISMATCH")
        if execution.get("execution_input_sha256") != execution.get("effective_prompt_sha256"):
            raise WorkflowError("EXECUTION_INPUT_HASH_MISMATCH")
        result=payload.get("result")
        if not isinstance(result,dict):
            raise WorkflowError("TERMINAL_PROVENANCE_MISSING")
        observed=result.get("executor_result")
        if event == "RUN_COMPLETED" and (not isinstance(observed,dict) or observed.get("execution_input_sha256") != execution.get("execution_input_sha256")):
            raise WorkflowError("EXECUTION_INPUT_HASH_MISMATCH")
        descriptor=result.get("report_provenance")
        if not isinstance(descriptor,dict) or descriptor.get("status") not in {"available","unavailable"}:
            raise WorkflowError("TERMINAL_REPORT_PROVENANCE_MISSING")
        if descriptor["status"]=="available" and (set(descriptor)!={"status","report_sha256"} or not isinstance(descriptor.get("report_sha256"),str) or not re.fullmatch(r"[0-9a-f]{64}",descriptor["report_sha256"])):
            raise WorkflowError("TERMINAL_REPORT_PROVENANCE_INVALID")
        if descriptor["status"]=="unavailable" and set(descriptor)!={"status"}:
            raise WorkflowError("TERMINAL_REPORT_PROVENANCE_INVALID")
    def _preflight(self,require_state=True):
        events,s=self._replayed()
        if require_state:
            try: current=self._state()
            except WorkflowError: raise
            if not projection_equal(current,s): raise WorkflowError("STATE_STALE_OR_TAMPERED: run rebuild-state")
        # Parent semantics are historical: a later execution may legitimately
        # change the parent's terminal/report state.
        self._validate_historical_provenance(events)
        validate_spool(self.base,s)
        return events,s

    def _stage_execution_input(self, data, expected_hash):
        """Create an ephemeral, private executor source from verified bytes."""
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise WorkflowError("EXECUTION_CONTEXT_HASH_MISMATCH")
        fd, name = tempfile.mkstemp(prefix=".execution-input-", dir=self.base)
        path = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            actual=path.read_bytes()
            if actual != data or hashlib.sha256(actual).hexdigest() != expected_hash:
                raise WorkflowError("EXECUTION_INPUT_VERIFICATION_FAILED")
            return path
        except Exception:
            if path.exists() or path.is_symlink(): path.unlink()
            raise
    def init(self):
        with lock(self.base/"lock"):
            if self.journal.path.exists(): raise WorkflowError("workflow already initialized")
            self.base.mkdir(parents=True,exist_ok=True)
            for d in DIRS: (self.base/d).mkdir(parents=True,exist_ok=True)
            w=witness(self.root,self.allowed); self.journal.append("WORKFLOW_INITIALIZED",repository_root=str(self.root),head=w["head"],branch=w["branch"],witness=w,validation_epoch=2); self._save(replay_journal(self.journal.read()))
    def rebuild(self):
        with lock(self.base/"lock"):
            events,s=self._replayed()
            if not s["initialized"]: raise WorkflowError("WORKFLOW_NOT_INITIALIZED")
            self._validate_historical_provenance(events)
            validate_spool(self.base,s); self._save(s); return s
    def _archive(self,raw,digest):
        p=self.base/"prompts"/(digest+".txt")
        if p.exists() and sha(p)!=digest: raise WorkflowError("PROMPT_ARCHIVE_CORRUPT")
        if not p.exists():
            with p.open("wb") as f: f.write(raw); f.flush(); os.fsync(f.fileno())
            fsync_dir(p.parent)
    def ingest(self):
        with lock(self.base/"lock"):
            _,state=self._preflight(); ownership={"protected_untracked":state.get("protected_untracked",[]),"patch_owned_untracked":state.get("patch_owned_untracked",[])}; current=witness(self.root,self.allowed,ownership); expected=state["latest_repository_witness"]
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
                    # Keep the schema as durable positive evidence for legacy
                    # compatibility; its absence must never select v1 under a
                    # v2 workflow root.
                    payload["prompt_schema"] = p.prompt_schema
                    if p.prompt_schema != "atlas-agent-prompt/1":
                        payload["network_access"] = p.network_access
                        if p.reuse_execution_id is not None: payload["reuse_execution_id"]=p.reuse_execution_id
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
    def _policy_for(self, record):
        path=self.root/"atlas-agent-policy.toml"
        if not path.exists():
            if record.get("prompt_schema")=="atlas-agent-prompt/2": raise WorkflowError("POLICY_CONFIG_REQUIRED")
            return None
        try: return load_policy(path)
        except PolicyError as error: raise WorkflowError(str(error)) from error
    @staticmethod
    def _execution_result(record):
        return canonical_execution_result(record)
    def _parent_context(self, state, generation):
        """Build the bounded, informational context for the immediate parent."""
        parent = state["generations"].get(str(generation - 1))
        if parent is None:
            data=encode_context_supplement({"kind":"none"}).encode()
            return data, None
        form={"kind":"checkpoint" if parent.get("action")=="checkpoint" else "execution", "generation":parent["generation"], "action":_context_value(parent.get("action")) or "unavailable", "status":_context_value(parent.get("status")) or "unavailable"}
        if parent["action"] == "checkpoint":
            result = parent.get("result") or {}
            commit = result.get("commit_sha")
            form["commit"] = commit if _context_value(commit) else None
            data=encode_context_supplement(form).encode("utf-8")
            if len(data)>SUPPLEMENT_MAX_BYTES: raise WorkflowError("CONTEXT_SUPPLEMENT_TOO_LARGE")
            return data, {"kind": "checkpoint", "generation": parent["generation"], "status": parent["status"], "commit": commit if _context_value(commit) else None}
        execution = parent.get("execution") or {}
        result = self._execution_result(parent)
        execution_id = _context_value(execution.get("execution_id"))
        thread_id = result.get("session_id")
        available = parent["status"] in {"COMPLETED", "INTERRUPTED"} and bool(execution)
        provenance = (parent.get("result") or {}).get("report_provenance") or execution.get("report_provenance")
        if execution.get("provenance_version") == 2:
            if not isinstance(provenance, dict) or provenance.get("status") not in {"available", "unavailable"}:
                raise WorkflowError("REPORT_PROVENANCE_MISSING")
            available = available and provenance["status"] == "available"
        elif available:
            # Legacy parent context is reconstructed from terminal metadata;
            # mutable current stdout is not historical state.
            terminal_claim = (parent.get("result") or {}).get("report_available")
            if isinstance(provenance, dict):
                terminal_claim = provenance.get("status") == "available"
            available = terminal_claim is True
        form.update({"execution_id":execution_id, "thread_id":_context_value(thread_id), "report_available":available})
        data=encode_context_supplement(form).encode("utf-8")
        if len(data)>SUPPLEMENT_MAX_BYTES: raise WorkflowError("CONTEXT_SUPPLEMENT_TOO_LARGE")
        return data, {"kind": "execution", "generation": parent["generation"], "status": parent["status"], "execution_id": execution_id, "report_available": available}
    def _publish_context(self, path, data):
        # The context directory is a fixed location inside the runtime tree.
        # Do not follow a pre-existing symlink at any component.
        contexts=self.base/"reports"/"contexts"
        if (path.parent != contexts or path.is_symlink() or contexts.is_symlink() or
                contexts.parent.is_symlink() or self.base.is_symlink()):
            raise WorkflowError("EXECUTION_CONTEXT_COLLISION")
        if not contexts.exists():
            contexts.mkdir(parents=True, exist_ok=False); fsync_dir(contexts.parent)
        if not contexts.is_dir(): raise WorkflowError("EXECUTION_CONTEXT_COLLISION")
        if path.exists():
            if path.is_symlink(): raise WorkflowError("EXECUTION_CONTEXT_COLLISION")
            if path.read_bytes() != data: raise WorkflowError("EXECUTION_CONTEXT_CONFLICT")
            fsync_dir(path.parent); return
        fd, tmp = tempfile.mkstemp(prefix="context-", dir=path.parent); staged = Path(tmp)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            try: os.link(staged,path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes()!=data: raise WorkflowError("EXECUTION_CONTEXT_CONFLICT")
            fsync_dir(path.parent)
        finally:
            if staged.exists(): staged.unlink()
    @staticmethod
    def _observe(observer,event):
        if observer is None: return
        try: observer(event)
        except Exception:
            # Human presentation is never lifecycle authority.
            pass
    def _reuse_snapshot(self, state, record, snapshot):
        target_id=record.get("reuse_execution_id")
        if not target_id: raise WorkflowError("REUSE_TARGET_MISSING")
        candidates=[]
        for candidate in state["generations"].values():
            owner=candidate.get("execution")
            if owner and owner.get("execution_id")==target_id: candidates.append((candidate,owner))
        if len(candidates)!=1: raise WorkflowError("REUSE_TARGET_UNKNOWN")
        target, owner=candidates[0]; target_result=self._execution_result(target)
        if target["status"]!="COMPLETED" or target_result.get("outcome")!="success": raise WorkflowError("REUSE_TARGET_STALE")
        thread_id=target_result.get("session_id")
        if not isinstance(thread_id,str) or not thread_id: raise WorkflowError("REUSE_TARGET_NO_THREAD")
        target_snapshot=owner.get("policy_snapshot")
        if owner.get("owner_schema")!="atlas-agent-execution-owner/2" or not isinstance(target_snapshot,dict): raise WorkflowError("REUSE_TARGET_INCOMPATIBLE")
        if (
            target_snapshot.get("schema") != "atlas-agent-policy-snapshot/2"
            or snapshot.get("schema") != "atlas-agent-policy-snapshot/2"
        ):
            raise WorkflowError("REUSE_TARGET_INCOMPATIBLE")
        for key in ("action","profile","executor","requested_model","requested_reasoning_effort","sandbox_mode","network_access","web_search","apps_enabled","session_storage","codex_profile","codex_binary_sha256","codex_config_sha256","codex_catalog_sha256","codex_profile_sha256"):
            if target_snapshot.get(key)!=snapshot.get(key): raise WorkflowError("REUSE_TARGET_INCOMPATIBLE")
        generation=record["generation"]
        if generation-target["generation"]>snapshot["max_reuse_generation_gap"]: raise WorkflowError("REUSE_TARGET_STALE")
        depth=target_snapshot.get("reuse_depth",0)+1
        if depth>snapshot["max_hot_reuse_hops"]: raise WorkflowError("REUSE_TARGET_STALE")
        for candidate in state["generations"].values():
            candidate_owner=candidate.get("execution") or {}
            candidate_snapshot=candidate_owner.get("policy_snapshot") or {}
            if candidate["status"]=="RUNNING" and candidate_snapshot.get("requested_thread_id")==thread_id:
                raise WorkflowError("REUSE_TARGET_STALE")
            if candidate["generation"]<=target["generation"]: continue
            result=self._execution_result(candidate)
            if result.get("session_id")!=thread_id and candidate_snapshot.get("requested_thread_id")!=thread_id: continue
            if candidate["status"]!="COMPLETED" or result.get("outcome")!="success": raise WorkflowError("REUSE_LINEAGE_TAINTED")
            raise WorkflowError("REUSE_TARGET_STALE")
        snapshot=dict(snapshot); snapshot.update({"reused_from_execution_id":target_id,"requested_thread_id":thread_id,"reuse_depth":depth})
        return snapshot
    @staticmethod
    def _known_thread_ids(state):
        known=set()
        for record in state["generations"].values():
            result=Workflow._execution_result(record)
            thread_id=result.get("session_id")
            if isinstance(thread_id,str) and thread_id: known.add(thread_id)
        return known
    def _validate_observed_session(self,state,snapshot,result):
        observed=result.session_id
        mode=snapshot.get("session_mode")
        if not isinstance(observed,str) or not observed:
            raise WorkflowError("FRESHNESS_UNVERIFIED" if mode=="fresh" else "REUSE_THREAD_UNVERIFIED")
        if mode=="fresh" and observed in self._known_thread_ids(state):
            raise WorkflowError("FRESHNESS_VIOLATION")
        if mode=="reuse" and observed!=snapshot.get("requested_thread_id"):
            raise WorkflowError("REUSE_THREAD_MISMATCH")
        requested_model=snapshot.get("requested_model")
        if result.observed_model is not None and result.observed_model!=requested_model:
            raise WorkflowError("OBSERVED_MODEL_MISMATCH")
        requested_reasoning=snapshot.get("requested_reasoning_effort")
        if result.observed_reasoning is not None and result.observed_reasoning!=requested_reasoning:
            raise WorkflowError("OBSERVED_REASONING_MISMATCH")
        return {"observed_thread_id":observed,"freshness_verification":"verified" if mode=="fresh" else "deferred"}
    def start_run(self,generation,hook=None,execution=None):
        with lock(self.base/"lock"):
            s,x=self._record(generation)
            if x["status"]!="ACCEPTED": raise WorkflowError("generation is not accepted")
            ownership={"protected_untracked":s.get("protected_untracked",[]),"patch_owned_untracked":s.get("patch_owned_untracked",[])}
            if witness(self.root,self.allowed,ownership)!=x["witness"]: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH")
            if execution is not None:
                execution_id=execution.get("execution_id")
                report_dir=Path(execution.get("report_dir",""))
                if type(execution_id) is not str or not execution_id or report_dir.is_absolute() or ".." in report_dir.parts or not str(report_dir).startswith("reports/executions/"):
                    raise WorkflowError("BAD_EXECUTION_METADATA")
                if any(r.get("execution",{}).get("execution_id")==execution_id for r in s["generations"].values()):
                    raise WorkflowError("EXECUTION_ID_COLLISION")
                if (self.base/report_dir).exists(): raise WorkflowError("EXECUTION_REPORT_COLLISION")
            src=self._find(self.base/"accepted",generation,x["prompt_sha256"]); payload={"generation":generation,"action":x["action"],"witness":x["witness"]}
            if x.get("prompt_schema") == "atlas-agent-prompt/2":
                network_access=x.get("network_access")
                if type(network_access) is not bool:
                    raise WorkflowError("PROMPT_NETWORK_PROVENANCE_MISSING")
                payload["network_access"]=network_access
            if execution is not None:
                # Preserve the public launcher path while giving an epoch-2
                # durable start the same provenance shape as execute().
                if s.get("validation_epoch", 1) >= 2 and "provenance_version" not in execution:
                    context=self._parent_context(s, generation)[0].decode("utf-8")
                    context_path=f"reports/contexts/{execution_id}.txt"
                    effective_path=f"reports/contexts/{execution_id}-effective.txt"
                    effective=hashlib.sha256(src.read_bytes()+context.encode()).hexdigest()
                    execution.update({"provenance_version":2,"report_provenance":{"status":"unavailable"},
                                      "prompt_input":"accepted_prompt_plus_atlas_context",
                                      "context_path":context_path,"effective_prompt_path":effective_path,
                                      "context_sha256":hashlib.sha256(context.encode()).hexdigest(),
                                      "effective_prompt_sha256":effective,"execution_input_sha256":effective})
                    payload["context_supplement"]=context
                payload["execution"]=execution
            move_transaction(self.base,self.journal,src,self.base/"running"/x["action"]/src.name,x["prompt_sha256"],"RUN_STARTED",payload,hook)
            try:
                s=replay_journal(self.journal.read()); self._save(s)
                post_start_error=None
            except BaseException as error:
                post_start_error=error
        if post_start_error is not None:
            reason=("KEYBOARD_INTERRUPT" if isinstance(post_start_error,KeyboardInterrupt)
                    else f"EXECUTOR_FAILURE: {post_start_error}")
            try:
                # The durable RUN_STARTED is authoritative even when the
                # state projection itself was interrupted.  interrupt_run
                # can reconstruct the RUNNING record directly from it.
                self.interrupt_run(generation,reason)
            except BaseException as terminal_error:
                raise WorkflowError(f"RUN_TERMINALIZATION_FAILED: {reason}") from terminal_error
            raise post_start_error
        return s
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
            self._validate_terminal_transition("RUN_COMPLETED", {"generation":generation,"execution":owner,"result":r}, s)
            ownership={"protected_untracked":s.get("protected_untracked",[]),"patch_owned_untracked":s.get("patch_owned_untracked",[])}
            before=x["witness"]; now=witness(self.root,self.allowed,ownership)
            violation=not witness_matches_policy(now,before,x["action"],running=True,ownership=ownership)
            src=self._find(self.base/"running"/x["action"],generation,x["prompt_sha256"])
            if violation:
                payload={"generation":generation,"action":x["action"],"reason":"REPOSITORY_POLICY_VIOLATION"};
                if x.get("execution") is not None: payload["execution"]=x["execution"]
                if isinstance(r.get("executor_result"),dict): payload["executor_result"]=r["executor_result"]
                if isinstance(x.get("execution"),dict) and x["execution"].get("provenance_version")==2:
                    payload["result"]={"report_provenance":r.get("report_provenance", {"status":"unavailable"})}
                move_transaction(self.base,self.journal,src,self.base/"interrupted"/src.name,x["prompt_sha256"],"RUN_INTERRUPTED",payload,hook)
                self._project_interruption("REPOSITORY_POLICY_VIOLATION")
                raise _RunTerminalError("REPOSITORY_POLICY_VIOLATION")
            owned=set(ownership["patch_owned_untracked"])
            protected={z["path"] for z in ownership["protected_untracked"]}
            start={z["path"] for z in before.get("unexpected_untracked",[])}
            terminal={z["path"] for z in now.get("unexpected_untracked",[])}
            acquired=sorted(terminal-start-protected-owned) if x["action"]=="implementation" else []
            payload={"generation":generation,"action":x["action"],"result":r,"witness":now,"acquired_untracked":acquired};
            if x.get("execution") is not None: payload["execution"]=x["execution"]
            move_transaction(self.base,self.journal,src,self.base/"completed"/src.name,x["prompt_sha256"],"RUN_COMPLETED",payload,hook); s=replay_journal(self.journal.read()); self._save(s); return s
    def _project_interruption(self,reason):
        """Refresh the cache after a durable terminal journal transition."""
        try:
            state=replay_journal(self.journal.read())
            self._save(state)
            return True
        except BaseException:
            # The journal transition is already canonical.  Projection failure
            # is secondary to the original abort and must never replace it.
            return False
    def _recover_interruption_artifacts(self,state):
        """Fill only absences witnessed by a canonical interruption."""
        interruptions={event["payload"]["generation"]:event["payload"] for event in self.journal.read() if event["event"]=="RUN_INTERRUPTED"}
        for record in state["generations"].values():
            execution=record.get("execution")
            if record.get("status")!="INTERRUPTED" or not isinstance(execution,dict):
                continue
            payload=interruptions.get(record["generation"])
            if payload is None:
                raise WorkflowError("JOURNAL_INTERRUPTION_MISSING")
            fallback=payload.get("fallback_artifacts")
            if fallback is None:
                continue
            report_dir=Path(execution.get("report_dir",""))
            if report_dir.is_absolute() or ".." in report_dir.parts or not str(report_dir).startswith("reports/executions/"):
                raise WorkflowError("BAD_EXECUTION_METADATA")
            directory=self.base/report_dir
            owner={"execution_id":execution.get("execution_id"),"executor":execution.get("executor"),"generation":record["generation"],"prompt_sha256":record["prompt_sha256"],"action":record["action"]}
            if execution.get("permission_envelope") is not None: owner["permission_envelope"]=execution["permission_envelope"]
            if execution.get("owner_schema") is not None: owner.update({"owner_schema":execution.get("owner_schema"),"policy_snapshot":execution.get("policy_snapshot")})
            result={**owner,"outcome":"exception","error":payload.get("reason"),"permission_observation_status":"unavailable","permission_failures":None,"telemetry_status":"failed","telemetry_error":"unavailable after durable interruption"}
            executor_result=payload.get("executor_result")
            if isinstance(executor_result,dict): result={**executor_result,**result}
            snapshot=execution.get("policy_snapshot") if isinstance(execution.get("policy_snapshot"),dict) else {}
            usage={"schema":USAGE_SCHEMA,"execution_id":execution.get("execution_id"),"generation":record["generation"],"prompt_sha256":record["prompt_sha256"],"action":record["action"],"checkpoint":record.get("checkpoint"),"thread_id":executor_result.get("session_id") if isinstance(executor_result,dict) else None,"codex_version":executor_result.get("version") if isinstance(executor_result,dict) else None,"requested_model":snapshot.get("requested_model"),"requested_reasoning":snapshot.get("requested_reasoning_effort"),"observed_model":executor_result.get("observed_model") if isinstance(executor_result,dict) else None,"reasoning_effort":executor_result.get("observed_reasoning") if isinstance(executor_result,dict) else None,"run":None,"context_window":None,"context_used":None,"context_remaining":None,"quota_before":None,"quota_after":None,"quota_status":"unavailable","sources":["unavailable"],"status":"unavailable","parser_malformed_lines":0,"captured_at":((executor_result or {}).get("finished_at") if isinstance(executor_result,dict) else None) or execution.get("started_at") or "unavailable"}
            for key in ("policy_config_sha256","asset_version","asset_set_sha256","prompt_set_sha256","profile","session_mode","reused_from_execution_id","reuse_depth","cold_policy","freshness_verification"):
                if key in snapshot: usage[key]=snapshot[key]
            files={"stdout.log":b"","stderr.log":b"","result.json":(json.dumps(result,sort_keys=True,indent=2)+"\n").encode(),"usage.json":(json.dumps(usage,sort_keys=True,indent=2)+"\n").encode()}
            for name in fallback: self._publish_missing_execution_file(directory/name,files[name])

    def _recover_context_artifacts(self, state):
        """Best-effort replay of non-authoritative, deterministic context files."""
        starts={e["payload"].get("generation"):e["payload"] for e in self.journal.read()
                if e["event"]=="RUN_STARTED"}
        for record in state["generations"].values():
            execution=record.get("execution")
            payload=starts.get(record.get("generation"))
            if not isinstance(execution,dict) or not isinstance(payload,dict): continue
            provenance={"prompt_input","context_path","effective_prompt_path","context_sha256","effective_prompt_sha256"}
            if not provenance <= set(execution) or "context_supplement" not in payload: continue
            try:
                context=payload["context_supplement"].encode("utf-8")
                context_path=self.base/Path(execution["context_path"])
                effective_path=self.base/Path(execution["effective_prompt_path"])
                if context_path.parent != self.base/"reports"/"contexts" or effective_path.parent != context_path.parent:
                    raise WorkflowError("EXECUTION_CONTEXT_COLLISION")
                prompt=self.base/"prompts"/(record["prompt_sha256"]+".txt")
                if not prompt.is_file() or sha(prompt)!=record["prompt_sha256"]:
                    raise WorkflowError("PROMPT_ARCHIVE_CORRUPT")
                effective=prompt.read_bytes()+context
                if hashlib.sha256(context).hexdigest()!=execution["context_sha256"] or hashlib.sha256(effective).hexdigest()!=execution["effective_prompt_sha256"]:
                    raise WorkflowError("EXECUTION_CONTEXT_HASH_MISMATCH")
                self._publish_context(context_path,context)
                self._publish_context(effective_path,effective)
            except WorkflowError as error:
                if str(error) in {"EXECUTION_CONTEXT_HASH_MISMATCH", "PROMPT_ARCHIVE_CORRUPT"}: raise
                # Filesystem presentation conflicts remain informational.
                continue
            except (OSError,UnicodeError):
                # These files are informational.  A missing, corrupt, or
                # conflicting artifact is reported by provenance inspection,
                # but cannot alter an otherwise valid lifecycle projection.
                continue
    def _missing_interruption_artifacts(self,record):
        execution=record.get("execution")
        if not isinstance(execution,dict): return []
        report_dir=self.base/execution["report_dir"]
        missing=[name for name in ("stdout.log","stderr.log") if not (report_dir/name).is_file()]
        result_path=report_dir/"result.json"
        if not result_path.is_file():
            missing.append("result.json")
        else:
            try: result=json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError,UnicodeError,json.JSONDecodeError): result=None
            if isinstance(result,dict) and result.get("telemetry_status")!="failed" and not (report_dir/"usage.json").is_file():
                missing.append("usage.json")
        return missing
    def interrupt_run(self,generation,reason,executor_result=None):
        with lock(self.base/"lock"):
            try:
                s,x=self._record(generation)
            except WorkflowError as error:
                if not str(error).startswith("STATE_STALE_OR_TAMPERED"):
                    raise
                # A failed RUNNING projection must not prevent the durable
                # terminal transition from being appended.
                s=replay_journal(self.journal.read()); x=s["generations"].get(str(generation))
                if not x: raise
            if x["status"]!="RUNNING": raise WorkflowError("generation is not running")
            src=self._find(self.base/"running"/x["action"],generation,x["prompt_sha256"]); payload={"generation":generation,"action":x["action"],"reason":reason};
            if x.get("execution") is not None: payload["execution"]=x["execution"]
            if isinstance(executor_result,dict):
                owner_id=(x.get("execution") or {}).get("execution_id")
                if executor_result.get("execution_id") == owner_id:
                    payload["executor_result"] = executor_result
            if isinstance(x.get("execution"),dict) and x["execution"].get("provenance_version")==2:
                descriptor={"status":"unavailable"}
                if x["execution"].get("executor")=="codex":
                    try:
                        report=CodexExecutor.latest_agent_report(self._report_path({"status":"INTERRUPTED","execution":x["execution"]}))
                        descriptor={"status":"available","report_sha256":hashlib.sha256(report.encode("utf-8")).hexdigest()}
                    except (ExecutorError,WorkflowError):
                        pass
                payload["result"]={"report_provenance":descriptor}
            fallback=self._missing_interruption_artifacts(x)
            if fallback: payload["fallback_artifacts"]=fallback
            self._validate_terminal_transition("RUN_INTERRUPTED", payload, s)
            move_transaction(self.base,self.journal,src,self.base/"interrupted"/src.name,x["prompt_sha256"],"RUN_INTERRUPTED",payload)
            return self._project_interruption(reason)
    def _finish_checkpoint(self,generation,x,intent,now):
        src=self._find(self.base/("accepted" if x["status"]=="ACCEPTED" else "running/checkpoint"),generation,x["prompt_sha256"])
        if x["status"]=="ACCEPTED":
            running=self.base/"running"/x["action"]/src.name
            start_payload={"generation":generation,"action":x["action"],"witness":x["witness"]}
            if x.get("prompt_schema") == "atlas-agent-prompt/2":
                start_payload["network_access"] = x["network_access"]
            move_transaction(self.base,self.journal,src,running,x["prompt_sha256"],"RUN_STARTED",start_payload)
            src=running
        result={"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"outcome":"committed","classification":"manual_checkpoint","commit_sha":intent["commit_sha"]}
        move_transaction(self.base,self.journal,src,self.base/"completed"/src.name,x["prompt_sha256"],"RUN_COMPLETED",{"generation":generation,"action":x["action"],"result":result,"witness":now})

    def checkpoint(self,generation,message,hook=None):
        """Commit and durably complete one accepted manual checkpoint."""
        with lock(self.base/"lock"):
            s,x=self._record(generation)
            if x["status"]!="ACCEPTED": raise WorkflowError("generation is not accepted")
            if x["action"]!="checkpoint": raise WorkflowError("GENERATION_IS_NOT_CHECKPOINT")
            if type(message) is not str or not message.strip(): raise WorkflowError("CHECKPOINT_COMMIT_MESSAGE_REQUIRED")
            ownership={"protected_untracked":s.get("protected_untracked",[]),"patch_owned_untracked":s.get("patch_owned_untracked",[])}
            if witness(self.root,self.allowed,ownership)!=x["witness"]: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH")
            try: intent=prepare_checkpoint(self.root,self.allowed,x["witness"],message,s.get("patch_owned_untracked",[]),[z["path"] for z in s.get("protected_untracked",[])])
            except RepositoryError as error: raise WorkflowError(str(error)) from error
            payload={"generation":generation,"prompt_sha256":x["prompt_sha256"],**intent}
            try: self.journal.append("CHECKPOINT_INTENT",**payload)
            except Exception as original:
                try: rollback_checkpoint(self.root,self.allowed,x["witness"],original)
                except RepositoryError as error: raise WorkflowError(str(error)) from error
                raise WorkflowError(f"CHECKPOINT_INTENT_PERSISTENCE_FAILED: {original}") from original
            if hook: hook("intent",payload)
            try: now=advance_checkpoint(self.root,self.allowed,intent,ownership)
            except RepositoryError as error: raise WorkflowError(f"CHECKPOINT_RECOVERY_REQUIRED: {error}") from error
            if hook: hook("committed",payload)
            try:
                now=verify_checkpoint_boundary(self.root,self.allowed,intent,ownership)
            except RepositoryError as error:
                raise WorkflowError(f"CHECKPOINT_RECOVERY_REQUIRED: {error}") from error
            self._finish_checkpoint(generation,x,intent,now)
            s=replay_journal(self.journal.read()); self._save(s); return s
    def execute(self,generation,executor=None,observer=None):
        """Explicitly execute one accepted generation through W1 lifecycle."""
        with lock(self.base/"lock"):
            s,x=self._record(generation)
            if x["status"]!="ACCEPTED": raise WorkflowError("generation is not accepted")
            accepted=self._find(self.base/"accepted",generation,x["prompt_sha256"])
            prompt_bytes=accepted.read_bytes()
            try: prompt=parse_prompt(prompt_bytes)
            except PromptError as error: raise WorkflowError(error.code) from error
            policy=self._policy_for(x)
            snapshot=None
            if prompt.prompt_schema=="atlas-agent-prompt/1" and prompt.session_mode=="reuse" and policy is None:
                raise WorkflowError("REUSE_TARGET_MISSING")
            if policy is not None:
                try: snapshot=resolve_policy(policy,prompt)
                except PolicyError as error: raise WorkflowError(str(error)) from error
                if prompt.session_mode=="reuse":
                    try: snapshot=self._reuse_snapshot(s,x,snapshot)
                    except WorkflowError: raise
                if snapshot["executor"]=="manual": raise WorkflowError("CHECKPOINT_MANUAL_REQUIRED")
            if (self.root/".codex"/"config.toml").is_file(): raise WorkflowError("CODEX_PROJECT_CONFIG_UNSUPPORTED")
            executor=executor or AtlasBubblewrapExecutor()
            if snapshot and isinstance(executor,CodexExecutor):
                executor.model=snapshot["requested_model"]; executor.sandbox=snapshot["sandbox_mode"]; executor.sandbox_mode=executor.sandbox; executor.network_access=snapshot["network_access"]; executor.ephemeral=snapshot["session_storage"]=="ephemeral"
            ownership={"protected_untracked":s.get("protected_untracked",[]),"patch_owned_untracked":s.get("patch_owned_untracked",[])}
            if witness(self.root,self.allowed,ownership)!=x["witness"]: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH")
            execution_id=new_execution_id(); report_dir=self.base/"reports"/"executions"/execution_id
            context, context_info = self._parent_context(s, generation)
            context_sha256=hashlib.sha256(context).hexdigest()
            effective_input=x["prompt_sha256"]
            effective_input=hashlib.sha256(prompt_bytes+context).hexdigest()
            context_path=self.base/"reports"/"contexts"/(execution_id+".txt")
            effective_path=self.base/"reports"/"contexts"/(execution_id+"-effective.txt")
            spec=ExecutionSpec(generation,x["prompt_sha256"],x["action"],accepted,self.root,execution_id,report_dir,self.base,x.get("checkpoint"),snapshot,prompt_bytes+context,"bytes-v1",effective_input)
            prepared=executor.prepare_execution(spec)
            if snapshot:
                try: current_policy_hash=policy_config_sha256(load_policy(self.root/"atlas-agent-policy.toml"))
                except PolicyError as error: raise WorkflowError(str(error)) from error
                if current_policy_hash!=snapshot["policy_config_sha256"]: raise WorkflowError("POLICY_RESOLUTION_MISMATCH")
            if witness(self.root,self.allowed,ownership)!=x["witness"]: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH")
            metadata={"execution_id":execution_id,"executor":prepared.executor,"started_at":utc_now(),"pid":None,"report_dir":str(report_dir.relative_to(self.base)),"permission_envelope":prepared.permission_envelope,"provenance_version":2,"report_provenance":{"status":"unavailable"}}
            sandbox_descriptor = (
                prepared.runtime_handle
                if isinstance(prepared.runtime_handle, dict)
                else None
            )
            if sandbox_descriptor is None and hasattr(executor, "sandbox_descriptor"):
                candidate = executor.sandbox_descriptor()
                if isinstance(candidate, dict) and candidate:
                    sandbox_descriptor = candidate
            if sandbox_descriptor is not None:
                metadata["sandbox"] = dict(sandbox_descriptor)
                metadata["execution_backend_schema"] = "atlas-bwrap-execution/1"
            metadata.update({"prompt_input":"accepted_prompt_plus_atlas_context","context_path":str(context_path.relative_to(self.base)),"effective_prompt_path":str(effective_path.relative_to(self.base)),"context_sha256":context_sha256,"effective_prompt_sha256":effective_input,"execution_input_sha256":effective_input})
            if snapshot:
                metadata.update({"owner_schema":"atlas-agent-execution-owner/2","policy_snapshot":snapshot})
            if any(r.get("execution",{}).get("execution_id")==execution_id for r in s["generations"].values()): raise WorkflowError("EXECUTION_ID_COLLISION")
            if (self.base/metadata["report_dir"]).exists(): raise WorkflowError("EXECUTION_REPORT_COLLISION")
            execution_artifact={**metadata,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"command":list(prepared.command),"version":prepared.version,"permission_envelope":prepared.permission_envelope}
            src=self._find(self.base/"accepted",generation,x["prompt_sha256"])
            start_payload={"generation":generation,"action":x["action"],"witness":x["witness"],"execution":metadata,"context_supplement":context.decode("utf-8")}
            if snapshot is not None:
                start_payload["network_access"] = prompt.network_access if prompt.prompt_schema=="atlas-agent-prompt/2" else False
            self._validate_authoritative_provenance(start_payload,s,prompt_bytes)
            def publish_owner(stage,transaction):
                if stage=="prepared": self._prepare_execution_publication(transaction,execution_artifact)
            move_transaction(self.base,self.journal,src,self.base/"running"/x["action"]/src.name,x["prompt_sha256"],"RUN_STARTED",start_payload,publish_owner)
            # RUN_STARTED is durable before reconstruction/projection.  From
            # this boundary every BaseException must pass through the same
            # durable terminalization path as executor failures.
            started=True
            post_start_error=None
            try:
                s=replay_journal(self.journal.read()); self._save(s)
            except BaseException as error:
                post_start_error=error
        if post_start_error is not None:
            reason=("KEYBOARD_INTERRUPT" if isinstance(post_start_error,KeyboardInterrupt)
                    else f"EXECUTOR_FAILURE: {post_start_error}")
            try:
                # The projection that failed is needed by interrupt_run's
                # normal preflight.  Rebuild it first, outside the original
                # lock, before appending the terminal transition.
                try:
                    self._save(replay_journal(self.journal.read()))
                except BaseException:
                    # interrupt_run can use the journal projection directly;
                    # a second projection failure must not strand RUNNING.
                    pass
                self.interrupt_run(generation,reason)
            except BaseException as terminal_error:
                raise _RunTerminalError(reason) from terminal_error
            raise post_start_error
        running= self.base/"running"/x["action"]/accepted.name
        started=True; telemetry_failed=False
        execution_input=None
        try:
            try:
                self._publish_context(context_path,context)
                self._publish_context(effective_path,prompt_bytes+context)
            except (WorkflowError,OSError,UnicodeError):
                # Provenance presentation is informational; RUN_STARTED is authoritative.
                pass
            prepared=getattr(executor,"post_start_prepare",lambda value: value)(prepared)
            self._publish_execution_artifact(report_dir/"execution.json",{**metadata,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"command":list(prepared.command),"version":prepared.version,"permission_envelope":prepared.permission_envelope})
            execution_input=self._stage_execution_input(prompt_bytes+context, effective_input)
            prepared=replace(prepared,spec=replace(prepared.spec,prompt_path=execution_input))
            launch={"kind":"dispatch_started","generation":generation,"action":x["action"],"session_mode":x.get("session_mode"),"execution_id":execution_id,"permission_envelope":prepared.permission_envelope}
            if hasattr(executor, "sandbox_descriptor"):
                launch["sandbox"] = executor.sandbox_descriptor()
            if snapshot: launch["policy_snapshot"]=snapshot
            self._observe(observer,launch)
            result=executor.run_execution(prepared)
            if getattr(result, "execution_input_sha256", None) != effective_input:
                raise WorkflowError("EXECUTION_INPUT_HASH_MISMATCH")
            result_payload={**result.__dict__,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"]}
            if snapshot:
                result_payload.update({"owner_schema":"atlas-agent-execution-owner/2","policy_snapshot":snapshot})
            _write_json(report_dir/"result.json",result_payload)
            try:
                collect_usage(prepared.spec,result,report_dir,requested_model=getattr(executor,"model",None),requested_reasoning=getattr(executor,"reasoning_effort",None),policy_snapshot=snapshot)
            except OSError as error:
                telemetry_failed=True
                _write_json(report_dir/"result.json",{**result_payload,"telemetry_status":"failed","telemetry_error":str(error)})
                self.interrupt_run(generation,"TELEMETRY_WRITE_FAILURE",result.__dict__)
                started=False
                raise WorkflowError(f"TELEMETRY_WRITE_FAILURE: {error}") from error
            if result.timed_out:
                self.interrupt_run(generation,"EXECUTOR_TIMEOUT",result.__dict__)
                raise WorkflowError("EXECUTOR_TIMEOUT")
            if result.exit_code != 0:
                reason="REUSE_SESSION_UNAVAILABLE" if snapshot and snapshot.get("session_mode")=="reuse" else f"EXECUTOR_EXIT_{result.exit_code}"
                self.interrupt_run(generation,reason,result.__dict__)
                raise WorkflowError(reason)
            try:
                observed_metadata=self._validate_observed_session(s,snapshot,result) if snapshot else {}
            except WorkflowError as error:
                self.interrupt_run(generation,str(error),result.__dict__)
                started=False
                result_payload["session_validation_error"]=str(error)
                _write_json(report_dir/"result.json",result_payload)
                raise
            if observed_metadata:
                result_payload.update(observed_metadata)
                _write_json(report_dir/"result.json",result_payload)
            report_provenance={"status":"unavailable"}
            if result.outcome == "success" and prepared.executor == "codex":
                try:
                    report_text=self._extract_report({"status":"COMPLETED","execution":metadata})
                    report_provenance={"status":"available","report_sha256":hashlib.sha256(report_text.encode("utf-8")).hexdigest()}
                except WorkflowError:
                    pass
            envelope={"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"outcome":result.outcome,"classification":"executor_process","report_path":result.report_path,"executor_result":result.__dict__,"report_provenance":report_provenance}
            envelope.update(observed_metadata)
            if execution_input is not None:
                execution_input.unlink(missing_ok=True)
                execution_input=None
            return self.complete_run(generation,envelope)
        except BaseException as error:
            if isinstance(error,_RunTerminalError): raise
            if isinstance(error, WorkflowError) and (str(error).startswith("EXECUTOR_EXIT_") or str(error)=="EXECUTOR_TIMEOUT" or str(error) in SESSION_VALIDATION_ERRORS): raise
            stdout=report_dir/"stdout.log"; stderr=report_dir/"stderr.log"
            if started:
                failed_result=locals().get("result")
                executor_result=failed_result.__dict__ if failed_result is not None else None
                interrupt_reason=("REUSE_SESSION_UNAVAILABLE" if snapshot and snapshot.get("session_mode")=="reuse" else
                                  ("KEYBOARD_INTERRUPT" if isinstance(error,KeyboardInterrupt) else f"EXECUTOR_FAILURE: {error}"))
                try:
                    projected = self.interrupt_run(generation,interrupt_reason,executor_result)
                    # Preserve every non-Exception BaseException exactly once
                    # its interruption has been durably journaled.  Projection
                    # is secondary and must not determine its public outcome.
                    if not isinstance(error, Exception) and projected is False:
                        raise error
                    if projected is False:
                        # Ordinary executor exceptions retain their public
                        # error contract, while skipping post-failure artifact
                        # work until recovery can project it safely.
                        if isinstance(error, WorkflowError):
                            raise error
                        raise WorkflowError(f"EXECUTOR_FAILURE: {error}") from error
                finally: started=False
            if not telemetry_failed:
                try: collect_usage(prepared.spec,type("Result",(),{"session_id":None,"version":prepared.version})(),report_dir,requested_model=getattr(executor,"model",None),policy_snapshot=snapshot)
                except OSError: pass
                try:
                    stdout.touch(exist_ok=True); stderr.touch(exist_ok=True)
                    failure={"execution_id":execution_id,"executor":prepared.executor,"generation":generation,"prompt_sha256":x["prompt_sha256"],"action":x["action"],"outcome":"exception","error":str(error),"permission_envelope":prepared.permission_envelope,"permission_observation_status":"unavailable","permission_failures":None}
                    if snapshot: failure.update({"owner_schema":"atlas-agent-execution-owner/2","policy_snapshot":snapshot})
                    _write_json(report_dir/"result.json",failure)
                except OSError: pass
            if not isinstance(error,Exception): raise error
            if snapshot and snapshot.get("session_mode")=="reuse": raise WorkflowError("REUSE_SESSION_UNAVAILABLE") from error
            raise WorkflowError(f"EXECUTOR_FAILURE: {error}") from error
        finally:
            if execution_input is not None:
                try: execution_input.unlink(missing_ok=True)
                except OSError: pass
    def _interruption_reason(self,generation):
        for event in reversed(self.journal.read()):
            if event["event"]=="RUN_INTERRUPTED" and event["payload"].get("generation")==generation:
                return event["payload"].get("reason")
        return None
    def _report_path(self,record):
        execution=record.get("execution") or {}
        report_dir=Path(execution.get("report_dir",""))
        if report_dir.is_absolute() or ".." in report_dir.parts or not str(report_dir).startswith("reports/executions/"):
            raise WorkflowError("BAD_EXECUTION_METADATA")
        return self.base/report_dir/"stdout.log"
    def _extract_report(self,record):
        if record.get("status") not in {"COMPLETED","INTERRUPTED"}:
            raise WorkflowError("EXECUTION_NOT_TERMINAL")
        execution=record.get("execution") or {}
        if execution.get("executor")!="codex": raise WorkflowError("EXECUTION_REPORT_UNSUPPORTED_EXECUTOR")
        try:
            report=CodexExecutor.latest_agent_report(self._report_path(record))
            provenance=(record.get("result") or {}).get("report_provenance")
            if provenance:
                if provenance.get("status") != "available" or hashlib.sha256(report.encode("utf-8")).hexdigest()!=provenance.get("report_sha256"):
                    raise WorkflowError("EXECUTION_REPORT_PROVENANCE_MISMATCH")
            return report
        except ExecutorError as error: raise WorkflowError(str(error)) from error
    def report(self,generation=None):
        """Return a bounded executor-specific final human report."""
        _,state=self._preflight()
        if generation is not None:
            record=state["generations"].get(str(generation))
            if record is None: raise WorkflowError("UNKNOWN_GENERATION")
            return self._extract_report(record)
        failures=[]
        for record in sorted(state["generations"].values(),key=lambda value:value["generation"],reverse=True):
            if record.get("status") not in {"COMPLETED","INTERRUPTED"} or not record.get("execution"): continue
            try: return self._extract_report(record)
            except WorkflowError as error: failures.append(str(error))
        if failures and any(value.startswith("EXECUTOR_OUTPUT_MALFORMED") for value in failures):
            raise WorkflowError(next(value for value in failures if value.startswith("EXECUTOR_OUTPUT_MALFORMED")))
        raise WorkflowError("NO_EXECUTION_REPORT")
    def _report_available(self,record):
        try: self._extract_report(record); return True
        except WorkflowError: return False
    def history(self):
        _,state=self._preflight(); rows=[]
        for record in sorted(state["generations"].values(),key=lambda value:value["generation"]):
            execution=record.get("execution") or {}; result=self._execution_result(record)
            row={"generation":record["generation"],"action":record["action"],"status":record["status"],"execution_id":execution.get("execution_id"),"report_available":self._report_available(record) if execution else False}
            if isinstance(result,dict):
                if result.get("started_at"): row["started_at"]=result["started_at"]
                if result.get("finished_at"): row["finished_at"]=result["finished_at"]
            commit=(record.get("result") or {}).get("commit_sha")
            if isinstance(commit,str) and commit: row["commit_sha"]=commit
            rows.append(row)
        return rows
    def _dispatch_summary(self,generation,state):
        record=state["generations"][str(generation)]; result=record.get("result") or {}; executor_result=result.get("executor_result") or record.get("execution_result") or {}; execution=record.get("execution") or {}
        summary={"kind":"dispatch_finished","generation":generation,"action":record["action"],"status":record["status"],"execution_id":execution.get("execution_id"),"thread_id":executor_result.get("session_id"),"interruption_reason":self._interruption_reason(generation) if record["status"]=="INTERRUPTED" else None,"report_available":self._report_available(record) if execution else False}
        for key in ("started_at","finished_at"):
            if executor_result.get(key): summary[key]=executor_result[key]
        report_dir=execution.get("report_dir")
        if report_dir:
            usage_path=self.base/report_dir/"usage.json"
            usage=load_presentation_usage(usage_path,record)
            if usage is not None: summary["tokens"]=usage
        return summary
    def dispatch(self, executor=None, observer=None):
        """Execute exactly one already accepted generation.

        Selection is deliberately limited to the first accepted generation.
        Execution remains the authority for policy and lifecycle validation;
        in particular, a blocked generation is never skipped.
        """
        with lock(self.base/"lock"):
            _, state = self._preflight()
            accepted = [record for record in state["generations"].values()
                        if record["status"] == "ACCEPTED"]
            if not accepted:
                running = [record for record in state["generations"].values()
                           if record["status"] == "RUNNING"]
                if running:
                    generation = min(running, key=lambda value: value["generation"])["generation"]
                    raise WorkflowError(f"GENERATION_{generation}: generation is not accepted")
                raise WorkflowError("NO_DISPATCHABLE_GENERATION")
            record = min(accepted, key=lambda value: value["generation"])
            generation = record["generation"]
        try:
            state = self.execute(generation, executor, observer=observer)
        except Exception as error:
            try:
                failed=self._state()
                if failed["generations"][str(generation)]["status"]=="INTERRUPTED": self._observe(observer,self._dispatch_summary(generation,failed))
            except (WorkflowError,KeyError): pass
            raise WorkflowError(f"GENERATION_{generation}: {error}") from error
        summary=self._dispatch_summary(generation,state); self._observe(observer,summary); summary.pop("kind",None); return summary
    def recover(self):
        with lock(self.base/"lock"):
            try:
                events=self.journal.read()
            except JournalError as error:
                raise WorkflowError(str(error)) from error
            s=replay_journal(events)
            unresolved=[]
            unresolved.extend(next(e["seq"] for e in events if e["event"]=="TRANSITION_PREPARED" and e["payload"]["transaction_id"]==tx) for tx in s["outstanding_transactions"])
            unresolved.extend(next(e["seq"] for e in events if e["event"]=="CHECKPOINT_INTENT" and str(e["payload"]["generation"])==g and e["payload"]["commit_sha"]==p["commit_sha"]) for g,p in s.get("outstanding_checkpoints",{}).items())
            if not unresolved:
                if not self._state_file().exists(): raise WorkflowError("STATE_STALE_OR_TAMPERED: run rebuild-state")
                current=self._state()
                if current!=s:
                    last=events[-1] if events else None
                    recoverable={"RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"}
                    if not last or last["event"] not in recoverable: raise WorkflowError("STATE_STALE_OR_TAMPERED: run rebuild-state")
                    transaction_id=last["payload"]["transaction_id"]
                    prepared=next((e for e in events if e["event"]=="TRANSITION_PREPARED" and e["payload"]["transaction_id"]==transaction_id),None)
                    if prepared is None or current!=replay_journal([e for e in events if e["seq"]<prepared["seq"]]):
                        raise WorkflowError("STATE_STALE_OR_TAMPERED: run rebuild-state")
                self._validate_historical_provenance(events)
                self._recover_interruption_artifacts(s)
                self._recover_context_artifacts(s)
                validate_spool(self.base,s)
                if current!=s: self._save(s)
                return s
            first_prepare=min(unresolved)
            prior=replay_journal([e for e in events if e["seq"]<first_prepare])
            if not self._state_file().exists() or self._state()!=prior: raise WorkflowError("STATE_STALE_OR_TAMPERED: run rebuild-state")
            for tx,p in list(s["outstanding_transactions"].items()):
                src=self.base/p["source"]; dst=self.base/p["destination"]
                se=src.exists(); de=dst.exists()
                if se and sha(src)!=p["prompt_sha256"]: raise WorkflowError("RECOVERY_SOURCE_HASH_MISMATCH")
                if de and sha(dst)!=p["prompt_sha256"]: raise WorkflowError("RECOVERY_DESTINATION_HASH_MISMATCH")
                if se and de: raise WorkflowError("RECOVERY_AMBIGUOUS")
                if not se and not de: raise WorkflowError("RECOVERY_MISSING_BOTH")
                if p["logical_event"]=="RUN_STARTED" and "execution" in p:
                    self._validate_authoritative_provenance(p,prior)
                    self._prepare_execution_publication(p)
                if se: os.replace(src,dst); fsync_dir(src.parent); fsync_dir(dst.parent)
                terminal=dict(p); event=terminal.pop("logical_event")
                self._validate_terminal_transition(event,terminal,prior)
                self.journal.append(event,**terminal)
                if p["logical_event"]=="RUN_STARTED" and "execution" in p:
                    try:
                        self._prepare_context_publication(p)
                    except (OSError,UnicodeError,WorkflowError):
                        # Context files are informational presentation only.
                        pass
            s=replay_journal(self.journal.read())
            for g,intent in list(s.get("outstanding_checkpoints",{}).items()):
                x=s["generations"].get(g)
                head=witness(self.root,self.allowed)["head"]
                if head==intent["parent_head"]:
                    if not x or x["status"]!="ACCEPTED": raise WorkflowError("CHECKPOINT_RECOVERY_STATE_MISMATCH")
                    try: rollback_checkpoint(self.root,self.allowed,intent["witness"],WorkflowError("CHECKPOINT_COMMIT_DID_NOT_HAPPEN"))
                    except RepositoryError as error: raise WorkflowError(str(error)) from error
                    self.journal.append("CHECKPOINT_ABORTED",generation=x["generation"],prompt_sha256=x["prompt_sha256"],commit_sha=intent["commit_sha"],reason="commit_did_not_happen")
                    continue
                if head!=intent["commit_sha"]: raise WorkflowError("CHECKPOINT_RECOVERY_REPOSITORY_MISMATCH")
                try:
                    ownership={"protected_untracked":s.get("protected_untracked",[]),"patch_owned_untracked":s.get("patch_owned_untracked",[])}
                    now=verify_checkpoint_boundary(self.root,self.allowed,intent,ownership)
                except RepositoryError as error: raise WorkflowError(f"CHECKPOINT_RECOVERY_REPOSITORY_MISMATCH: {error}") from error
                if not x or x["status"] not in {"ACCEPTED","RUNNING"}: raise WorkflowError("CHECKPOINT_RECOVERY_STATE_MISMATCH")
                self._finish_checkpoint(x["generation"],x,intent,now)
            s=replay_journal(self.journal.read()); self._recover_interruption_artifacts(s); self._recover_context_artifacts(s); validate_spool(self.base,s); self._save(s); return s
