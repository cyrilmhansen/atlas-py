import argparse
import json
import sys
from datetime import datetime

from .workflow import Workflow,WorkflowError,replay_journal,witness_matches_policy
from .spool import validate_spool
from .repository import witness
from .codex_executor import CodexExecutor
from .bubblewrap import AtlasBubblewrapExecutor


def _duration(started,finished):
    if not started or not finished: return None
    try:
        start=datetime.fromisoformat(started.replace("Z","+00:00")); end=datetime.fromisoformat(finished.replace("Z","+00:00"))
        return max(0,(end-start).total_seconds())
    except (TypeError,ValueError): return None


def _elapsed(seconds):
    seconds=max(0,int(seconds))
    minutes,remainder=divmod(seconds,60); hours,minutes=divmod(minutes,60)
    if hours: return f"{hours}h {minutes:02d}m {remainder:02d}s"
    if minutes: return f"{minutes}m {remainder:02d}s"
    return f"{remainder}s"


class DispatchPresenter:
    def event(self,event):
        if event["kind"]=="dispatch_started": self._started(event)
        elif event["kind"]=="dispatch_finished": self._finished(event)

    def _started(self,event):
        snapshot=event.get("policy_snapshot") or {}; envelope=event.get("permission_envelope") or {}
        print("Atlas dispatch")
        print(f"g{event['generation']} · {event['action']} · {event.get('session_mode') or snapshot.get('session_mode') or 'session unavailable'}")
        if snapshot.get("profile"): print(f"profile {snapshot['profile']}")
        model=snapshot.get("requested_model"); reasoning=snapshot.get("requested_reasoning_effort")
        if model or reasoning:
            values=[]
            if model: values.append(f"model {model}")
            if reasoning: values.append(f"reasoning {reasoning}")
            print(" · ".join(values))
        if event.get("service_tier") == "fast":
            print("service fast")
        sandbox=envelope.get("sandbox_mode"); network=envelope.get("network_access")
        values=[]
        if sandbox: values.append(f"sandbox {sandbox}")
        if type(network) is bool: values.append(f"network {'enabled' if network else 'disabled'}")
        if values: print(" · ".join(values))
        sandbox_descriptor=event.get("sandbox") or {}
        if sandbox_descriptor.get("backend") == "bubblewrap":
            print("sandbox Atlas/bubblewrap")
            print(f"workspace {'read-only' if sandbox_descriptor.get('filesystem_mode') == 'read-only' else 'read-write'}")
            print("tmp memory · var/tmp disk")
            print("network restricted by Codex")
        if snapshot.get("session_mode")=="reuse":
            values=[]
            if snapshot.get("reused_from_execution_id"): values.append(f"execution {snapshot['reused_from_execution_id']}")
            if snapshot.get("requested_thread_id"): values.append(f"thread {snapshot['requested_thread_id']}")
            if values: print("reuse " + " · ".join(values))
        print("starting...")

    def progress(self,event):
        elapsed=_elapsed(event.get("elapsed_seconds",0))
        if event.get("kind")=="heartbeat": print(f"[{elapsed}] still running...")
        elif event.get("kind")=="agent_message":
            message=" ".join((event.get("message") or "").split())
            if len(message)>500: message=message[:497]+"..."
            print(f"[{elapsed}] {message}")

    def _finished(self,event):
        print("Atlas dispatch result")
        print(f"g{event['generation']} · {event['action']} · {event['status']}")
        duration=_duration(event.get("started_at"),event.get("finished_at"))
        if duration is not None: print(f"elapsed {_elapsed(duration)}")
        if event.get("execution_id"): print(f"execution {event['execution_id']}")
        if event.get("thread_id"): print(f"thread {event['thread_id']}")
        tokens=event.get("tokens")
        if isinstance(tokens,dict) and not isinstance(tokens.get("observations"),list):
            fields=[]
            for key,label in (("input_tokens","input"),("cached_input_tokens","cached"),("output_tokens","output"),("reasoning_output_tokens","reasoning"),("total_tokens","total")):
                if type(tokens.get(key)) is int: fields.append(f"{label} {tokens[key]}")
            if fields: print("tokens " + " · ".join(fields))
        if event.get("interruption_reason"): print(f"interruption {event['interruption_reason']}")
        print(f"report {'available' if event.get('report_available') else 'unavailable'}")


def main(argv=None):
    p=argparse.ArgumentParser(prog="atlas-agent")
    p.add_argument("command",choices=["init","ingest","rebuild-state","recover","status","doctor","history","report","start-run","complete-run","interrupt-run","checkpoint","executor-info","execute","dispatch"])
    p.add_argument("generation",nargs="?",type=int); p.add_argument("--result"); p.add_argument("--message"); p.add_argument("--reason",default="manual interruption"); p.add_argument("--model"); p.add_argument("--fast",action="store_true",help="request Codex Fast service tier for this execution"); p.add_argument("--sandbox",default="read-only",choices=["read-only","workspace-write","danger-full-access"]); p.add_argument("--network-access",action="store_true",help="explicitly request workspace-write network access"); p.add_argument("--timeout-seconds",type=float,default=300); a=p.parse_args(argv)
    try:
        w=Workflow()
        if a.command=="init": w.init()
        elif a.command=="ingest": w.ingest()
        elif a.command=="rebuild-state": w.rebuild()
        elif a.command=="recover": w.recover()
        elif a.command=="start-run": w.start_run(a.generation)
        elif a.command=="interrupt-run": w.interrupt_run(a.generation,a.reason)
        elif a.command=="checkpoint":
            if a.generation is None: raise WorkflowError("generation is required")
            if a.message is None: raise WorkflowError("--message is required")
            state=w.checkpoint(a.generation,a.message); record=state["generations"][str(a.generation)]; commit=record["result"]["commit_sha"]
            current=witness(w.root,w.allowed)
            print(f"g{a.generation} · {record['status']}")
            print(f"commit {commit[:12]} · {a.message}")
            print("repository witness " + ("MATCH" if current==state["latest_repository_witness"] else "MISMATCH"))
            print("push not performed")
        elif a.command=="report": print(w.report(a.generation))
        elif a.command=="executor-info": print(json.dumps(AtlasBubblewrapExecutor().info(),sort_keys=True,indent=2))
        elif a.command=="execute": w.execute(a.generation,AtlasBubblewrapExecutor(model=a.model,sandbox=a.sandbox,network_access=a.network_access,timeout_seconds=a.timeout_seconds,service_tier="fast" if a.fast else None))
        elif a.command=="dispatch":
            presenter=DispatchPresenter()
            executor=AtlasBubblewrapExecutor(model=a.model,sandbox=a.sandbox,network_access=a.network_access,timeout_seconds=a.timeout_seconds,service_tier="fast" if a.fast else None,progress_callback=presenter.progress)
            w.dispatch(executor,observer=presenter.event)
        elif a.command=="complete-run":
            if not a.result: raise WorkflowError("--result JSON is required")
            w.complete_run(a.generation,json.loads(a.result))
        elif a.command=="doctor":
            events,state=w._preflight(require_state=True)
            if not state["initialized"]: raise WorkflowError("WORKFLOW_NOT_INITIALIZED")
            if state["outstanding_transactions"]: raise WorkflowError("INCOMPLETE_TRANSACTION: run recover")
            current=__import__("tools.atlas_agent.repository",fromlist=["witness"]).witness(w.root,w.allowed)
            running=[x for x in state["generations"].values() if x["status"]=="RUNNING"]
            if running:
                if any(not witness_matches_policy(current,x["witness"],x["action"],running=True) for x in running): raise WorkflowError("REPOSITORY_WITNESS_MISMATCH_RUNNING")
            elif current!=state["latest_repository_witness"]: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH_BOUNDARY")
            for g,x in state["generations"].items():
                if x["status"] in {"RUNNING","COMPLETED","INTERRUPTED"} and x["action"] not in {"implementation","patch_review","state_audit","checkpoint"}: raise WorkflowError("BAD_ACTION")
            print(f"doctor: OK ({len(events)} events)")
        elif a.command=="status":
            events=w.journal.read(); state=replay_journal(events)
            semantic="MATCH"
            try: w._validate_historical_provenance(events)
            except WorkflowError: semantic="SEMANTIC_INVALID"
            print("Atlas agent workflow\njournal: OK\nstate: "+(semantic if semantic!="MATCH" else ("MATCH" if w._state_file().exists() and w._state()==state else "MISMATCH")))
            for g,x in sorted(state["generations"].items(),key=lambda z:int(z[0])): print(f"generation {g}  {x['checkpoint']}  {x['action']}  status {x['status']}")
            print("repository witness:","MATCH" if state["latest_repository_witness"]==witness(w.root,w.allowed) else "MISMATCH")
        else:
            for row in w.history():
                fields=[f"g{row['generation']}",row["action"],row["status"]]
                duration=_duration(row.get("started_at"),row.get("finished_at"))
                if duration is not None: fields.append(_elapsed(duration))
                if row.get("execution_id"): fields.append("exec "+row["execution_id"][:12])
                fields.append("report "+("yes" if row["report_available"] else "no"))
                if row.get("commit_sha"): fields.append("commit "+row["commit_sha"][:12])
                print(" · ".join(fields))
    except (WorkflowError,ValueError,OSError,RuntimeError) as e: print(f"error: {e}",file=sys.stderr); return 1
    return 0
