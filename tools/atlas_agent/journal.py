"""The append-only, strictly validated W1 journal."""
from __future__ import annotations
import hashlib, json, os, re, time
from datetime import datetime
from pathlib import Path
from typing import Any
from .model import SCHEMA
class JournalError(RuntimeError): pass
ZERO="0"*64
EVENTS={"WORKFLOW_INITIALIZED","PROMPT_RECEIVED","PROMPT_ACCEPTED","PROMPT_REJECTED","TRANSITION_PREPARED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED","RECOVERY_PERFORMED"}
HEX=re.compile(r"^[0-9a-f]{64}$")
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
    if type(value["unexpected_untracked"]) is not list or any(type(x) is not str or not re.fullmatch(r"[0-9a-f]+",x) for x in value["unexpected_untracked"]): raise JournalError(f"witness untracked invalid at line {line}")
class Journal:
    def __init__(self,path:Path): self.path=path
    def read(self):
        if not self.path.exists(): return []
        out=[]; previous=ZERO
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
                self._validate_payload(raw["event"],raw["payload"],n)
                previous=raw["event_sha256"]; out.append(raw)
        return out
    @staticmethod
    def _validate_payload(event,p,n):
        required={"WORKFLOW_INITIALIZED":{"repository_root","head","branch","witness"},"PROMPT_RECEIVED":{"prompt_sha256","source"},"PROMPT_REJECTED":{"transaction_id","source","destination","prompt_sha256","reason_code","reason"},"PROMPT_ACCEPTED":{"transaction_id","source","destination","generation","parent","prompt_sha256","action","checkpoint","session_mode","expected_head","witness"},"TRANSITION_PREPARED":{"transaction_id","logical_event","source","destination","prompt_sha256"},"RUN_STARTED":{"transaction_id","source","destination","generation","prompt_sha256","action"},"RUN_COMPLETED":{"transaction_id","source","destination","generation","prompt_sha256","action","result","witness"},"RUN_INTERRUPTED":{"transaction_id","source","destination","generation","prompt_sha256","action","reason"},"RECOVERY_PERFORMED":set()}[event]
        if not required<=set(p): raise JournalError(f"payload for {event} incomplete at line {n}")
        allowed={"WORKFLOW_INITIALIZED":{"repository_root","head","branch","witness"},"PROMPT_RECEIVED":{"prompt_sha256","source"},"PROMPT_REJECTED":{"transaction_id","source","destination","prompt_sha256","reason_code","reason"},"PROMPT_ACCEPTED":{"transaction_id","source","destination","generation","parent","prompt_sha256","action","checkpoint","session_mode","expected_head","witness"},"TRANSITION_PREPARED":{"transaction_id","logical_event","source","destination","prompt_sha256","generation","parent","action","checkpoint","session_mode","expected_head","witness","result","reason","reason_code"},"RUN_STARTED":{"transaction_id","source","destination","generation","prompt_sha256","action"},"RUN_COMPLETED":{"transaction_id","source","destination","generation","prompt_sha256","action","result","witness"},"RUN_INTERRUPTED":{"transaction_id","source","destination","generation","prompt_sha256","action","reason"},"RECOVERY_PERFORMED":{"repaired"}}[event]
        if not set(p)<=allowed: raise JournalError(f"payload fields invalid for {event} at line {n}")
        if event in {"PROMPT_RECEIVED","PROMPT_REJECTED","PROMPT_ACCEPTED","TRANSITION_PREPARED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"} and (type(p.get("prompt_sha256")) is not str or not HEX.fullmatch(p["prompt_sha256"])): raise JournalError(f"prompt hash invalid at line {n}")
        if event in {"PROMPT_ACCEPTED","PROMPT_REJECTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"} and (type(p.get("transaction_id")) is not str or not p["transaction_id"]): raise JournalError(f"transaction id missing at line {n}")
        if event=="TRANSITION_PREPARED" and p.get("logical_event") not in {"PROMPT_ACCEPTED","PROMPT_REJECTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"}: raise JournalError(f"logical event invalid at line {n}")
        if event in {"WORKFLOW_INITIALIZED","PROMPT_ACCEPTED","RUN_COMPLETED"}: _witness(p["witness"],n)
        if event=="WORKFLOW_INITIALIZED" and (type(p["repository_root"]) is not str or type(p["head"]) is not str or not re.fullmatch(r"[0-9a-f]{40,64}",p["head"]) or (p["branch"] is not None and type(p["branch"]) is not str)): raise JournalError(f"initialization payload invalid at line {n}")
        if event in {"PROMPT_ACCEPTED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"} and (type(p.get("generation")) is not int or p["generation"]<=0): raise JournalError(f"generation invalid at line {n}")
        if event=="PROMPT_ACCEPTED" and (type(p["parent"]) not in (int,str) or type(p["checkpoint"]) is not str or type(p["action"]) is not str or type(p["session_mode"]) is not str or type(p["expected_head"]) is not str): raise JournalError(f"prompt metadata invalid at line {n}")
        if event=="RUN_COMPLETED" and type(p["result"]) is not dict: raise JournalError(f"result invalid at line {n}")
        if event in {"PROMPT_REJECTED","PROMPT_ACCEPTED","TRANSITION_PREPARED","RUN_STARTED","RUN_COMPLETED","RUN_INTERRUPTED"} and (type(p["source"]) is not str or type(p["destination"]) is not str): raise JournalError(f"transition paths invalid at line {n}")
        if "witness" in p: _witness(p["witness"],n)
    def append(self,event,**fields):
        events=self.read(); seq=len(events)+1
        e={"schema":SCHEMA,"seq":seq,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"event":event,"payload":fields,"previous_event_sha256":events[-1]["event_sha256"] if events else ZERO}
        e["event_sha256"]=_hash_event(e); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as f: f.write(canonical(e)+"\n"); f.flush(); os.fsync(f.fileno())
        return e
