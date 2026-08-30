"""The append-only, strictly validated W1 journal."""
from __future__ import annotations
import hashlib, json, os, re, time
from datetime import datetime
from pathlib import Path
from .prompt import parse_prompt, PromptError
from typing import Any
from .model import SCHEMA
from .policy import validate_snapshot, PolicyError
class JournalError(RuntimeError): pass
ZERO="0"*64
EVENTS={"WORKFLOW_INITIALIZED","PROMPT_RECEIVED","PROMPT_ACCEPTED","PROMPT_REJECTED","TRANSITION_PREPARED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED","CHECKPOINT_INTENT","CHECKPOINT_ABORTED","RECOVERY_PERFORMED"}
HEX=re.compile(r"^[0-9a-f]{64}$")
CONTEXT_PATH=re.compile(r"^reports/contexts/[A-Za-z0-9][A-Za-z0-9._-]*\.txt$")
SAFE_CONTEXT=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
CONTEXT_HEADER="Atlas-generated context supplement\n\nPrevious generation artifacts:\n"
_CONTEXT_LINE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
def canonical_context_identifier(value):
    """Return the representation permitted in a supplement, or omit it."""
    return value if isinstance(value,str) and _CONTEXT_LINE.fullmatch(value) else None
def canonical_execution_result(record):
    """Select the durable executor result used for historical context."""
    terminal=(record.get("result") if isinstance(record.get("result"),dict) else {})
    if isinstance(terminal.get("executor_result"),dict): return terminal["executor_result"]
    if isinstance(record.get("execution_result"),dict): return record["execution_result"]
    return {}
def encode_context_supplement(form):
    """Encode the single canonical parent-context representation."""
    if form["kind"] == "none": return CONTEXT_HEADER+"- unavailable: no immediate parent artifact\n"
    lines=[f"- generation: {form['generation']}", f"- action: {form['action']}", f"- status: {form['status']}"]
    if form["kind"] == "checkpoint":
        if form.get("commit"): lines.append(f"- commit: {form['commit']}")
    else:
        if form.get("execution_id"): lines.append(f"- execution_id: {form['execution_id']}")
        if form.get("thread_id"): lines.append(f"- thread_id: {form['thread_id']}")
        available=form["report_available"]
        lines.append(f"- report: {'available' if available else 'unavailable'}")
        if available: lines.append(f"- report command: python -m tools.atlas_agent report {form['generation']}")
    return CONTEXT_HEADER+"\n".join(lines)+"\n"
def decode_context_supplement(value):
    if value == encode_context_supplement({"kind":"none"}): return {"kind":"none"}
    if not isinstance(value,str) or not value.startswith(CONTEXT_HEADER): raise JournalError("context supplement invalid")
    lines=value[len(CONTEXT_HEADER):].splitlines()
    if len(lines)<3 or any(not line.startswith("- ") for line in lines): raise JournalError("context supplement invalid")
    fields={line[2:].split(": ",1)[0]:line[2:].split(": ",1)[1] for line in lines if ": " in line[2:]}
    if any(k not in {"generation","action","status","commit","execution_id","thread_id","report","report command"} for k in fields): raise JournalError("context supplement invalid")
    if set(fields)-{"generation","action","status","commit","execution_id","thread_id","report","report command"} or fields.get("generation","") != lines[0][2:].split(": ",1)[1]: raise JournalError("context supplement invalid")
    try: generation=int(fields["generation"])
    except (KeyError,ValueError): raise JournalError("context supplement invalid")
    if generation<=0 or not _CONTEXT_LINE.fullmatch(fields.get("action","")) or not _CONTEXT_LINE.fullmatch(fields.get("status","")): raise JournalError("context supplement invalid")
    if fields.get("action")=="checkpoint":
        if set(fields)-{"generation","action","status","commit"} or ("commit" in fields and not re.fullmatch(r"[0-9a-f]{40,64}",fields["commit"])): raise JournalError("context supplement invalid")
        return {"kind":"checkpoint","generation":generation,"action":"checkpoint","status":fields["status"],"commit":fields.get("commit")}
    if "commit" in fields or "report" not in fields or fields["report"] not in {"available","unavailable"}: raise JournalError("context supplement invalid")
    if "report command" in fields and fields["report"]!="available": raise JournalError("context supplement invalid")
    if "report command" in fields and fields["report command"] != f"python -m tools.atlas_agent report {generation}": raise JournalError("context supplement invalid")
    for k in ("execution_id","thread_id"):
        if k in fields and not _CONTEXT_LINE.fullmatch(fields[k]): raise JournalError("context supplement invalid")
    result={"kind":"execution","generation":generation,"action":fields["action"],"status":fields["status"],"execution_id":fields.get("execution_id"),"thread_id":fields.get("thread_id"),"report_available":fields["report"]=="available"}
    if encode_context_supplement(result)!=value: raise JournalError("context supplement is not canonical")
    return result
def canonical(obj:Any)->str: return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _hash_event(e):
    body=dict(e); body.pop("event_sha256",None)
    return hashlib.sha256(canonical(body).encode()).hexdigest()
def _timestamp(value):
    if type(value) is not str: return False
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError: return False
def _witness(value, line):
    if type(value) is not dict or set(value)!={"head","branch","index_semantic_sha256","tracked_worktree_sha256","tracked_worktree_content_sha256","unexpected_untracked"}: raise JournalError(f"witness invalid at line {line}")
    if type(value["head"]) is not str or not re.fullmatch(r"[0-9a-f]{40,64}",value["head"]): raise JournalError(f"witness HEAD invalid at line {line}")
    if value["branch"] is not None and type(value["branch"]) is not str: raise JournalError(f"witness branch invalid at line {line}")
    for key in ("index_semantic_sha256","tracked_worktree_sha256","tracked_worktree_content_sha256"):
        if type(value[key]) is not str or not HEX.fullmatch(value[key]): raise JournalError(f"witness hash invalid at line {line}")
    untracked=value["unexpected_untracked"]
    if type(untracked) is not list or any(type(x) is not dict or set(x)!={"path","content_sha256"} or type(x["path"]) is not str or not re.fullmatch(r"(?:[0-9a-f]{2})+",x["path"]) or type(x["content_sha256"]) is not str or not HEX.fullmatch(x["content_sha256"]) for x in untracked): raise JournalError(f"witness untracked invalid at line {line}")
    if untracked!=sorted(untracked,key=lambda x:x["path"]) or len({x["path"] for x in untracked})!=len(untracked): raise JournalError(f"witness untracked invalid at line {line}")
def _execution(value,line):
    if type(value) is not dict or not {"execution_id","executor","started_at","pid","report_dir"}<=set(value): raise JournalError(f"execution metadata invalid at line {line}")
    if set(value)-{"execution_id","executor","started_at","pid","report_dir","permission_envelope","owner_schema","policy_snapshot","provenance_version","execution_input_sha256","report_provenance","prompt_input","context_path","effective_prompt_path","context_sha256","effective_prompt_sha256","sandbox","execution_backend_schema"}: raise JournalError(f"execution metadata invalid at line {line}")
    if type(value["execution_id"]) is not str or not value["execution_id"] or type(value["executor"]) is not str or type(value["started_at"]) is not str or (value["pid"] is not None and type(value["pid"]) is not int) or type(value["report_dir"]) is not str: raise JournalError(f"execution metadata types invalid at line {line}")
    provenance={"prompt_input","context_path","effective_prompt_path","context_sha256","effective_prompt_sha256"}
    present=provenance & set(value)
    if present and present != provenance: raise JournalError(f"execution provenance incomplete at line {line}")
    if present:
        if value["prompt_input"] != "accepted_prompt_plus_atlas_context": raise JournalError(f"execution prompt input invalid at line {line}")
        for key in ("context_path","effective_prompt_path"):
            if type(value[key]) is not str or not CONTEXT_PATH.fullmatch(value[key]): raise JournalError(f"execution context path invalid at line {line}")
        context_name=value["context_path"].removeprefix("reports/contexts/")
        effective_name=value["effective_prompt_path"].removeprefix("reports/contexts/")
        if not context_name.endswith(".txt") or context_name[:-4] != value["execution_id"] or effective_name != context_name[:-4]+"-effective.txt": raise JournalError(f"execution context paths invalid at line {line}")
        if any(type(value[key]) is not str or not HEX.fullmatch(value[key]) for key in ("context_sha256","effective_prompt_sha256")): raise JournalError(f"execution provenance hash invalid at line {line}")
    modern_fields={"provenance_version","execution_input_sha256","report_provenance"}
    if modern_fields & set(value):
        if value.get("provenance_version") != 2 or type(value.get("execution_input_sha256")) is not str or not HEX.fullmatch(value["execution_input_sha256"]):
            raise JournalError(f"execution provenance version invalid at line {line}")
        if present != provenance:
            raise JournalError(f"execution provenance incomplete at line {line}")
        descriptor=value.get("report_provenance")
        if not isinstance(descriptor,dict) or descriptor != {"status":"unavailable"}:
            raise JournalError(f"execution report provenance invalid at line {line}")
    if "permission_envelope" in value:
        envelope=value["permission_envelope"]
        if type(envelope) is not dict or set(envelope)!={"sandbox_mode","approval_policy","approvals_reviewer","strict_config","ignore_rules","network_access"}: raise JournalError(f"permission envelope invalid at line {line}")
        if envelope["sandbox_mode"] not in {"read-only","workspace-write","danger-full-access"} or envelope["approval_policy"]!="never" or envelope["approvals_reviewer"]!="user" or envelope["strict_config"] is not True or envelope["ignore_rules"] is not True or type(envelope["network_access"]) is not bool: raise JournalError(f"permission envelope invalid at line {line}")
    if "owner_schema" in value or "policy_snapshot" in value:
        if value.get("owner_schema")!="atlas-agent-execution-owner/2" or "policy_snapshot" not in value: raise JournalError(f"execution owner schema invalid at line {line}")
        try: validate_snapshot(value["policy_snapshot"])
        except PolicyError as error: raise JournalError(f"policy snapshot invalid at line {line}") from error
    modern_bwrap = value.get("execution_backend_schema") == "atlas-bwrap-execution/1"
    if "execution_backend_schema" in value and not modern_bwrap:
        raise JournalError(f"execution backend schema invalid at line {line}")
    if "sandbox" in value:
        descriptor = value["sandbox"]
        required = {"schema","provider","backend","filesystem_mode","filesystem_enforcement",
                    "process_enforcement","network_enforcement","requested_network_access",
                    "resolved_network_access","user_namespace","pid_namespace","ipc_namespace",
                    "mount_roles","temporary_storage","bwrap","bwrap_version","codex_executable",
                    "codex_version","scratch_backing_class","exec_server_transport","inner_codex_sandbox","inner_codex_network"}
        if type(descriptor) is not dict or set(descriptor) != required:
            raise JournalError(f"sandbox provenance invalid at line {line}")
        if descriptor["schema"] != "atlas-bwrap/1" or descriptor["provider"] != "atlas" or descriptor["backend"] != "bubblewrap":
            raise JournalError(f"sandbox provenance invalid at line {line}")
        if descriptor["filesystem_mode"] not in {"read-only","workspace-write"}:
            raise JournalError(f"sandbox action mismatch at line {line}")
        if descriptor["filesystem_enforcement"] != "atlas-bwrap":
            raise JournalError(f"sandbox filesystem enforcement mismatch at line {line}")
        if descriptor["process_enforcement"] != "atlas-bwrap":
            raise JournalError(f"sandbox process enforcement mismatch at line {line}")
        if descriptor["network_enforcement"] != "codex":
            raise JournalError(f"sandbox network enforcement mismatch at line {line}")
        requested_network = descriptor["requested_network_access"]
        resolved_network = descriptor["resolved_network_access"]
        if type(requested_network) is not bool or type(resolved_network) is not bool or requested_network != resolved_network:
            raise JournalError(f"sandbox network mismatch at line {line}")
        envelope = value.get("permission_envelope")
        if isinstance(envelope, dict) and envelope.get("network_access") is not resolved_network:
            raise JournalError(f"sandbox network mismatch at line {line}")
        snapshot = value.get("policy_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("network_access") is not resolved_network:
            raise JournalError(f"sandbox network mismatch at line {line}")
        if descriptor["pid_namespace"] is not True or descriptor["ipc_namespace"] is not True or descriptor["user_namespace"] != "bwrap-default":
            raise JournalError(f"sandbox provenance invalid at line {line}")
        if type(descriptor["mount_roles"]) is not list or len(descriptor["mount_roles"]) > 64 or any(type(x) is not str or len(x)>128 for x in descriptor["mount_roles"]):
            raise JournalError(f"sandbox provenance invalid at line {line}")
        if descriptor["temporary_storage"] != {"tmp":"private-tmpfs","shm":"private-tmpfs","var_tmp":"private-disk-scratch"}:
            raise JournalError(f"sandbox provenance invalid at line {line}")
        if descriptor["scratch_backing_class"] != "disk":
            raise JournalError(f"sandbox provenance invalid at line {line}")
        for key in ("bwrap","bwrap_version","codex_executable","codex_version","exec_server_transport","inner_codex_sandbox","inner_codex_network"):
            if type(descriptor[key]) is not str or not descriptor[key] or len(descriptor[key]) > 512:
                raise JournalError(f"sandbox provenance invalid at line {line}")
        if descriptor["inner_codex_sandbox"] != descriptor["filesystem_mode"]:
            raise JournalError(f"sandbox action mismatch at line {line}")
        expected_inner_network = "enabled" if descriptor["resolved_network_access"] else "restricted"
        if descriptor["inner_codex_network"] != expected_inner_network:
            raise JournalError(f"sandbox network mismatch at line {line}")
    if modern_bwrap and "sandbox" not in value:
        raise JournalError(f"sandbox provenance missing at line {line}")

def _validate_parent_context(form, generation, generations, line):
    """Check durable parent semantics as they existed before this event."""
    if form["kind"] == "none":
        if generation != 1: raise JournalError(f"context supplement parent mismatch at line {line}")
        return
    parent=generations.get(generation-1)
    if parent is None: raise JournalError(f"context supplement parent mismatch at line {line}")
    expected_kind="checkpoint" if parent["action"]=="checkpoint" else "execution"
    if form["kind"] != expected_kind or form["generation"] != parent["generation"]:
        raise JournalError(f"context supplement parent semantics invalid at line {line}")
    if form["action"] != parent["action"] or form["status"] != parent["status"]:
        raise JournalError(f"context supplement parent semantics invalid at line {line}")
    if expected_kind == "checkpoint":
        commit=(parent.get("result") or {}).get("commit_sha")
        if form.get("commit") != commit:
            raise JournalError(f"context supplement parent checkpoint invalid at line {line}")
        return
    execution=parent.get("execution") or {}
    result=canonical_execution_result(parent)
    if form.get("execution_id") != canonical_context_identifier(execution.get("execution_id")):
        raise JournalError(f"context supplement parent execution invalid at line {line}")
    if form.get("thread_id") != canonical_context_identifier(result.get("session_id")):
        raise JournalError(f"context supplement parent thread invalid at line {line}")
    if execution.get("provenance_version") == 2:
        descriptor=(parent.get("result") or {}).get("report_provenance")
        if not isinstance(descriptor,dict) or descriptor.get("status") not in {"available","unavailable"}:
            raise JournalError(f"context supplement parent report provenance invalid at line {line}")
        if form.get("report_available") != (descriptor["status"] == "available"):
            raise JournalError(f"context supplement parent report claim invalid at line {line}")

class Journal:
    def __init__(self,path:Path): self.path=path

    def _archived_prompt(self, prompt_sha256, line):
        """Return the hash-bound immutable parsed prompt."""
        archive=self.path.parent / "prompts" / f"{prompt_sha256}.txt"
        try:
            raw=archive.read_bytes()
        except OSError as error:
            raise JournalError(f"prompt archive unavailable at line {line}") from error
        if hashlib.sha256(raw).hexdigest()!=prompt_sha256:
            raise JournalError(f"prompt archive hash mismatch at line {line}")
        try:
            return parse_prompt(raw)
        except PromptError as error:
            raise JournalError(f"prompt archive invalid at line {line}") from error

    def _archived_prompt_schema(self, prompt_sha256, line):
        return self._archived_prompt(prompt_sha256, line).prompt_schema
    def read(self):
        if not self.path.exists(): return []
        out=[]; previous=ZERO; generations={}; outstanding={}; validation_epoch=1; initialized=False
        with self.path.open("r",encoding="utf-8",newline="") as f:
            for n,line in enumerate(f,1):
                if not line.endswith("\n"): raise JournalError(f"journal line {n} is not newline terminated")
                try: raw=json.loads(line)
                except json.JSONDecodeError as x: raise JournalError(f"invalid JSON at line {n}: {x}") from x
                if type(raw) is not dict or set(raw)!={"schema","seq","timestamp","event","payload","previous_event_sha256","event_sha256"}: raise JournalError(f"journal schema/fields invalid at line {n}")
                if raw["schema"]!=SCHEMA or type(raw["seq"]) is not int or raw["seq"]!=n: raise JournalError(f"journal schema/sequence invalid at line {n}")
                if not _timestamp(raw["timestamp"]): raise JournalError(f"timestamp invalid at line {n}")
                if raw["event"] not in EVENTS or type(raw["payload"]) is not dict: raise JournalError(f"event invalid at line {n}")
                if raw["previous_event_sha256"]!=previous or not HEX.fullmatch(raw["previous_event_sha256"]): raise JournalError(f"journal chain broken at line {n}")
                if type(raw["event_sha256"]) is not str or not HEX.fullmatch(raw["event_sha256"]) or _hash_event(raw)!=raw["event_sha256"]: raise JournalError(f"event hash broken at line {n}")
                if raw["event"] == "WORKFLOW_INITIALIZED":
                    if n != 1 or initialized:
                        raise JournalError(f"workflow initialization must be the unique root event at line {n}")
                    epoch = raw["payload"].get("validation_epoch", 1)
                    if type(epoch) is not int or epoch not in {1, 2}: raise JournalError(f"validation epoch invalid at line {n}")
                    validation_epoch = epoch
                    initialized=True
                archived_prompt=None
                if raw["event"] == "PROMPT_ACCEPTED":
                    archived_prompt=self._archived_prompt(raw["payload"]["prompt_sha256"],n)
                    archived_schema=archived_prompt.prompt_schema
                    journal_schema=raw["payload"].get("prompt_schema")
                    if journal_schema is not None and journal_schema != archived_schema:
                        raise JournalError(f"prompt schema archive mismatch at line {n}")
                    if archived_schema == "atlas-agent-prompt/2":
                        if journal_schema != archived_schema:
                            raise JournalError(f"prompt schema archive mismatch at line {n}")
                        if (
                            "network_access" not in raw["payload"]
                            or raw["payload"]["network_access"] is not archived_prompt.network_access
                        ):
                            raise JournalError(f"prompt network archive mismatch at line {n}")
                self._validate_payload(raw["event"],raw["payload"],n, generations, validation_epoch)
                p=raw["payload"]
                if raw["event"]=="TRANSITION_PREPARED": outstanding[p["transaction_id"]]=p
                elif raw["event"] in {"PROMPT_ACCEPTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"}:
                    prepared=outstanding.pop(p["transaction_id"],None)
                    if raw["event"]=="PROMPT_ACCEPTED":
                        generations[p["generation"]]={
                            "generation":p["generation"],
                            "action":p["action"],
                            "status":"ACCEPTED",
                            "prompt_schema":p.get("prompt_schema"),
                            "network_access": (
                                archived_prompt.network_access
                                if archived_prompt is not None
                                and archived_prompt.prompt_schema == "atlas-agent-prompt/2"
                                else False
                            ),
                        }
                    elif raw["event"]=="RUN_STARTED":
                        rec=generations.get(p["generation"])
                        if rec: rec.update({"status":"RUNNING","execution":p.get("execution")})
                    elif raw["event"] in {"RUN_COMPLETED","RUN_INTERRUPTED"}:
                        rec=generations.get(p["generation"])
                        if rec:
                            rec["status"]="COMPLETED" if raw["event"]=="RUN_COMPLETED" else "INTERRUPTED"
                            if "result" in p: rec["result"]=p["result"]
                            if "executor_result" in p: rec["execution_result"]=p["executor_result"]
                previous=raw["event_sha256"]; out.append(raw)
        if out and not initialized:
            raise JournalError("nonempty journal must have workflow initialization root")
        return out
    @staticmethod
    def _validate_payload(event,p,n,generations=None,validation_epoch=1):
        required={"WORKFLOW_INITIALIZED":{"repository_root","head","branch","witness"},"PROMPT_RECEIVED":{"prompt_sha256","source"},"PROMPT_REJECTED":{"transaction_id","source","destination","prompt_sha256","reason_code","reason"},"PROMPT_ACCEPTED":{"transaction_id","source","destination","generation","parent","prompt_sha256","action","checkpoint","session_mode","expected_head","witness"},"TRANSITION_PREPARED":{"transaction_id","logical_event","source","destination","prompt_sha256"},"RUN_STARTED":{"transaction_id","source","destination","generation","prompt_sha256","action"},"RUN_COMPLETED":{"transaction_id","source","destination","generation","prompt_sha256","action","result","witness"},"RUN_INTERRUPTED":{"transaction_id","source","destination","generation","prompt_sha256","action","reason"},"CHECKPOINT_INTENT":{"generation","prompt_sha256","parent_head","tree_sha","commit_sha","witness"},"CHECKPOINT_ABORTED":{"generation","prompt_sha256","commit_sha","reason"},"RECOVERY_PERFORMED":set()}[event]
        if not required<=set(p): raise JournalError(f"payload for {event} incomplete at line {n}")
        allowed={
            "WORKFLOW_INITIALIZED":{"repository_root","head","branch","witness","validation_epoch"},
            "PROMPT_RECEIVED":{"prompt_sha256","source"},
            "PROMPT_REJECTED":{"transaction_id","source","destination","prompt_sha256","reason_code","reason"},
            "PROMPT_ACCEPTED":{"transaction_id","source","destination","generation","parent","prompt_sha256","action","checkpoint","session_mode","expected_head","witness","prompt_schema","network_access","reuse_execution_id"},
            "TRANSITION_PREPARED":{"transaction_id","logical_event","source","destination","prompt_sha256","generation","parent","action","checkpoint","session_mode","expected_head","witness","result","reason","reason_code","execution","prompt_schema","network_access","reuse_execution_id","executor_result","fallback_artifacts","acquired_untracked"},
            "RUN_STARTED":{"transaction_id","source","destination","generation","prompt_sha256","action","execution","witness","network_access"},
            "RUN_COMPLETED":{"transaction_id","source","destination","generation","prompt_sha256","action","result","witness","execution","acquired_untracked"},
            "RUN_INTERRUPTED":{"transaction_id","source","destination","generation","prompt_sha256","action","reason","execution","result","executor_result","fallback_artifacts"},
            "CHECKPOINT_INTENT":{"generation","prompt_sha256","parent_head","tree_sha","commit_sha","witness"},
            "CHECKPOINT_ABORTED":{"generation","prompt_sha256","commit_sha","reason"},
            "RECOVERY_PERFORMED":{"repaired"},
        }[event]
        if event in {"TRANSITION_PREPARED", "RUN_STARTED"}: allowed=allowed | {"context_supplement"}
        if not set(p)<=allowed: raise JournalError(f"payload fields invalid for {event} at line {n}")
        if event in {"PROMPT_RECEIVED","PROMPT_REJECTED","PROMPT_ACCEPTED","TRANSITION_PREPARED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED","CHECKPOINT_INTENT","CHECKPOINT_ABORTED"} and (type(p.get("prompt_sha256")) is not str or not HEX.fullmatch(p["prompt_sha256"])): raise JournalError(f"prompt hash invalid at line {n}")
        if event in {"PROMPT_ACCEPTED","PROMPT_REJECTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"} and (type(p.get("transaction_id")) is not str or not p["transaction_id"]): raise JournalError(f"transaction id missing at line {n}")
        if event=="TRANSITION_PREPARED" and p.get("logical_event") not in {"PROMPT_ACCEPTED","PROMPT_REJECTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"}: raise JournalError(f"logical event invalid at line {n}")
        if event in {"WORKFLOW_INITIALIZED","PROMPT_ACCEPTED","RUN_COMPLETED"}: _witness(p["witness"],n)
        if event == "RUN_STARTED" and "witness" in p: _witness(p["witness"],n)
        if event == "RUN_COMPLETED" and "acquired_untracked" in p:
            acquired=p["acquired_untracked"]
            if (type(acquired) is not list or acquired != sorted(acquired) or
                len(acquired) != len(set(acquired)) or
                any(type(path) is not str or not re.fullmatch(r"(?:[0-9a-f]{2})+", path) for path in acquired)):
                raise JournalError(f"acquired ownership invalid at line {n}")
        if event=="WORKFLOW_INITIALIZED" and (type(p["repository_root"]) is not str or type(p["head"]) is not str or not re.fullmatch(r"[0-9a-f]{40,64}",p["head"]) or (p["branch"] is not None and type(p["branch"]) is not str) or type(p.get("validation_epoch",1)) is not int or p.get("validation_epoch",1) not in {1,2}): raise JournalError(f"initialization payload invalid at line {n}")
        if event in {"PROMPT_ACCEPTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED","CHECKPOINT_INTENT","CHECKPOINT_ABORTED"} and (type(p.get("generation")) is not int or p["generation"]<=0): raise JournalError(f"generation invalid at line {n}")
        if event=="PROMPT_ACCEPTED" and (type(p["parent"]) not in (int,str) or type(p["checkpoint"]) is not str or type(p["action"]) is not str or type(p["session_mode"]) is not str or type(p["expected_head"]) is not str): raise JournalError(f"prompt metadata invalid at line {n}")
        if event=="PROMPT_ACCEPTED":
            if "prompt_schema" in p and p["prompt_schema"] not in {"atlas-agent-prompt/1", "atlas-agent-prompt/2"}: raise JournalError(f"prompt schema invalid at line {n}")
            if "network_access" in p and type(p["network_access"]) is not bool: raise JournalError(f"prompt network invalid at line {n}")
            if "reuse_execution_id" in p and (type(p["reuse_execution_id"]) is not str or not p["reuse_execution_id"]): raise JournalError(f"prompt reuse target invalid at line {n}")
        if event=="RUN_COMPLETED" and type(p["result"]) is not dict: raise JournalError(f"result invalid at line {n}")
        started=(generations or {}).get(p.get("generation")) or (generations or {}).get(str(p.get("generation")))
        started_execution=started.get("execution") if isinstance(started,dict) else None

        if (
            isinstance(started,dict)
            and started.get("prompt_schema") == "atlas-agent-prompt/2"
            and (
                event == "RUN_STARTED"
                or (
                    event == "TRANSITION_PREPARED"
                    and p.get("logical_event") == "RUN_STARTED"
                )
            )
        ):
            expected_network=started.get("network_access")
            if (
                type(expected_network) is not bool
                or "network_access" not in p
                or p["network_access"] is not expected_network
            ):
                raise JournalError(f"prompt network provenance mismatch at line {n}")
        # The prompt schema is durable transaction provenance.  It must remain
        # authoritative even if an attacker removes every v2 field from the
        # execution/result copies.
        # A hash-bound archived v2 prompt is durable modern evidence.  The
        # mutable root epoch may preserve legacy compatibility, but cannot
        # weaken the semantics proven by that prompt archive.
        explicit_legacy = isinstance(started, dict) and started.get("prompt_schema") == "atlas-agent-prompt/1"
        archived_v2 = isinstance(started, dict) and started.get("prompt_schema") == "atlas-agent-prompt/2"
        v2=archived_v2 or (validation_epoch >= 2 and not explicit_legacy)

        # A hash-bound v2 prompt is positive modern evidence.  Modern execution
        # ownership must not be inferred from optional fields that can be
        # removed from the journal.
        start_event = (
            event == "RUN_STARTED"
            or (
                event == "TRANSITION_PREPARED"
                and p.get("logical_event") == "RUN_STARTED"
            )
        )
        terminal_event = event in {"RUN_COMPLETED","RUN_INTERRUPTED"}
        terminal_with_owner = terminal_event and started_execution is not None

        if archived_v2 and (start_event or terminal_with_owner):
            execution=p.get("execution")
            if not isinstance(execution,dict):
                raise JournalError(f"modern execution ownership missing at line {n}")

            if execution.get("owner_schema") != "atlas-agent-execution-owner/2":
                raise JournalError(f"modern execution owner schema missing at line {n}")

            snapshot=execution.get("policy_snapshot")
            try:
                validate_snapshot(snapshot)
            except PolicyError as error:
                raise JournalError(f"modern policy snapshot invalid at line {n}") from error
            if (
                not isinstance(snapshot,dict)
                or snapshot.get("schema") != "atlas-agent-policy-snapshot/2"
            ):
                raise JournalError(f"modern policy snapshot invalid at line {n}")

            envelope=execution.get("permission_envelope")
            if not isinstance(envelope,dict):
                raise JournalError(f"modern permission envelope missing at line {n}")
            if (
                envelope.get("network_access") is not snapshot.get("network_access")
                or envelope.get("sandbox_mode") != snapshot.get("sandbox_mode")
            ):
                raise JournalError(f"modern permission envelope mismatch at line {n}")

            if start_event and (
                "network_access" not in p
                or p["network_access"] is not snapshot.get("network_access_requested")
            ):
                raise JournalError(f"modern network request mismatch at line {n}")

            # Real Codex executions must carry the concrete sandbox backend;
            # FakeExecutor histories used by deterministic tests are not
            # reclassified as Bubblewrap executions.
        if event == "RUN_STARTED" and isinstance(p.get("execution"),dict) and p["execution"].get("provenance_version")==2 and p["execution"].get("execution_input_sha256") != p["execution"].get("effective_prompt_sha256"):
            raise JournalError(f"execution handoff digest mismatch at line {n}")
        if event in {"RUN_COMPLETED","RUN_INTERRUPTED"} and v2 and started_execution is not None:
            if p.get("execution") != started_execution:
                raise JournalError(f"TERMINAL_EXECUTION_MISMATCH at line {n}")
            if not isinstance(p.get("result"),dict):
                raise JournalError(f"terminal v2 provenance incomplete at line {n}")
            if started_execution.get("execution_input_sha256") != started_execution.get("effective_prompt_sha256"):
                raise JournalError(f"execution handoff digest mismatch at line {n}")
            if event == "RUN_COMPLETED":
                observed=p.get("result",{}).get("executor_result")
                if not isinstance(observed,dict) or observed.get("execution_input_sha256") != started_execution.get("execution_input_sha256"):
                    raise JournalError(f"execution handoff digest mismatch at line {n}")
        if event in {"RUN_COMPLETED","RUN_INTERRUPTED"} and isinstance(p.get("execution"),dict) and p["execution"].get("provenance_version")==2:
            descriptor=p["result"].get("report_provenance")
            if not isinstance(descriptor,dict) or descriptor.get("status") not in {"available","unavailable"} or set(descriptor)-{"status","report_sha256"}:
                raise JournalError(f"report provenance invalid at line {n}")
            if descriptor["status"]=="available" and (type(descriptor.get("report_sha256")) is not str or not HEX.fullmatch(descriptor["report_sha256"])):
                raise JournalError(f"report provenance invalid at line {n}")
            if descriptor["status"]=="unavailable" and "report_sha256" in descriptor:
                raise JournalError(f"report provenance invalid at line {n}")
        if event in {"CHECKPOINT_INTENT","CHECKPOINT_ABORTED"} and (type(p["commit_sha"]) is not str or not re.fullmatch(r"[0-9a-f]{40,64}",p["commit_sha"])): raise JournalError(f"checkpoint commit invalid at line {n}")
        if event=="CHECKPOINT_INTENT" and any(type(p[k]) is not str or not re.fullmatch(r"[0-9a-f]{40,64}",p[k]) for k in ("parent_head","tree_sha")): raise JournalError(f"checkpoint intent invalid at line {n}")
        if event=="CHECKPOINT_ABORTED" and type(p["reason"]) is not str: raise JournalError(f"checkpoint abort invalid at line {n}")
        if "executor_result" in p and type(p["executor_result"]) is not dict: raise JournalError(f"executor result invalid at line {n}")
        if "fallback_artifacts" in p:
            fallback=p["fallback_artifacts"]
            if type(fallback) is not list or not fallback or len(fallback)!=len(set(fallback)) or not set(fallback)<={"stdout.log","stderr.log","result.json","usage.json"}: raise JournalError(f"fallback artifacts invalid at line {n}")
            if event=="TRANSITION_PREPARED" and p.get("logical_event")!="RUN_INTERRUPTED": raise JournalError(f"fallback artifacts invalid at line {n}")
        if event in {"PROMPT_REJECTED","PROMPT_ACCEPTED","TRANSITION_PREPARED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"} and (type(p["source"]) is not str or type(p["destination"]) is not str): raise JournalError(f"transition paths invalid at line {n}")
        if "witness" in p: _witness(p["witness"],n)
        if "execution" in p:
            _execution(p["execution"],n)
            execution=p["execution"]
            if execution.get("execution_backend_schema") == "atlas-bwrap-execution/1":
                descriptor=execution.get("sandbox")
                envelope=execution.get("permission_envelope")
                expected={"patch_review":"read-only","state_audit":"read-only","implementation":"workspace-write"}
                if not isinstance(descriptor,dict):
                    raise JournalError(f"sandbox provenance missing at line {n}")
                if p.get("action") in expected and descriptor.get("filesystem_mode") != expected[p["action"]]:
                    raise JournalError(f"sandbox action mismatch at line {n}")
                if not isinstance(envelope,dict) or descriptor.get("filesystem_mode") != envelope.get("sandbox_mode"):
                    raise JournalError(f"sandbox permission mismatch at line {n}")
                if descriptor.get("filesystem_enforcement") != "atlas-bwrap":
                    raise JournalError(f"sandbox filesystem enforcement mismatch at line {n}")
                if descriptor.get("process_enforcement") != "atlas-bwrap":
                    raise JournalError(f"sandbox process enforcement mismatch at line {n}")
                if descriptor.get("network_enforcement") != "codex":
                    raise JournalError(f"sandbox network enforcement mismatch at line {n}")
                network = envelope.get("network_access")
                snapshot = execution.get("policy_snapshot")
                if (type(network) is not bool or
                    descriptor.get("requested_network_access") is not network or
                    descriptor.get("resolved_network_access") is not network):
                    raise JournalError(f"sandbox network mismatch at line {n}")
                if isinstance(snapshot,dict):
                    if snapshot.get("network_access") is not network:
                        raise JournalError(f"sandbox network mismatch at line {n}")
                    if (
                        event=="RUN_STARTED"
                        and snapshot.get("schema")=="atlas-agent-policy-snapshot/2"
                    ):
                        if (
                            "network_access" not in p
                            or p["network_access"] is not snapshot.get("network_access_requested")
                        ):
                            raise JournalError(f"sandbox network request mismatch at line {n}")
                elif event=="RUN_STARTED" and "network_access" in p:
                    raise JournalError(f"sandbox network request mismatch at line {n}")
                expected_inner_network = "enabled" if network else "restricted"
                if descriptor.get("inner_codex_network") != expected_inner_network:
                    raise JournalError(f"sandbox network mismatch at line {n}")
                if p.get("action") in {"patch_review","state_audit"} and network:
                    raise JournalError(f"sandbox network mismatch at line {n}")
        epoch2_execution = {"provenance_version", "execution_input_sha256", "report_provenance",
                            "prompt_input", "context_path", "effective_prompt_path",
                            "context_sha256", "effective_prompt_sha256"}
        lifecycle_start = event == "RUN_STARTED"
        # Checkpoint is the one explicit non-executor lifecycle.  Every other
        # epoch-2 RUN_STARTED transaction owns an execution and its complete
        # provenance bundle; absence cannot imply a legacy/manual mode.
        # Epoch 2 must not infer legacy compatibility from missing provenance.
        # Only a durable v1 schema marker is positive evidence of a legacy
        # execution lifecycle; absent fields are corruption.
        checkpoint_start = p.get("action") == "checkpoint"
        start_transaction = (event == "RUN_STARTED" or
                             (event == "TRANSITION_PREPARED" and p.get("logical_event") == "RUN_STARTED"))
        if v2 and lifecycle_start and started is not None and p.get("action") != "checkpoint":
            if "execution" not in p:
                raise JournalError(f"epoch-2 execution provenance incomplete at line {n}")
            execution = p.get("execution")
            if not isinstance(execution, dict) or not epoch2_execution <= set(execution):
                raise JournalError(f"epoch-2 execution provenance incomplete at line {n}")
        if (v2 and start_transaction and started is not None and
            not checkpoint_start and "witness" not in p):
            raise JournalError(f"epoch-2 start witness incomplete at line {n}")
        if v2 and event in {"RUN_COMPLETED", "RUN_INTERRUPTED"} and "execution" in p:
            execution=p.get("execution")
            if not isinstance(execution,dict) or not epoch2_execution <= set(execution):
                raise JournalError(f"epoch-2 execution provenance incomplete at line {n}")
            result=p.get("result")
            if not isinstance(result,dict) or not isinstance(result.get("report_provenance"),dict):
                raise JournalError(f"epoch-2 terminal provenance incomplete at line {n}")
            if started_execution is not None and execution != started_execution:
                raise JournalError(f"terminal execution provenance mismatch at line {n}")
        provenance_fields={"prompt_input","context_path","effective_prompt_path","context_sha256","effective_prompt_sha256"}
        has_provenance=isinstance(p.get("execution"),dict) and bool(provenance_fields & set(p["execution"]))
        context_transaction=(event == "RUN_STARTED" or
                             (event == "TRANSITION_PREPARED" and p.get("logical_event") == "RUN_STARTED"))
        if context_transaction and has_provenance != ("context_supplement" in p):
            raise JournalError(f"context provenance pairing invalid at line {n}")
        if "context_supplement" in p:
            supplement=p["context_supplement"]
            if type(supplement) is not str or len(supplement.encode("utf-8")) > 4096:
                raise JournalError(f"context supplement invalid at line {n}")
            form=decode_context_supplement(supplement)
            if encode_context_supplement(form)!=supplement: raise JournalError(f"context supplement is not canonical at line {n}")
            if form["kind"] != "none" and form["generation"] != p.get("generation",0)-1: raise JournalError(f"context supplement parent mismatch at line {n}")
            if form["kind"] == "none" and p.get("generation") != 1: raise JournalError(f"context supplement parent mismatch at line {n}")
            if form["kind"] == "execution" and form["action"] == "checkpoint": raise JournalError(f"context supplement invalid at line {n}")
            if generations is not None:
                _validate_parent_context(form,p.get("generation",0),generations,n)
            execution=p.get("execution")
            if not isinstance(execution,dict) or "context_sha256" not in execution or hashlib.sha256(supplement.encode("utf-8")).hexdigest()!=execution["context_sha256"]:
                raise JournalError(f"context supplement provenance invalid at line {n}")
    def append(self,event,**fields):
        events=self.read(); seq=len(events)+1
        e={"schema":SCHEMA,"seq":seq,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"event":event,"payload":fields,"previous_event_sha256":events[-1]["event_sha256"] if events else ZERO}
        e["event_sha256"]=_hash_event(e); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as f: f.write(canonical(e)+"\n"); f.flush(); os.fsync(f.fileno())
        return e
