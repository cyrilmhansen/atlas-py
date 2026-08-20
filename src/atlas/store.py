from __future__ import annotations
import copy, json, sqlite3
from pathlib import Path
from .errors import AdmissionError, AtlasError, ClosedStoreError, ValidationError
from .identity import *
from .model import *
from .model import thaw
from .values import value_from_json, value_to_json
from .vocabulary import *

_STATUSES={"exact","bound","estimate","unknown"}; _POLARITIES={"positive","negative"}

class _Isolated(dict):
    """Physical-row keyed isolation, with legacy lookup by an unambiguous id."""
    def _legacy(self, key):
        if type(key) is str:
            matches=[physical for physical in self if physical[1] == key]
            if len(matches) == 1: return matches[0]
        return key
    def __contains__(self, key): return dict.__contains__(self, self._legacy(key))
    def __getitem__(self, key): return dict.__getitem__(self, self._legacy(key))

def _id(cls, raw): return cls(raw) if type(raw) is str else (_raise("identifier must be exact text"))
def _raise(msg): raise ValidationError(msg)
def _exact_text(raw, message="text must be exact and non-empty"):
    if type(raw) is not str or not raw or any(0xD800 <= ord(char) <= 0xDFFF for char in raw): raise ValidationError(message)
    return raw
def _exact_list(raw, message="value must be an exact list"):
    if type(raw) is not list: raise ValidationError(message)
    return raw

class Store:
    def __init__(self, path):
        self.path=str(path); self._db=sqlite3.connect(self.path); self._db.row_factory=sqlite3.Row; self._closed=False
        self._db.executescript("CREATE TABLE IF NOT EXISTS records (id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(kind,id)); CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS knowledge_identity (knowledge_id TEXT PRIMARY KEY, kind TEXT NOT NULL, row_id TEXT NOT NULL)")
        self._migrate_knowledge_identity()
        self.vocabulary=Vocabulary({},{}); self.descriptions={}; self.sources={}; self.rules={}; self.contexts={}; self.snapshots={}; self.records={}; self.isolated=_Isolated(); self._load()

    def _check(self):
        if self._closed: raise ClosedStoreError("store is closed")

    def _load(self):
        row=self._db.execute("SELECT payload FROM meta WHERE key='vocabulary'").fetchone()
        if row: self._configure_loaded(json.loads(row[0]))
        rows=list(self._db.execute("SELECT id,kind,payload FROM records ORDER BY CASE kind WHEN 'description' THEN 1 WHEN 'source' THEN 2 WHEN 'rule' THEN 3 WHEN 'context' THEN 4 WHEN 'property' THEN 5 WHEN 'relation' THEN 6 WHEN 'snapshot' THEN 7 ELSE 8 END, id"))
        for row in rows:
            if row["kind"] in {"description", "source", "rule", "context"}:
                self._restore_safely(row["kind"], row["id"], row["payload"])
        for row in rows:
            if row["kind"] in {"property", "relation", "snapshot"}:
                self._restore_safely(row["kind"], row["id"], row["payload"])

    def _migrate_knowledge_identity(self):
        known={row["knowledge_id"] for row in self._db.execute("SELECT knowledge_id FROM knowledge_identity")}
        rows=[]
        for row in self._db.execute("SELECT id,kind,payload FROM records WHERE kind IN ('property','relation')"):
            try:
                payload=json.loads(row["payload"])
                knowledge_id=payload.get("id")
                if type(knowledge_id) is str:
                    rows.append((knowledge_id,row["kind"],row["id"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        claimants={}
        for knowledge_id, kind, row_id in rows:
            if knowledge_id in known: continue
            claimants.setdefault(knowledge_id, []).append((kind, row_id))
        try:
            for knowledge_id, candidates in claimants.items():
                if len(candidates) == 1:
                    kind, row_id = candidates[0]
                    self._db.execute("INSERT INTO knowledge_identity(knowledge_id,kind,row_id) VALUES(?,?,?)", (knowledge_id,kind,row_id))
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def _knowledge_owner(self, knowledge_id, kind, row_id):
        owner=self._db.execute("SELECT kind,row_id FROM knowledge_identity WHERE knowledge_id=?", (knowledge_id,)).fetchone()
        if owner is None:
            return False
        return owner["kind"] == kind and owner["row_id"] == row_id

    def _restore_safely(self, kind, ident, raw):
        try:
            self._restore(kind, json.loads(raw), ident)
        except (AtlasError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.isolated[(kind, ident)]={"kind":kind,"row_id":ident,"payload":raw,"reason":str(exc)}

    def _configure_loaded(self, raw):
        predicates={}; properties={}
        for x in raw.get("predicates",[]):
            p=PredicateSpec(_id(PredicateId,x["id"]),x["version"],x["arity"],tuple(x["roles"])); predicates[(p.id.value,p.version)]=p
        for x in raw.get("properties",[]):
            p=PropertySpec(_id(PropertyId,x["id"]),x["version"],x["value"],x.get("cardinality","multivalued")); properties[(p.id.value,p.version)]=p
        self.vocabulary=Vocabulary(predicates,properties)

    def _persist(self, kind, ident, payload):
        if kind in {"property", "relation"}:
            knowledge_id=payload["id"]
            self._db.execute("INSERT INTO knowledge_identity(knowledge_id,kind,row_id) VALUES(?,?,?)", (knowledge_id,kind,ident))
        self._db.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)",(ident,kind,json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))))

    def _restore(self, kind, p, physical_id=None):
        if type(p) is not dict: raise ValidationError("persisted payload must be an object")
        if physical_id is not None and ("id" not in p or type(p["id"]) is not str or p["id"] != physical_id):
            raise ValidationError("persisted row identity disagrees with payload identity")
        if kind=="description":
            ident=_id(DescriptionId,p["id"]); label=p["label"]
            if type(label) is not str: raise ValidationError("description label must be exact text")
            self.descriptions[ident.value]=Description(ident,label)
        elif kind=="source": self.sources[p["id"]]=Source(_id(SourceId,p["id"]))
        elif kind=="context":
            enabled=tuple(_id(RuleId,x) for x in p["enabled_rules"])
            if any(x.value not in self.rules for x in enabled): raise ValidationError("invalid persisted context rule reference")
            scopes=p["visible_scopes"]
            if type(scopes) is not list or any(type(x) is not str for x in scopes): raise ValidationError("invalid persisted context scopes")
            if type(p["enabled_rules"]) is not list: raise ValidationError("invalid persisted context rules")
            self.contexts[p["id"]]=Context(_id(ContextId,p["id"]),tuple(scopes),enabled)
        elif kind=="rule":
            body=p["payload"]
            if type(body) is not dict or type(body.get("participants")) is not list or type(body.get("head")) is not dict: raise ValidationError("invalid persisted rule structure")
            head=body["head"]; pred=_id(PredicateId,head["predicate"]); version=_exact_text(head["version"])
            spec=self.vocabulary.predicates.get((pred.value,version)); participants=tuple(_rule_text(x) for x in body["participants"]); hparts=tuple(_rule_text(x) for x in head.get("participants",[]))
            if spec is None or len(participants)!=len(set(participants)) or hparts!=participants or len(hparts)!=spec.arity or head.get("polarity") not in _POLARITIES: raise ValidationError("invalid persisted rule head")
            _validate_rule_payload(body, self.vocabulary)
            if type(p["evaluation_supported"]) is not bool: raise ValidationError("invalid persisted rule evaluation status")
            self.rules[p["id"]]=Rule(_id(RuleId,p["id"]),_exact_text(p["version"]),body,p["evaluation_supported"])
        elif kind=="snapshot":
            required=("id","parent","record_ids","predicate_versions","property_versions","rule_versions","context_ids","context_definitions","rule_definitions")
            if any(field not in p for field in required): raise ValidationError("incomplete persisted snapshot")
            if type(p["record_ids"]) is not list or type(p["predicate_versions"]) is not list or type(p["property_versions"]) is not list or type(p["rule_versions"]) is not list or type(p["context_ids"]) is not list or type(p["context_definitions"]) is not list or type(p["rule_definitions"]) is not list: raise ValidationError("invalid persisted snapshot structure")
            ids=tuple(_id(KnowledgeId,x) for x in p["record_ids"])
            if any(x.value not in self.records for x in ids): raise ValidationError("snapshot references invalid or absent record")
            parent=_id(SnapshotId,p["parent"]) if p["parent"] else None
            if parent is not None and parent.value not in self.snapshots: raise ValidationError("snapshot parent is invalid or absent")
            contexts=tuple(_id(ContextId,x) for x in p["context_ids"])
            if len({x.value for x in contexts}) != len(contexts):
                raise ValidationError("snapshot context_ids contain a duplicate")
            if any(type(x) is not dict for x in p["context_definitions"]):
                raise ValidationError("invalid persisted snapshot context definition")
            if any(type(x.get("visible_scopes")) is not list or type(x.get("enabled_rules")) is not list for x in p["context_definitions"]):
                raise ValidationError("invalid persisted snapshot context definition")
            context_defs=tuple((_exact_text(x["id"]),tuple(x["visible_scopes"]),tuple(x["enabled_rules"])) for x in p["context_definitions"])
            if any(any(type(scope) is not str for scope in x[1]) or any(type(rule) is not str for rule in x[2]) for x in context_defs):
                raise ValidationError("invalid persisted snapshot context definition")
            context_def_ids=tuple(x[0] for x in context_defs)
            if len(set(context_def_ids)) != len(context_def_ids) or set(context_def_ids) != {x.value for x in contexts}:
                raise ValidationError("snapshot context definitions do not exactly match context_ids")
            if any(type(x) is not dict for x in p["rule_definitions"]):
                raise ValidationError("invalid persisted snapshot rule definition")
            if any(type(x.get("payload")) is not dict for x in p["rule_definitions"]):
                raise ValidationError("invalid persisted snapshot rule definition")
            rule_defs=tuple((_exact_text(x["id"]),_exact_text(x["version"]),json.dumps(x["payload"],ensure_ascii=False,sort_keys=True,separators=(",",":")),x["evaluation_supported"]) for x in p["rule_definitions"])
            if any(type(x[3]) is not bool for x in rule_defs):
                raise ValidationError("invalid persisted snapshot rule definition")
            rule_def_pairs=tuple((x[0],x[1]) for x in rule_defs)
            snapshot_rule_versions=tuple(tuple(x) for x in p["rule_versions"])
            if len(set(snapshot_rule_versions)) != len(snapshot_rule_versions) or len(set(rule_def_pairs)) != len(rule_def_pairs) or set(rule_def_pairs) != set(snapshot_rule_versions):
                raise ValidationError("snapshot rule definitions do not exactly match rule_versions")
            snap=Snapshot(_id(SnapshotId,p["id"]),parent,ids,tuple(tuple(x) for x in p["predicate_versions"]),tuple(tuple(x) for x in p["property_versions"]),snapshot_rule_versions,contexts,context_defs,rule_defs)
            if any((x[0],x[1]) not in self.vocabulary.predicates for x in snap.predicate_versions) or any((x[0],x[1]) not in self.vocabulary.properties for x in snap.property_versions): raise ValidationError("snapshot vocabulary environment is unresolved")
            if any(not any(r.id.value==x[0] and r.version==x[1] for r in self.rules.values()) for x in snap.rule_versions): raise ValidationError("snapshot rule environment is unresolved")
            if any(x.value not in self.contexts for x in snap.context_ids): raise ValidationError("snapshot context environment is unresolved")
            for ident, scopes, enabled in snap.context_definitions:
                current=self.contexts.get(ident)
                if current is None or current.visible_scopes != scopes or tuple(x.value for x in current.enabled_rules) != enabled:
                    if current is not None:
                        self.isolated[("context", ident)]={"kind":"context","row_id":ident,"reason":"context definition disagrees with historical snapshot"}
                        del self.contexts[ident]
                    raise ValidationError("snapshot context definition is inconsistent")
            for ident, version, payload, supported in snap.rule_definitions:
                current=self.rules.get(ident)
                if current is None or current.version != version or json.dumps(thaw(current.payload),ensure_ascii=False,sort_keys=True,separators=(",",":")) != payload or current.evaluation_supported != supported:
                    if current is not None:
                        self.isolated[("rule", ident)]={"kind":"rule","row_id":ident,"reason":"rule definition disagrees with historical snapshot"}
                        del self.rules[ident]
                    raise ValidationError("snapshot rule definition is inconsistent")
            self.snapshots[p["id"]]=snap
        elif kind=="property":
            if not self._knowledge_owner(p["id"], kind, physical_id or p["id"]): raise ValidationError("knowledge identity is not the admitted owner")
            prop=_id(PropertyId,p["property"]); version=_exact_text(p["version"]); spec=self.vocabulary.properties.get((prop.value,version))
            d=_id(DescriptionId,p["description"]); prov=tuple(_id(SourceId,x) for x in p["provenance"])
            if spec is None or d.value not in self.descriptions or any(x.value not in self.sources for x in prov) or not prov: raise ValidationError("invalid persisted property assertion references")
            value=value_from_json(p["value"],spec.value_kind)
            if not _exact_text(p["scope"]) or p["epistemic_status"] not in _STATUSES: raise ValidationError("invalid persisted property metadata")
            self.records[p["id"]]=PropertyAssertion(_id(KnowledgeId,p["id"]),d,prop,version,value,p["scope"],p["epistemic_status"],prov)
        elif kind=="relation":
            if not self._knowledge_owner(p["id"], kind, physical_id or p["id"]): raise ValidationError("knowledge identity is not the admitted owner")
            pred=_id(PredicateId,p["predicate"]); version=_exact_text(p["version"]); spec=self.vocabulary.predicates.get((pred.value,version)); parts=tuple(_id(DescriptionId,x) for x in p["participants"]); prov=tuple(_id(SourceId,x) for x in p["provenance"])
            if spec is None or len(parts)!=spec.arity or len(_unique_values(parts)) != len(parts) or any(x.value not in self.descriptions for x in parts) or any(x.value not in self.sources for x in prov) or not prov or p["polarity"] not in _POLARITIES or not _exact_text(p["scope"]) or p["epistemic_status"] not in _STATUSES: raise ValidationError("invalid persisted relation assertion")
            self.records[p["id"]]=RelationAssertion(_id(KnowledgeId,p["id"]),pred,version,parts,p["polarity"],p["scope"],p["epistemic_status"],prov)

    def configure_vocabulary(self, raw, _commit=True):
        self._check(); predicates={}; properties={}
        predicates.update(self.vocabulary.predicates); properties.update(self.vocabulary.properties)
        for x in raw.get("predicates",[]):
            p=PredicateSpec(_id(PredicateId,x["id"]),x["version"],x["arity"],tuple(x["roles"])); key=(p.id.value,p.version)
            if key in predicates and predicates[key] != p: raise AdmissionError("conflicting predicate identity/version")
            predicates[key]=p
        for x in raw.get("properties",[]):
            p=PropertySpec(_id(PropertyId,x["id"]),x["version"],x["value"],x.get("cardinality","multivalued")); key=(p.id.value,p.version)
            if key in properties and properties[key] != p: raise AdmissionError("conflicting property identity/version")
            properties[key]=p
        candidate=Vocabulary(predicates,properties)
        payload=self._vocabulary_payload(candidate)
        try:
            row=self._db.execute("SELECT payload FROM meta WHERE key='vocabulary'").fetchone()
            if row is None:
                self._db.execute("INSERT INTO meta(key,payload) VALUES('vocabulary',?)", (payload,))
            elif json.loads(row[0]) != json.loads(payload):
                self._db.execute("UPDATE meta SET payload=? WHERE key='vocabulary'", (payload,))
            if _commit: self._db.commit()
        except Exception:
            if _commit: self._db.rollback()
            raise
        self.vocabulary=candidate

    def _vocabulary_payload(self, vocabulary):
        return json.dumps({"predicates":[{"id":p.id.value,"version":p.version,"arity":p.arity,"roles":list(p.roles)} for p in vocabulary.predicates.values()],"properties":[{"id":p.id.value,"version":p.version,"value":p.value_kind,"cardinality":p.cardinality} for p in vocabulary.properties.values()]},ensure_ascii=False,sort_keys=True,separators=(",",":"))

    def _check_vocabulary_compatibility(self, candidate):
        for key, old in self.vocabulary.predicates.items():
            new=candidate.predicates.get(key)
            if new is None: raise AdmissionError("vocabulary is append-only; existing predicate version cannot disappear")
            if new != old: raise AdmissionError("conflicting predicate identity/version")
        for key, old in self.vocabulary.properties.items():
            new=candidate.properties.get(key)
            if new is None: raise AdmissionError("vocabulary is append-only; existing property version cannot disappear")
            if new != old: raise AdmissionError("conflicting property identity/version")

    def admit(self, batch, _commit=True, _publish=True):
        self._check(); batch=list(batch); descriptions=dict(self.descriptions); sources=dict(self.sources); records=dict(self.records); rules=dict(self.rules); contexts=dict(self.contexts)
        pending=[]
        try:
            for item in batch:
                kind=item["kind"]; p=item["payload"]
                if kind=="description":
                    if type(p.get("label")) is not str: raise ValidationError("description label must be exact text")
                    x=Description(_id(DescriptionId,p["id"]),p["label"]); _unique(descriptions,x.id.value,"description"); descriptions[x.id.value]=x; pending.append((kind,x.id.value,p))
                elif kind=="source":
                    x=Source(_id(SourceId,p["id"])); _unique(sources,x.id.value,"source"); sources[x.id.value]=x; pending.append((kind,x.id.value,p))
                elif kind in {"property","relation"}:
                    ident=_id(KnowledgeId,p["id"]); _unique(records,ident.value,"knowledge")
                    prov=tuple(_id(SourceId,x) for x in _exact_list(p["provenance"], "provenance must be an exact list"))
                    if not prov or any(x.value not in sources for x in prov): raise ValidationError("provenance reference unresolved")
                    scope = _exact_text(p.get("scope")); status = _exact_text(p.get("epistemic_status"))
                    if status not in _STATUSES: raise ValidationError("invalid record metadata")
                    if kind=="property":
                        d=_id(DescriptionId,p["description"]); prop=_id(PropertyId,p["property"]); version=_exact_text(p.get("version")); spec=self.vocabulary.properties.get((prop.value,version))
                        if d.value not in descriptions or spec is None: raise ValidationError("unresolved property assertion")
                        value_from_json(p["value"],spec.value_kind); records[ident.value]=p; pending.append((kind,ident.value,p))
                    else:
                        pred=_id(PredicateId,p["predicate"]); version=_exact_text(p.get("version")); spec=self.vocabulary.predicates.get((pred.value,version))
                        parts=tuple(_id(DescriptionId,x) for x in _exact_list(p.get("participants"), "participants must be an exact list"))
                        polarity = _exact_text(p.get("polarity"))
                        if spec is None or len(parts)!=spec.arity or len(_unique_values(parts)) != len(parts) or any(x.value not in descriptions for x in parts) or polarity not in _POLARITIES: raise ValidationError("invalid relation assertion")
                        records[ident.value]=p; pending.append((kind,ident.value,p))
                elif kind=="rule":
                    body=p["payload"]
                    if type(body) is not dict or type(body.get("participants")) is not list: raise ValidationError("invalid rule structure")
                    participants = tuple(_rule_text(value) for value in body["participants"])
                    if len(_unique_values(participants)) != len(participants): raise ValidationError("duplicate rule participant")
                    head=body.get("head")
                    if type(head) is not dict: raise ValidationError("invalid rule head")
                    pred_id = _id(PredicateId, head.get("predicate")); version = head.get("version")
                    version = _exact_text(version, "invalid rule head version")
                    pred=self.vocabulary.predicates.get((pred_id.value,version))
                    head_participants = tuple(_rule_text(value) for value in head.get("participants", []))
                    polarity = _exact_text(head.get("polarity"))
                    if pred is None or len(head_participants) != pred.arity or len(head_participants) != len(participants) or head_participants != participants or polarity not in _POLARITIES: raise ValidationError("invalid rule head")
                    _validate_rule_payload(body, self.vocabulary); safe_body = thaw(_freeze_json(body)); x=Rule(_id(RuleId,p["id"]),p["version"],safe_body,_rule_supported(safe_body)); _unique(rules,x.id.value,"rule"); rules[x.id.value]=x; pending.append((kind,x.id.value,{"id":x.id.value,"version":x.version,"payload":thaw(x.payload),"evaluation_supported":x.evaluation_supported}))
                elif kind=="context":
                    if type(p.get("visible_scopes")) is not list or any(type(z) is not str for z in p["visible_scopes"]): raise ValidationError("context scopes must be an exact list")
                    if type(p.get("enabled_rules")) is not list: raise ValidationError("context rules must be an exact list")
                    x=Context(_id(ContextId,p["id"]),tuple(p["visible_scopes"]),tuple(_id(RuleId,z) for z in p["enabled_rules"])); _unique(contexts,x.id.value,"context")
                    if any(z.value not in rules for z in x.enabled_rules): raise ValidationError("unresolved context rule")
                    contexts[x.id.value]=x; pending.append((kind,x.id.value,p))
                else: raise ValidationError("unsupported admission record")
        except (KeyError, TypeError, ValueError) as e: raise AdmissionError(str(e)) from e
        try:
            for kind,ident,p in pending: self._persist(kind,ident,p)
            if _commit: self._db.commit()
        except Exception:
            if _commit: self._db.rollback()
            raise
        if _publish:
            self.descriptions,self.sources,self.records,self.rules,self.contexts=descriptions,sources,dict(self.records),rules,contexts
            for kind, ident, payload in pending:
                if kind in {"property", "relation"}: self._restore(kind, payload, ident)

    def snapshot(self, ident, parent=None, _commit=True, _publish=True):
        self._check(); sid=_id(SnapshotId,ident)
        if sid.value in self.snapshots: raise AdmissionError("duplicate snapshot identity")
        if parent is not None and _id(SnapshotId,parent).value not in self.snapshots: raise ValidationError("unresolved snapshot parent")
        ids=tuple(_id(KnowledgeId,x) for x in sorted(self.records));
        predicates=tuple(sorted(self.vocabulary.predicates)); properties=tuple(sorted(self.vocabulary.properties)); rules=tuple(sorted((r.id.value,r.version) for r in self.rules.values())); contexts=tuple(_id(ContextId,x) for x in sorted(self.contexts))
        context_definitions=tuple((x.id.value,x.visible_scopes,tuple(r.value for r in x.enabled_rules)) for x in (self.contexts[k] for k in sorted(self.contexts)))
        rule_definitions=tuple((r.id.value,r.version,json.dumps(thaw(r.payload),ensure_ascii=False,sort_keys=True,separators=(",",":")),r.evaluation_supported) for r in (self.rules[k] for k in sorted(self.rules)))
        snap=Snapshot(sid,_id(SnapshotId,parent) if parent else None,ids,predicates,properties,rules,contexts,context_definitions,rule_definitions)
        try:
            self._persist("snapshot",sid.value,{"id":sid.value,"parent":str(snap.parent) if snap.parent else None,"record_ids":[str(x) for x in ids],"predicate_versions":[list(x) for x in predicates],"property_versions":[list(x) for x in properties],"rule_versions":[list(x) for x in rules],"context_ids":[str(x) for x in contexts],"context_definitions":[{"id":i,"visible_scopes":list(scopes),"enabled_rules":list(enabled)} for i,scopes,enabled in context_definitions],"rule_definitions":[{"id":i,"version":v,"payload":json.loads(payload),"evaluation_supported":supported} for i,v,payload,supported in rule_definitions]})
            if _commit: self._db.commit()
        except Exception:
            if _commit: self._db.rollback()
            raise
        if _publish: self.snapshots[sid.value]=snap
        return sid
    def open_snapshot(self, ident): self._check(); return self.snapshots[_id(SnapshotId,ident).value]
    def read(self, ident, snapshot=None):
        self._check(); record=self.records.get(_id(KnowledgeId,ident).value); return record if snapshot is None or record and record.id in self.open_snapshot(snapshot).record_ids else None
    def find(self, *, kind=None, snapshot=None):
        self._check(); allowed=None if snapshot is None else set(self.open_snapshot(snapshot).record_ids); return tuple(r for r in self.records.values() if (allowed is None or r.id in allowed) and (kind is None or (kind=="property" and isinstance(r,PropertyAssertion)) or (kind=="relation" and isinstance(r,RelationAssertion))))
    def close(self):
        if not self._closed: self._db.close(); self._closed=True

def _unique(mapping,key,domain):
    if key in mapping: raise ValidationError(f"duplicate {domain} identity")

def _unique_values(values):
    result=[]
    for value in values:
        if any(value == prior for prior in result): return result + [value]
        result.append(value)
    return result

def _rule_text(value):
    if type(value) is not str or not value or any(0xD800 <= ord(char) <= 0xDFFF for char in value): raise ValidationError("rule participant must be an exact non-empty string")
    return value

def _validate_rule_payload(body, vocabulary):
    participants=tuple(_rule_text(value) for value in body["participants"])
    def check_expr(expr):
        if type(expr) is not dict: raise ValidationError("invalid rule expression")
        op=_exact_text(expr.get("op"), "invalid rule expression operator")
        if op == "property":
            participant=_rule_text(expr.get("participant")); property_id=_id(PropertyId, expr.get("property"))
            if participant not in participants: raise ValidationError("unresolved rule participant")
            versions=[key[1] for key in vocabulary.properties if key[0] == property_id.value]
            requested=expr.get("version")
            if requested is not None and (type(requested) is not str or (property_id.value, requested) not in vocabulary.properties): raise ValidationError("unresolved rule property version")
            if requested is None and len(versions) != 1: raise ValidationError("ambiguous rule property version")
        elif op in {"set_union", "set_subset"}:
            check_expr(expr.get("left")); check_expr(expr.get("right"))
        # Other operators remain persistable but unsupported in M1.
    check_expr(body.get("when"))

def _freeze_json(value):
    if type(value) is dict:
        if any(type(key) is not str for key in value): raise ValidationError("payload keys must be exact strings")
        return {key: _freeze_json(item) for key,item in value.items()}
    if type(value) is list: return [_freeze_json(item) for item in value]
    if type(value) in (str,int,float,bool) or value is None: return value
    raise ValidationError("payload contains a non-persistable value")

def _rule_supported(payload):
    if type(payload) is not dict: return False
    expression = payload.get("when") if "when" in payload else payload
    if type(expression) is not dict: return False
    op = expression.get("op")
    if op in {"set_union", "set_subset"}: return _rule_supported(expression.get("left")) and _rule_supported(expression.get("right"))
    return op == "property"

def open_store(path): return Store(Path(path))

def admit_fixture(store, fixture):
    store._check()
    # All fixture work happens on an independent in-memory state.  The clone
    # deliberately shares only the SQLite connection, whose transaction is
    # committed once the candidate is complete.
    candidate=copy.copy(store)
    for name in ("descriptions", "sources", "records", "rules", "contexts", "snapshots", "isolated"):
        setattr(candidate, name, dict(getattr(store, name)))
    batch=[]
    store._db.execute("BEGIN")
    for x in fixture["descriptions"]: batch.append(("description",x["id"],x))
    for x in {p for f in fixture["facts"]+fixture["relations"] for p in f["provenance"]}: batch.append(("source",x,{"id":x}))
    try:
        candidate.configure_vocabulary(fixture["vocabulary"],_commit=False)
        # Resolve compact, unversioned references against the final candidate
        # vocabulary: existing state plus this fixture's admitted vocabulary.
        for x in fixture["facts"]:
            matches=[version for ident,version in candidate.vocabulary.properties if ident==x["property"]]
            version=x["version"] if "version" in x else (matches[0] if len(matches)==1 else (_raise("fixture property reference must identify one exact version")))
            batch.append(("property",x["id"],dict(x,version=version)))
        for x in fixture["relations"]: batch.append(("relation",x["id"],x))
        for x in fixture["rules"]: batch.append(("rule",x["id"],{"id":x["id"],"version":x["version"],"payload":x}))
        for x in fixture["contexts"]: batch.append(("context",x["id"],x))
        candidate.admit([{"kind":k,"payload":p} for k,_,p in batch],_commit=False)
        for x in fixture["snapshots"]: candidate.snapshot(x["id"],x.get("parent"),_commit=False)
        store._db.commit()
    except Exception:
        store._db.rollback()
        raise
    for name in ("vocabulary", "descriptions", "sources", "records", "rules", "contexts", "snapshots", "isolated"):
        setattr(store, name, getattr(candidate, name))
    return store
