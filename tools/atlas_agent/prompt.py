import hashlib
import re
import tomllib
from .model import Prompt, PROMPT_SCHEMA, PROMPT_SCHEMA_V2, ACTIONS, SESSIONS

class PromptError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

def parse_prompt(raw: bytes) -> Prompt:
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise PromptError("MALFORMED_UTF8", str(e))
    if not text.startswith("+++\n"):
        raise PromptError("MALFORMED_FRONT_MATTER", "prompt must start with +++")
    lines=text.splitlines(keepends=True); end=None; offset=4
    for line in lines[1:]:
        if line.rstrip("\r\n")=="+++" and line in ("+++\n","+++\r\n","+++"):
            end=offset; break
        offset += len(line)
    if end is None:
        raise PromptError("MALFORMED_FRONT_MATTER", "closing +++ is missing")
    header = text[4:end]
    try:
        data = tomllib.loads(header)
    except tomllib.TOMLDecodeError as e:
        raise PromptError("MALFORMED_FRONT_MATTER", str(e))
    schema = data.get("schema")
    if schema == PROMPT_SCHEMA:
        allowed = {"schema", "generation", "parent", "checkpoint", "action", "expected_head", "session_mode"}
    elif schema == PROMPT_SCHEMA_V2:
        allowed = {"schema", "generation", "parent", "checkpoint", "action", "expected_head", "session_mode", "network_access", "reuse_execution_id"}
    else:
        raise PromptError("UNSUPPORTED_SCHEMA", str(schema))
    unknown = set(data) - allowed
    if unknown:
        raise PromptError("UNKNOWN_FIELD", ", ".join(sorted(unknown)))
    required = {"schema", "generation", "parent", "checkpoint", "action", "expected_head", "session_mode"}
    if schema == PROMPT_SCHEMA_V2: required.add("network_access")
    missing = required - set(data)
    if missing:
        raise PromptError("MISSING_FIELD", ", ".join(sorted(missing)))
    generation = data["generation"]
    if type(generation) is not int or generation <= 0:
        raise PromptError("BAD_GENERATION", "generation must be a positive integer")
    parent = data["parent"]
    if not (parent == "genesis" or (type(parent) is int and 0 < parent < generation)):
        raise PromptError("BAD_GENERATION", "parent must be genesis or an earlier generation")
    if not isinstance(data["checkpoint"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",data["checkpoint"]):
        raise PromptError("MISSING_FIELD", "checkpoint must be non-empty")
    if type(data["action"]) is not str:
        raise PromptError("UNKNOWN_ACTION", "action must be a string")
    if data["action"] not in ACTIONS:
        raise PromptError("UNKNOWN_ACTION", str(data["action"]))
    if type(data["session_mode"]) is not str:
        raise PromptError("BAD_SESSION_MODE", "session_mode must be a string")
    if data["session_mode"] not in SESSIONS:
        raise PromptError("BAD_SESSION_MODE", str(data["session_mode"]))
    network_access = None
    reuse_execution_id = None
    if schema == PROMPT_SCHEMA_V2:
        if type(data["network_access"]) is not bool:
            raise PromptError("BAD_NETWORK_ACCESS", "network_access must be bool")
        network_access = data["network_access"]
        reuse_execution_id = data.get("reuse_execution_id")
        if data["session_mode"] == "fresh" and reuse_execution_id is not None:
            raise PromptError("REUSE_TARGET_FORBIDDEN", "fresh prompts cannot name a reuse target")
        if data["session_mode"] == "reuse" and (type(reuse_execution_id) is not str or not reuse_execution_id):
            raise PromptError("REUSE_TARGET_MISSING", "reuse prompts require reuse_execution_id")
    head = data["expected_head"]
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        raise PromptError("BAD_EXPECTED_HEAD", "expected_head must be a Git object id")
    close_len=3 if text[end:end+3]=="+++" else 3
    body_start=end+close_len
    if text[body_start:body_start+2]=="\r\n": body_start+=2
    elif text[body_start:body_start+1]=="\n": body_start+=1
    return Prompt(raw, digest, generation, parent, data["checkpoint"], data["action"], head.lower(), data["session_mode"], text[body_start:], network_access, reuse_execution_id, schema)
