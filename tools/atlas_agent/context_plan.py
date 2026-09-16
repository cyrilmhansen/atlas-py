"""The ephemeral, deliberately narrow operator context-plan adapter."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from atlas.semantic_query import (RustAnalyzerAuthority, SemanticQuery,
                                  query_rust_semantics)
from atlas.python_semantic_query import (PyrightAuthority, PythonSemanticQuery,
                                          query_python_semantics)
from .pvc import PvcPrepareRequest, PvcPrepareResult, validate_prepare_result
from .one_shot import ProcessResult
from .pvc_context import PvcContextComposition, PvcContextSelection
from .review import build_review_package
from .semantic import build_semantic_tablet
from .python_semantic import build_python_semantic_tablet

SCHEMA = "atlas-agent-context-plan/1"
SCHEMA_V2 = "atlas-agent-context-plan/2"


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ValueError("CONTEXT_PLAN_DUPLICATE_KEY")
        out[key] = value
    return out


def _finite(value):
    raise ValueError("CONTEXT_PLAN_NONFINITE_NUMBER")


def parse_context_plan(path) -> dict:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("CONTEXT_PLAN_PATH_INVALID")
    try:
        raw = path.read_bytes().decode("utf-8")
        data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_finite)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise ValueError("CONTEXT_PLAN_INVALID") from None
    schema = data.get("schema") if type(data) is dict else None
    # Check the JSON type before using membership.  In particular, a list or
    # object is unhashable and must not escape as a Python TypeError.
    if type(schema) is not str:
        raise ValueError("CONTEXT_PLAN_SCHEMA_INVALID")
    if schema not in {SCHEMA, SCHEMA_V2}:
        raise ValueError("CONTEXT_PLAN_SCHEMA_INVALID")
    if set(data) != {"schema", "members"} or type(data["members"]) is not list or not data["members"]:
        raise ValueError("CONTEXT_PLAN_SCHEMA_INVALID")
    for member in data["members"]:
        if type(member) is not dict or type(member.get("kind")) is not str:
            raise ValueError("CONTEXT_PLAN_MEMBER_INVALID")
        kind = member["kind"]
        if kind == "REVIEW":
            allowed = {"kind"}
        elif kind == "SOURCE":
            allowed = {"kind", "result_path", "tablet_ids", "purpose", "sources"}
            if set(member) - allowed or not isinstance(member.get("result_path"), str):
                raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
            if type(member.get("tablet_ids")) is not list or not member["tablet_ids"] or any(type(x) is not str or not x for x in member["tablet_ids"]):
                raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
            if type(member.get("purpose")) is not str or not member["purpose"].strip():
                raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
            if "sources" in member and (type(member["sources"]) is not list or any(type(x) is not str for x in member["sources"])):
                raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
        elif kind == "SEMANTIC":
            allowed = {"kind", "query", "executable", "version"}
            if schema == SCHEMA_V2:
                allowed.add("backend")
                if (type(member.get("backend")) is not str
                        or member["backend"] not in {"rust", "python"}):
                    raise ValueError("CONTEXT_PLAN_SEMANTIC_INVALID")
            if set(member) - allowed:
                raise ValueError("CONTEXT_PLAN_UNKNOWN_FIELD")
            q = member.get("query")
            if set(member) - allowed or type(q) is not dict or set(q) != {"kind", "path", "line", "character"}:
                raise ValueError("CONTEXT_PLAN_SEMANTIC_INVALID")
            if (type(q["kind"]) is not str
                    or q["kind"] not in {"definition", "references", "hover"}
                    or type(q["path"]) is not str):
                raise ValueError("CONTEXT_PLAN_SEMANTIC_INVALID")
            if type(q["line"]) is not int or type(q["character"]) is not int or q["line"] < 0 or q["character"] < 0:
                raise ValueError("CONTEXT_PLAN_SEMANTIC_INVALID")
            if type(member.get("executable")) is not str or not Path(member["executable"]).is_absolute():
                raise ValueError("CONTEXT_PLAN_AUTHORITY_REQUIRED")
            if schema == SCHEMA_V2 and (
                    type(member.get("version")) is not str
                    or not member["version"].strip()):
                raise ValueError("CONTEXT_PLAN_SEMANTIC_INVALID")
            if "version" in member and type(member["version"]) is not str:
                raise ValueError("CONTEXT_PLAN_SEMANTIC_INVALID")
        else:
            raise ValueError("CONTEXT_PLAN_MEMBER_KIND_INVALID")
        if set(member) - allowed:
            raise ValueError("CONTEXT_PLAN_UNKNOWN_FIELD")
    return data


def context_plan_example() -> dict:
    """An authoring template, not discovered or recommended context."""
    return {"schema": SCHEMA_V2, "members": [
        {"kind": "REVIEW"},
        {"kind": "SOURCE", "result_path": "relative/path/to/retained-pvc-result",
         "tablet_ids": ["APO-VC-000001"], "purpose": "Inspect the selected source image",
         "sources": ["atlas-agent.toml"]},
        {"kind": "SEMANTIC", "backend": "python",
         "query": {"kind": "definition", "path": "tools/atlas_agent/cli.py",
                   "line": 0, "character": 0},
         "executable": "/absolute/path/to/pyright-langserver",
         "version": "operator-supplied Pyright version"},
    ]}


def _semantic_request(plan, member):
    """Reuse backend validation without starting a server or probing its version."""
    python = plan["schema"] == SCHEMA_V2 and member["backend"] == "python"
    query_type = PythonSemanticQuery if python else SemanticQuery
    authority_type = PyrightAuthority if python else RustAnalyzerAuthority
    q = member["query"]
    query = query_type(q["kind"], q["path"], q["line"], q["character"])
    authority = authority_type(member["executable"], member.get("version"))
    return query, authority


def check_context_plan(workflow, plan: dict) -> str:
    """Static validation and request preview; no acquisition or temporary PVCs.

    This deliberately does not claim execution admission or a frozen target.
    Dispatch still revalidates and acquires every explicitly selected member.
    """
    target = workflow.preview_dispatch_target()
    lines = ["Context plan: static check OK (not dispatch readiness)",
             f"schema: {plan['schema']}", f"repository: {workflow.root}",
             "No semantic acquisition, version probe, review construction, or temporary PVC resources."]
    if target is None:
        lines.append("target: none — NO_DISPATCHABLE_GENERATION (no ACCEPTED generation)")
    else:
        lines.extend([
            f"target: g{target.generation} · {target.action} · {target.checkpoint} · ACCEPTED",
            f"expected head: {target.expected_head}",
            f"accepted prompt sha256: {target.prompt_sha256}",
        ])
    lines.extend([
        "Target is the lowest ACCEPTED generation now; not reserved. Dispatch never skips a blocked target.",
        "Requested members (plan order; rendering is TASK, DIFF, SOURCE, SEMANTIC):",
    ])
    for index, member in enumerate(plan["members"], 1):
        kind = member["kind"]
        try:
            if kind == "REVIEW":
                lines.append(f"  {index}. REVIEW — accepted TASK + exact Git DIFF (not constructed)")
            elif kind == "SOURCE":
                selection = _source(workflow.root, member)
                lines.append(f"  {index}. SOURCE — retained PNG selection validated")
                lines.append(f"     result: {json.dumps(str(selection.result.scratch_path))}")
                lines.append(f"     tablets: {json.dumps(member['tablet_ids'])}; purpose: {json.dumps(member['purpose'])}")
                lines.append(f"     sources: {json.dumps(member.get('sources') or ['atlas-agent.toml'])}")
            else:
                query, authority = _semantic_request(plan, member)
                backend = member.get("backend", "rust")
                lines.append(f"  {index}. SEMANTIC — {backend} {query.kind} {json.dumps(query.path)} line={query.line} character={query.character} (zero-based UTF-8 bytes)")
                lines.append(f"     executable: {json.dumps(authority.executable)}; version: {json.dumps(authority.version)} (operator assertion)")
        except Exception as error:
            raise ValueError(f"CONTEXT_PLAN_MEMBER_{index}_{kind}_INVALID: {error}") from error
    lines.extend([
        "Checked: schema, query/path shape, executable availability, retained SOURCE authority, accepted spool provenance.",
        "Not checked: semantic file/coordinate bounds, server identity/protocol/results, review diff, aggregate render limits, execution policy or repository admission.",
        "Dispatch acquires observations and constructs temporary REVIEW/SEMANTIC PVCs; SOURCE is borrowed, never generated.",
    ])
    return "\n".join(lines)


def _source(root, member):
    root = Path(root).resolve()
    relative = Path(member["result_path"])
    if relative.is_absolute():
        raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
    directory = (root / relative).resolve()
    try:
        directory.relative_to(root)
    except ValueError:
        raise ValueError("CONTEXT_PLAN_SOURCE_INVALID") from None
    if not directory.is_dir():
        raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
    sources = tuple(member.get("sources") or ("atlas-agent.toml",))
    # This rehydrates only the already-retained result; it never invokes PVC.
    request = PvcPrepareRequest(root, sources)
    result = PvcPrepareResult(ProcessResult(("retained-pvc-result",), "", "",
                                             0, directory / "stdout",
                                             directory / "stderr",
                                             scratch_path=directory), request)
    validated = validate_prepare_result(result)
    tablets = {tablet["id"]: tablet for tablet in
               validated.validated_snapshot.document["tablets"]}
    if any(tablet_id not in tablets for tablet_id in member["tablet_ids"]):
        raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
    # SOURCE is deliberately not a way to smuggle review or semantic tablets
    # in under a different name.
    artifacts = {artifact["artifactId"]: artifact for artifact in
                 validated.validated_snapshot.document["artifacts"]}
    if any(artifacts[tablets[tablet_id]["artifactId"]]["mediaType"] != "image/png"
           for tablet_id in member["tablet_ids"]):
        raise ValueError("CONTEXT_PLAN_SOURCE_INVALID")
    return PvcContextSelection(validated, tuple(member["tablet_ids"]),
                                member["purpose"])


def build_context_composition(workflow, plan: dict, target=None) -> PvcContextComposition:
    """Construct selections in exactly the order supplied by the operator."""
    if target is None:
        target = workflow.preview_dispatch_target()
        if target is None:
            raise ValueError("NO_DISPATCHABLE_GENERATION")
    prompt = target.prompt
    expected_head = target.expected_head
    protected = list(target.protected_untracked)
    patch_owned = list(target.patch_owned_untracked)
    selections = []
    owned_resources = []
    try:
        for member in plan["members"]:
            if member["kind"] == "REVIEW":
                package = build_review_package(workflow.root, expected_head,
                                               prompt.body, workflow.allowed,
                                                {"protected_untracked": protected,
                                                 "patch_owned_untracked": patch_owned})
                selection = package.pvc_context()
                selections.append(selection)
                owned_resources.append(selection.result.scratch_path)
            elif member["kind"] == "SOURCE":
                selections.append(_source(workflow.root, member))
            else:
                try:
                    query, authority = _semantic_request(plan, member)
                    payload = (query_python_semantics(workflow.root, authority, query)
                               if plan["schema"] == SCHEMA_V2
                               and member["backend"] == "python"
                               else query_rust_semantics(workflow.root, authority, query))
                except Exception as error:
                    # The semantic boundary has its own detailed error
                    # vocabulary; the operator boundary deliberately exposes
                    # one stable rejection class.
                    raise ValueError("CONTEXT_PLAN_SEMANTIC_INVALID") from error
                tablet = (build_python_semantic_tablet(payload)
                          if plan["schema"] == SCHEMA_V2
                          and member["backend"] == "python"
                          else build_semantic_tablet(payload))
                selection = tablet.pvc_context()
                selections.append(selection)
                owned_resources.append(selection.result.scratch_path)
        return PvcContextComposition(tuple(selections), "operator context plan",
                                     tuple(owned_resources))
    except BaseException:
        for resource in owned_resources:
            try:
                shutil.rmtree(resource, ignore_errors=True)
            except (OSError, RuntimeError):
                pass
        raise


def cleanup_context_composition(composition):
    if not isinstance(composition, PvcContextComposition):
        return
    for resource in composition.owned_resources:
        try:
            shutil.rmtree(resource, ignore_errors=True)
        except (OSError, RuntimeError):
            pass


# Small public spellings for callers that do not need to know the parser's
# implementation name.
load_context_plan = parse_context_plan
compose_context_plan = build_context_composition
