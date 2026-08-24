import argparse,json,sys
from .workflow import Workflow,WorkflowError,replay_journal,witness_matches_policy
from .spool import validate_spool
from .repository import witness
from .codex_executor import CodexExecutor
def main(argv=None):
    p=argparse.ArgumentParser(prog="python -m tools.atlas_agent"); p.add_argument("command",choices=["init","ingest","rebuild-state","recover","status","doctor","history","start-run","complete-run","interrupt-run","executor-info","execute"]); p.add_argument("generation",nargs="?",type=int); p.add_argument("--result"); p.add_argument("--reason",default="manual interruption"); p.add_argument("--model"); p.add_argument("--sandbox",default="read-only",choices=["read-only","workspace-write","danger-full-access"]); p.add_argument("--network-access",action="store_true",help="explicitly request workspace-write network access"); p.add_argument("--timeout-seconds",type=float,default=300); a=p.parse_args(argv)
    try:
        w=Workflow()
        if a.command=="init": w.init()
        elif a.command=="ingest": w.ingest()
        elif a.command=="rebuild-state": w.rebuild()
        elif a.command=="recover": w.recover()
        elif a.command=="start-run": w.start_run(a.generation)
        elif a.command=="interrupt-run": w.interrupt_run(a.generation,a.reason)
        elif a.command=="executor-info": print(json.dumps(CodexExecutor().info(),sort_keys=True,indent=2))
        elif a.command=="execute": w.execute(a.generation,CodexExecutor(model=a.model,sandbox=a.sandbox,network_access=a.network_access,timeout_seconds=a.timeout_seconds))
        elif a.command=="complete-run":
            if not a.result: raise WorkflowError("--result JSON is required")
            w.complete_run(a.generation,json.loads(a.result))
        elif a.command=="doctor":
            events=w.journal.read(); state=replay_journal(events)
            if not state["initialized"]: raise WorkflowError("WORKFLOW_NOT_INITIALIZED")
            if state["outstanding_transactions"]: raise WorkflowError("INCOMPLETE_TRANSACTION: run recover")
            if not w._state_file().exists() or w._state()!=state: raise WorkflowError("STATE_PROJECTION_MISMATCH")
            validate_spool(w.base,state)
            current=__import__("tools.atlas_agent.repository",fromlist=["witness"]).witness(w.root,w.allowed)
            running=[x for x in state["generations"].values() if x["status"]=="RUNNING"]
            if running:
                if any(not witness_matches_policy(current,x["witness"],x["action"],running=True) for x in running): raise WorkflowError("REPOSITORY_WITNESS_MISMATCH_RUNNING")
            elif current!=state["latest_repository_witness"]: raise WorkflowError("REPOSITORY_WITNESS_MISMATCH_BOUNDARY")
            for g,x in state["generations"].items():
                if x["status"] in {"RUNNING","COMPLETED","INTERRUPTED"} and x["action"] not in {"implementation","patch_review","state_audit","checkpoint"}: raise WorkflowError("BAD_ACTION")
            print(f"doctor: OK ({len(events)} events)")
        elif a.command=="status":
            events=w.journal.read(); state=replay_journal(events); print("Atlas agent workflow\njournal: OK\nstate: "+("MATCH" if w._state_file().exists() and w._state()==state else "MISMATCH"))
            for g,x in sorted(state["generations"].items(),key=lambda z:int(z[0])): print(f"generation {g}  {x['checkpoint']}  {x['action']}  status {x['status']}")
            print("repository witness:","MATCH" if state["latest_repository_witness"]==witness(w.root,w.allowed) else "MISMATCH")
        else:
            for e in w.journal.read():
                if e["event"] in ("RUN_COMPLETED","RUN_INTERRUPTED"): print(f"g{e['payload']['generation']} {e['payload']['action']} {e['event'].removeprefix('RUN_')}")
    except (WorkflowError,ValueError,OSError,RuntimeError) as e: print(f"error: {e}",file=sys.stderr); return 1
    return 0
