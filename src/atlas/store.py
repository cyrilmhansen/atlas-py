from __future__ import annotations
import copy, json, sqlite3
from pathlib import Path
from collections.abc import Mapping
from types import MappingProxyType
from .errors import AdmissionError, AtlasError, ClosedStoreError, GroundingError, ValidationError
from .identity import *
from .model import *
from .model import thaw
from .values import value_from_json, value_to_json
from .vocabulary import *
from .evidence import validate_grounding_evidence
from .provenance import canonical_provenance
from .scope import (evaluate as evaluate_scope, grounding_payload, restore_grounding,
                    restore_scope, scope_payload, validate_scope_environment,
                    compute_declared_scope_completeness, validate_grounding_manifest,
                    _manifest as _manifest_for_store)
from .problem import (GroundedDecisionProblem, grounded_decision_problem_payload,
                      Decision, M1SelectionResult, decision_payload, restore_decision,
                      restore_grounded_decision_problem,
                      _explain_m1,
                      ArtifactStatus,
                      validate_persisted_decision,
                      validate_persisted_grounded_decision_problem)

_STATUSES={"exact","bound","estimate","unknown"}; _POLARITIES={"positive","negative"}
SUPERSESSION_SCHEMA="atlas.core-v1.supersession/1"

class _Isolated(dict):
    """Physical-row keyed isolation, with legacy lookup by an unambiguous id."""
    def _legacy(self, key):
        if type(key) is str:
            matches=[physical for physical in self if physical[1] == key]
            if len(matches) == 1: return matches[0]
        return key
    def __contains__(self, key): return dict.__contains__(self, self._legacy(key))
    def __getitem__(self, key): return dict.__getitem__(self, self._legacy(key))

def _id(cls, raw): return raw if type(raw) is cls else (cls(raw) if type(raw) is str else (_raise("identifier must be exact text")))
def _raise(msg): raise ValidationError(msg)
def _exact_text(raw, message="text must be exact and non-empty"):
    if type(raw) is not str or not raw or any(0xD800 <= ord(char) <= 0xDFFF for char in raw): raise ValidationError(message)
    return raw
def _exact_list(raw, message="value must be an exact list"):
    if type(raw) is not list: raise ValidationError(message)
    return raw
def _decode_exact_string_pair(raw, field_name):
    """Decode one persisted JSON identity/version pair without coercion."""
    if type(raw) is not list or len(raw) != 2 or any(type(value) is not str for value in raw):
        raise ValidationError(f"{field_name} entries require exactly two strings")
    return (raw[0], raw[1])
def _require_exact_keys(value, keys, message):
    if type(value) is not dict or set(value) != set(keys):
        raise ValidationError(message)

class Store:
    def __init__(self, path):
        self.path=str(path); self._db=sqlite3.connect(self.path); self._db.row_factory=sqlite3.Row; self._closed=False
        self._db.executescript("CREATE TABLE IF NOT EXISTS records (id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(kind,id)); CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS knowledge_identity (knowledge_id TEXT PRIMARY KEY, kind TEXT NOT NULL, row_id TEXT NOT NULL)")
        self._migrate_knowledge_identity()
        self.vocabulary=Vocabulary({},{}); self.descriptions={}; self.sources={}; self.rules={}; self.contexts={}; self.snapshots={}; self.records={}; self.derivations={}; self.supersessions={}; self._supersession_claimants=[]; self.decision_scopes={}; self.decision_groundings={}; self.grounded_decision_problems={}; self.decisions={}; self.isolated=_Isolated(); self._load()

    def _check(self):
        if self._closed: raise ClosedStoreError("store is closed")

    def _load(self):
        self._snapshot_claimants=[]
        row=self._db.execute("SELECT payload FROM meta WHERE key='vocabulary'").fetchone()
        if row: self._configure_loaded(json.loads(row[0]))
        rows=list(self._db.execute("SELECT id,kind,payload FROM records ORDER BY CASE kind WHEN 'description' THEN 1 WHEN 'source' THEN 2 WHEN 'rule' THEN 3 WHEN 'context' THEN 4 WHEN 'property' THEN 5 WHEN 'relation' THEN 6 WHEN 'snapshot' THEN 7 WHEN 'supersession' THEN 8 WHEN 'derivation' THEN 9 WHEN 'decision_scope' THEN 10 WHEN 'decision_grounding' THEN 11 WHEN 'grounded_decision_problem' THEN 12 WHEN 'decision' THEN 13 ELSE 14 END, id"))
        for row in rows:
            if row["kind"] in {"description", "source", "rule", "context"}:
                self._restore_safely(row["kind"], row["id"], row["payload"])
        for row in rows:
            if row["kind"] in {"property", "relation", "derivation"}:
                self._restore_safely(row["kind"], row["id"], row["payload"])
        for row in rows:
            if row["kind"] == "snapshot":
                self._restore_safely(row["kind"], row["id"], row["payload"])
        for row in rows:
            if row["kind"] == "supersession":
                self._restore_safely(row["kind"], row["id"], row["payload"])
        self._validate_supersessions()
        # Only snapshots accepted by the common restore validator are
        # historical claimants.  Keep this candidate set before dependency
        # closure: final snapshot validity may depend on the definitions that
        # these candidates help classify, but malformed raw JSON never gets
        # to contribute a claim.
        self._classify_unmatched_definition_claims(tuple(self._snapshot_claimants))
        self._validate_definition_closure()

        # M1b is a prerequisite closure, not merely a local row check.  It
        # must settle before any M1c.1 object is even a restore candidate:
        # scopes and runs refer to the final historical snapshot set.
        self._validate_derivation_pairs()

        for row in rows:
            if row["kind"] == "decision_scope":
                self._restore_safely(row["kind"], row["id"], row["payload"])
        for row in rows:
            if row["kind"] == "decision_grounding":
                self._restore_safely(row["kind"], row["id"], row["payload"])
        for row in rows:
            if row["kind"] == "grounded_decision_problem":
                self._restore_safely(row["kind"], row["id"], row["payload"])
        for row in rows:
            if row["kind"] == "decision":
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

    def _isolation(self, kind, ident, reason):
        self.isolated[(kind, ident)]={"kind":kind,"row_id":ident,"reason":reason}

    def _classify_unmatched_definition_claims(self, snapshot_claimants):
        """Classify a global definition only when no snapshot claims it.

        A bad claimant must not make a good claimant's definition look bad.
        This pass is deliberately after every snapshot candidate has been
        decoded, so it cannot depend on the claimant iteration order.
        """
        raw_context_claims=[]; raw_rule_claims=[]
        for snapshot in snapshot_claimants:
            raw_context_claims.extend(snapshot.context_definitions)
            raw_rule_claims.extend(snapshot.rule_definitions)
        for ident, current in sorted(self.contexts.items()):
            claims=[claim for claim in raw_context_claims if claim[0] == ident]
            if claims and not any(current.visible_scopes == claim[1] and
                                  tuple(x.value for x in current.enabled_rules) == claim[2]
                                  for claim in claims):
                self._isolation("context", ident, "context definition disagrees with historical snapshots")
                self.contexts.pop(ident, None)
        for ident, current in sorted(self.rules.items()):
            claims=[claim for claim in raw_rule_claims if claim[0] == ident]
            current_payload=json.dumps(thaw(current.payload),ensure_ascii=False,sort_keys=True,separators=(",",":"))
            if claims and not any(current.version == version and current_payload == payload and
                                  current.evaluation_supported == supported
                                  for _, version, payload, supported in claims):
                self._isolation("rule", ident, "rule definition disagrees with historical snapshots")
                self.rules.pop(ident, None)

        # Contexts are active definitions too.  A definition that has been
        # classified invalid must not remain publicly usable or be copied by
        # a later snapshot.  A context depending on an invalid rule is also
        # no longer an active context candidate.
        for ident, current in sorted(tuple(self.contexts.items())):
            if any(rule.value not in self.rules for rule in current.enabled_rules):
                self._isolation("context", ident, "context references an invalid rule definition")
                self.contexts.pop(ident, None)

        for ident in tuple(self.contexts):
            if ("context", ident) in self.isolated:
                self.contexts.pop(ident, None)

    def _validate_definition_closure(self):
        """Remove historical objects that require a non-active definition.

        This is an in-memory fixed point.  SQLite rows are never repaired;
        rows removed here remain visible through ``isolated``.
        """
        invalid_snapshots={}
        while True:
            changed=False
            for ident, snapshot in sorted(tuple(self.snapshots.items())):
                reason=None
                if snapshot.parent is not None and snapshot.parent.value not in self.snapshots:
                    reason="snapshot parent is invalid or absent"
                if reason is None and any(context.value not in self.contexts for context in snapshot.context_ids):
                    reason="snapshot references an invalid context definition"
                if reason is None:
                    for context_id, scopes, enabled in snapshot.context_definitions:
                        current=self.contexts.get(context_id)
                        if (current is None or current.visible_scopes != scopes or
                            tuple(rule.value for rule in current.enabled_rules) != enabled):
                            reason="snapshot context definition is not active"
                            break
                if reason is None and any(rule_id not in self.rules or
                                          self.rules[rule_id].version != version
                                          for rule_id, version in snapshot.rule_versions):
                    reason="snapshot references an invalid rule definition"
                if reason is None:
                    for rule_id, version, payload, supported in snapshot.rule_definitions:
                        current=self.rules.get(rule_id)
                        if (current is None or current.version != version or
                            json.dumps(thaw(current.payload), ensure_ascii=False,
                                       sort_keys=True, separators=(",", ":")) != payload or
                            current.evaluation_supported != supported):
                            reason="snapshot rule definition is not active"
                            break
                if reason is not None:
                    invalid_snapshots[ident]=reason
            if not invalid_snapshots:
                break
            for ident, reason in sorted(invalid_snapshots.items()):
                if ident in self.snapshots:
                    self.snapshots.pop(ident)
                    self._isolation("snapshot", ident, reason)
                    changed=True
            invalid_snapshots.clear()
            if not changed:
                break

    def _validate_derivation_pairs(self):
        """Compute the complete restored derivation closure before publishing."""
        records, derivations, snapshots = dict(self.records), dict(self.derivations), dict(self.snapshots)
        invalid, invalid_snapshots = {}, {}

        def mark(ident, reason):
            invalid.setdefault(ident, reason)

        # Local pair/environment validation sees every candidate, never a
        # progressively pruned public map.
        for ident, record in sorted(records.items()):
            if isinstance(record, RelationAssertion) and record.derivation_id is not None:
                derivation=derivations.get(record.derivation_id.value)
                reason=self._derivation_error(record, derivation, records, snapshots)
                if reason is not None:
                    mark(ident, reason)
                    if derivation is not None: mark(derivation.knowledge_id.value, reason)
        for ident, derivation in sorted(derivations.items()):
            record=records.get(ident)
            if not isinstance(record, RelationAssertion) or record.derivation_id != derivation.knowledge_id:
                mark(ident, "derivation has no matching relation")

        # Deterministic Tarjan SCC over derived candidates. Facts are leaves;
        # missing dependencies are handled by propagation below.
        graph={ident: tuple(dep.value for dep in d.dependencies if dep.value in derivations)
               for ident, d in derivations.items()}
        index=0; indices={}; lowlinks={}; stack=[]; on_stack=set(); components=[]
        def strongconnect(node):
            nonlocal index
            indices[node]=lowlinks[node]=index; index += 1
            stack.append(node); on_stack.add(node)
            for child in sorted(graph[node]):
                if child not in indices:
                    strongconnect(child); lowlinks[node]=min(lowlinks[node], lowlinks[child])
                elif child in on_stack:
                    lowlinks[node]=min(lowlinks[node], indices[child])
            if lowlinks[node] == indices[node]:
                component=[]
                while True:
                    child=stack.pop(); on_stack.remove(child); component.append(child)
                    if child == node: break
                components.append(tuple(sorted(component)))
        for node in sorted(graph):
            if node not in indices: strongconnect(node)
        for component in components:
            if len(component) > 1 or component[0] in graph[component[0]]:
                for ident in component: mark(ident, "derivation dependency cycle")

        def dependency_is_valid(ident):
            record=records.get(ident)
            if record is None: return False
            if ident in derivations:
                return ident not in invalid and isinstance(record, RelationAssertion) and record.derivation_id == derivations[ident].knowledge_id
            return not isinstance(record, RelationAssertion) or record.derivation_id is None

        # Alternate dependency propagation and historical snapshot invalidation
        # until neither set changes.
        for ident, snapshot in sorted(snapshots.items()):
            if snapshot.parent is not None and snapshot.parent.value not in snapshots:
                invalid_snapshots[ident]="snapshot parent is invalid or absent"
        while True:
            before=(frozenset(invalid), frozenset(invalid_snapshots))
            for ident, derivation in sorted(derivations.items()):
                if ident not in invalid and any(not dependency_is_valid(dep.value) for dep in derivation.dependencies):
                    mark(ident, "invalid dependency")
            for ident, snapshot in sorted(snapshots.items()):
                if ident not in invalid_snapshots and (
                    (snapshot.parent is not None and snapshot.parent.value in invalid_snapshots) or
                    any(record_id.value not in records or record_id.value in invalid for record_id in snapshot.record_ids)):
                    invalid_snapshots[ident]="snapshot references an invalid derived relation"
            for ident, derivation in sorted(derivations.items()):
                if ident not in invalid and derivation.snapshot.value in invalid_snapshots:
                    mark(ident, "derivation references an invalid snapshot")
            after=(frozenset(invalid), frozenset(invalid_snapshots))
            if before == after: break

        # Publish only the fixed-point result; isolation remains physical-row
        # keyed, so relation and derivation rows cannot collapse into one key.
        for ident, reason in sorted(invalid.items()):
            derivations.pop(ident, None); records.pop(ident, None)
            if ident in self.derivations: self._isolation("derivation", ident, reason)
            if ident in self.records: self._isolation("relation", ident, reason)
        for ident, reason in sorted(invalid_snapshots.items()):
            snapshots.pop(ident, None)
            if ident in self.snapshots: self._isolation("snapshot", ident, reason)
        self.records, self.derivations, self.snapshots = records, derivations, snapshots

    def _derivation_error(self, relation, derivation, records=None, snapshots=None):
        records=self.records if records is None else records
        snapshots=self.snapshots if snapshots is None else snapshots
        if not isinstance(derivation, Derivation) or derivation.knowledge_id != relation.id:
            return "derived relation has no valid derivation"
        snapshot=snapshots.get(derivation.snapshot.value)
        if snapshot is None:
            return "derivation references an invalid snapshot"
        if derivation.context not in snapshot.context_ids:
            return "derivation references an invalid context"
        rule_matches=[x for x in snapshot.rule_definitions if x[0] == derivation.rule_id.value]
        if len(rule_matches) != 1 or rule_matches[0][1] != derivation.rule_version:
            return "derivation references an invalid rule version"
        try:
            payload=json.loads(rule_matches[0][2]); declared=tuple(payload["participants"]); head=payload["head"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return "derivation references an invalid rule definition"
        if tuple(name for name, _ in derivation.bindings) != declared or any(description not in snapshot.description_ids for _, description in derivation.bindings):
            return "derivation bindings disagree with historical rule"
        binding=dict(derivation.bindings)
        if tuple(binding[name] for name in head.get("participants", ())) != relation.participants:
            return "derived relation participants disagree with derivation"
        if head.get("predicate") != relation.predicate.value or head.get("version") != relation.version or head.get("polarity") != relation.polarity:
            return "derived relation term disagrees with derivation"
        if len(set(derivation.dependencies)) != len(derivation.dependencies):
            return "derivation contains duplicate dependencies"
        if any(dep.value not in records or dep not in snapshot.record_ids for dep in derivation.dependencies):
            return "derivation references an invalid dependency"
        context_matches=[x for x in snapshot.context_definitions if x[0] == derivation.context.value]
        if len(context_matches) != 1:
            return "derivation context is not fixed by snapshot"
        expected_scope = context_matches[0][1][0] if len(context_matches[0][1]) == 1 else tuple(context_matches[0][1])
        if relation.scope != expected_scope:
            return "derived relation scope disagrees with historical context"
        expected_provenance = canonical_provenance(
            source for dependency in derivation.dependencies
            for source in records[dependency.value].provenance)
        if canonical_provenance(relation.provenance) != expected_provenance:
            return "derived relation provenance disagrees with dependencies"
        try:
            conclusion=GroundedConclusion(
                RelationTerm(relation.predicate, relation.version, relation.participants),
                relation.polarity, relation.epistemic_status, relation.scope, relation.provenance,
                derivation.rule_id, derivation.rule_version, derivation.dependencies)
            result=GroundingResult(derivation.rule_id, derivation.rule_version,
                                   MappingProxyType(dict(derivation.bindings)), EvaluationTruth.TRUE,
                                   conclusion, derivation.dependencies, (), (),
                                   derivation.snapshot, derivation.context, derivation.grounding_evidence)
            validate_grounding_evidence(result, declared)
        except (AtlasError, TypeError, ValueError):
            return "derivation grounding evidence disagrees with persisted pair"
        if any(source.value not in self.sources for source in relation.provenance):
            return "derived relation references invalid provenance"
        return None

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
            _validate_rule_payload(body, self.vocabulary, require_exact=True)
            if type(p["evaluation_supported"]) is not bool: raise ValidationError("invalid persisted rule evaluation status")
            self.rules[p["id"]]=Rule(_id(RuleId,p["id"]),_exact_text(p["version"]),body,p["evaluation_supported"])
        elif kind=="snapshot":
            required=("id","parent","record_ids","predicate_versions","property_versions","rule_versions","context_ids","context_definitions","rule_definitions","description_ids")
            if set(p) != set(required): raise ValidationError("incomplete or unknown persisted snapshot field")
            if type(p["record_ids"]) is not list or type(p["predicate_versions"]) is not list or type(p["property_versions"]) is not list or type(p["rule_versions"]) is not list or type(p["context_ids"]) is not list or type(p["context_definitions"]) is not list or type(p["rule_definitions"]) is not list or type(p["description_ids"]) is not list: raise ValidationError("invalid persisted snapshot structure")
            ids=tuple(_id(KnowledgeId,x) for x in p["record_ids"])
            description_ids=tuple(_id(DescriptionId,x) for x in p["description_ids"])
            if len({x.value for x in description_ids}) != len(description_ids): raise ValidationError("snapshot description_ids contain a duplicate")
            if any(x.value not in self.descriptions for x in description_ids): raise ValidationError("snapshot references invalid or absent description")
            if any(x.value not in self.records for x in ids): raise ValidationError("snapshot references invalid or absent record")
            raw_parent=p["parent"]
            if raw_parent is None:
                parent=None
            elif type(raw_parent) is str:
                parent=SnapshotId(raw_parent)
            else:
                raise ValidationError("snapshot parent must be null or an exact SnapshotId string")
            # Parent existence is checked after all snapshot candidates have
            # been decoded; lexical/SQL row order is not semantic here.
            contexts=tuple(_id(ContextId,x) for x in p["context_ids"])
            if len({x.value for x in contexts}) != len(contexts):
                raise ValidationError("snapshot context_ids contain a duplicate")
            for x in p["context_definitions"]:
                _require_exact_keys(x, {"id", "visible_scopes", "enabled_rules"},
                                    "invalid persisted snapshot context definition")
            if any(type(x.get("visible_scopes")) is not list or type(x.get("enabled_rules")) is not list for x in p["context_definitions"]):
                raise ValidationError("invalid persisted snapshot context definition")
            context_defs=tuple((_exact_text(x["id"]),tuple(x["visible_scopes"]),tuple(x["enabled_rules"])) for x in p["context_definitions"])
            if any(any(type(scope) is not str for scope in x[1]) or any(type(rule) is not str for rule in x[2]) for x in context_defs):
                raise ValidationError("invalid persisted snapshot context definition")
            context_def_ids=tuple(x[0] for x in context_defs)
            if len(set(context_def_ids)) != len(context_def_ids) or set(context_def_ids) != {x.value for x in contexts}:
                raise ValidationError("snapshot context definitions do not exactly match context_ids")
            for x in p["rule_definitions"]:
                _require_exact_keys(x, {"id", "version", "payload", "evaluation_supported"},
                                    "invalid persisted snapshot rule definition")
            if any(type(x.get("payload")) is not dict for x in p["rule_definitions"]):
                raise ValidationError("invalid persisted snapshot rule definition")
            rule_defs=tuple((_exact_text(x["id"]),_exact_text(x["version"]),json.dumps(x["payload"],ensure_ascii=False,sort_keys=True,separators=(",",":")),x["evaluation_supported"]) for x in p["rule_definitions"])
            if any(type(x[3]) is not bool for x in rule_defs):
                raise ValidationError("invalid persisted snapshot rule definition")
            rule_def_pairs=tuple((x[0],x[1]) for x in rule_defs)
            predicate_versions=tuple(_decode_exact_string_pair(x, "snapshot predicate_versions")
                                     for x in p["predicate_versions"])
            property_versions=tuple(_decode_exact_string_pair(x, "snapshot property_versions")
                                    for x in p["property_versions"])
            snapshot_rule_versions=tuple(_decode_exact_string_pair(x, "snapshot rule_versions")
                                         for x in p["rule_versions"])
            if len(set(snapshot_rule_versions)) != len(snapshot_rule_versions) or len(set(rule_def_pairs)) != len(rule_def_pairs) or set(rule_def_pairs) != set(snapshot_rule_versions):
                raise ValidationError("snapshot rule definitions do not exactly match rule_versions")
            snap=Snapshot(_id(SnapshotId,p["id"]),parent,ids,predicate_versions,property_versions,snapshot_rule_versions,contexts,context_defs,rule_defs,description_ids)
            if any((x[0],x[1]) not in self.vocabulary.predicates for x in snap.predicate_versions) or any((x[0],x[1]) not in self.vocabulary.properties for x in snap.property_versions): raise ValidationError("snapshot vocabulary environment is unresolved")
            # This is the structural claimant boundary.  The candidate has
            # passed the complete Snapshot shape/identity/environment decode,
            # but its final activity may still depend on the definitions it
            # carries (and is therefore checked below and in closure).
            self._snapshot_claimants.append(snap)
            if any(not any(r.id.value==x[0] and r.version==x[1] for r in self.rules.values()) for x in snap.rule_versions): raise ValidationError("snapshot rule environment is unresolved")
            if any(x.value not in self.contexts for x in snap.context_ids): raise ValidationError("snapshot context environment is unresolved")
            for ident, scopes, enabled in snap.context_definitions:
                current=self.contexts.get(ident)
                if current is None or current.visible_scopes != scopes or tuple(x.value for x in current.enabled_rules) != enabled:
                    raise ValidationError("snapshot context definition is inconsistent")
            for ident, version, payload, supported in snap.rule_definitions:
                current=self.rules.get(ident)
                if current is None or current.version != version or json.dumps(thaw(current.payload),ensure_ascii=False,sort_keys=True,separators=(",",":")) != payload or current.evaluation_supported != supported:
                    raise ValidationError("snapshot rule definition is inconsistent")
            self.snapshots[p["id"]]=snap
        elif kind=="supersession":
            _require_exact_keys(p, {"schema", "id", "old", "new", "snapshot"},
                                "invalid persisted supersession")
            if p["schema"] != SUPERSESSION_SCHEMA or p["id"] != physical_id or type(p["old"]) is not str or type(p["new"]) is not str or type(p["snapshot"]) is not str:
                raise ValidationError("invalid persisted supersession identity")
            item=Supersession(_id(KnowledgeId,p["old"]), _id(KnowledgeId,p["new"]), _id(SnapshotId,p["snapshot"]))
            self._validate_supersession_candidate(item.old, item.new, item.snapshot)
            self._supersession_claimants.append((physical_id, item))
        elif kind=="derivation":
            required=("id","knowledge_id","rule_id","rule_version","bindings","snapshot","context","dependencies","grounding_evidence")
            if any(field not in p for field in required): raise ValidationError("incomplete persisted derivation")
            if p["id"] != p["knowledge_id"]: raise ValidationError("derivation identity disagrees with knowledge identity")
            knowledge_id=_id(KnowledgeId,p["knowledge_id"]); rule_id=_id(RuleId,p["rule_id"])
            bindings=tuple((_exact_text(x["participant"]),_id(DescriptionId,x["description"])) for x in p["bindings"] if type(x) is dict and "participant" in x and "description" in x)
            if type(p["bindings"]) is not list or len(bindings) != len(p["bindings"]): raise ValidationError("invalid persisted derivation bindings")
            dependencies=tuple(_id(KnowledgeId,x) for x in p["dependencies"])
            self.derivations[knowledge_id.value]=Derivation(knowledge_id,rule_id,_exact_text(p["rule_version"]),bindings,_id(SnapshotId,p["snapshot"]),_id(ContextId,p["context"]),dependencies,_exact_text(p["grounding_evidence"]))
        elif kind=="decision_scope":
            scope=restore_scope(p)
            validate_grounding_manifest(scope.manifest)
            validate_scope_environment(self, scope)
            if scope.id.value in self.decision_scopes: raise ValidationError("duplicate decision scope")
            self.decision_scopes[scope.id.value]=scope
        elif kind=="decision_grounding":
            grounding=restore_grounding(p)
            scope=self.decision_scopes.get(grounding.scope_id.value)
            if scope is None: raise ValidationError("grounding references an invalid decision scope")
            computed = compute_declared_scope_completeness(self, scope, grounding)
            if grounding.status is not computed:
                raise ValidationError("persisted grounding status disagrees with recomputed status")
            self.decision_groundings[grounding.scope_id.value]=grounding
        elif kind=="grounded_decision_problem":
            problem_id, problem = restore_grounded_decision_problem(p)
            if problem_id.value != physical_id:
                raise ValidationError("grounded decision problem identity disagrees with row identity")
            scope = self.decision_scopes.get(problem.scope_id.value)
            grounding = self.decision_groundings.get(problem.scope_id.value)
            if scope is None or grounding is None:
                raise ValidationError("grounded decision problem references an invalid source grounding")
            if problem_id.value in self.grounded_decision_problems:
                raise ValidationError("duplicate grounded decision problem")
            validate_persisted_grounded_decision_problem(self, problem)
            self.grounded_decision_problems[problem_id.value] = problem
        elif kind=="decision":
            decision=restore_decision(p)
            if decision.id.value != physical_id:
                raise ValidationError("decision identity disagrees with row identity")
            if decision.id.value in self.decisions:
                raise ValidationError("duplicate decision")
            validate_persisted_decision(self, decision)
            self.decisions[decision.id.value] = decision
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
            derivation_id=None if p.get("derivation_id") is None else _id(KnowledgeId,p["derivation_id"])
            scope=p["scope"] if type(p["scope"]) is str else tuple(p["scope"])
            if spec is None or len(parts)!=spec.arity or len(_unique_values(parts)) != len(parts) or any(x.value not in self.descriptions for x in parts) or any(x.value not in self.sources for x in prov) or not prov or p["polarity"] not in _POLARITIES or (type(p["scope"]) is not str and (derivation_id is None or type(p["scope"]) is not list)) or p["epistemic_status"] not in _STATUSES: raise ValidationError("invalid persisted relation assertion")
            self.records[p["id"]]=RelationAssertion(_id(KnowledgeId,p["id"]),pred,version,parts,p["polarity"],scope,p["epistemic_status"],prov,derivation_id)

    def _validate_supersessions(self):
        """Publish a deterministic, closed supersession relation after restore."""
        candidates=tuple(sorted(self._supersession_claimants, key=lambda x: (x[1].old.value, x[1].new.value, x[1].snapshot.value, x[0])))
        grouped={}
        for physical, item in candidates:
            grouped.setdefault(item.old.value, []).append((physical, item))
        valid={}
        for old, claims in sorted(grouped.items()):
            replacements={(item.new.value, item.snapshot.value) for _, item in claims}
            new_ids={item.new.value for _, item in claims}
            if len(new_ids) != 1:
                for physical, _ in claims: self._isolation("supersession", physical, "conflicting replacement for one knowledge id")
                continue
            # A repeated claim is harmless only when it is byte-for-byte the same row identity.
            if len(claims) != 1:
                for physical, _ in claims: self._isolation("supersession", physical, "duplicate supersession claim")
                continue
            physical, item=claims[0]
            valid[old]=item
        # A replacement chain is allowed, but it must be acyclic.
        for old in tuple(sorted(valid)):
            seen=set(); current=old
            while current in valid:
                if current in seen:
                    cycle=set(seen); cycle.add(current)
                    for source, item in candidates:
                        if item.old.value in cycle: self._isolation("supersession", source, "supersession cycle")
                    for node in cycle: valid.pop(node, None)
                    break
                seen.add(current); current=valid[current].new.value
        self.supersessions=valid

    @staticmethod
    def _supersession_slot(record):
        if isinstance(record, PropertyAssertion):
            return (type(record), record.description, record.property, record.version,
                    type(record.value))
        if isinstance(record, RelationAssertion):
            return (type(record), record.predicate, record.version,
                    record.participants, record.polarity)
        return None

    def _validate_supersession_candidate(self, old, new, snapshot, edges=None):
        """Purely validate one edge against records, snapshot, and a graph."""
        if old == new:
            raise ValidationError("knowledge cannot supersede itself")
        previous=self.records.get(old.value); replacement=self.records.get(new.value)
        if previous is None or replacement is None:
            raise ValidationError("supersession requires existing old and new knowledge")
        old_slot=self._supersession_slot(previous); new_slot=self._supersession_slot(replacement)
        if old_slot is None or old_slot != new_slot:
            raise ValidationError("supersession changes the semantic domain")
        target=self.snapshots.get(snapshot.value)
        if target is None:
            raise ValidationError("unknown reference snapshot")
        if old not in target.record_ids or new not in target.record_ids:
            raise ValidationError("old and new knowledge must be present in the reference snapshot")
        if edges is not None:
            graph={key: edge.new.value for key, edge in edges.items()}
            graph[old.value]=new.value
            for start in graph:
                current=start; seen=set()
                while current in graph:
                    if current in seen:
                        raise ValidationError("supersession cycle")
                    seen.add(current); current=graph[current]

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
                    normalized = _normalize_rule_payload(body, self.vocabulary)
                    safe_body = thaw(_freeze_json(normalized)); x=Rule(_id(RuleId,p["id"]),p["version"],safe_body,_rule_supported(safe_body)); _unique(rules,x.id.value,"rule"); rules[x.id.value]=x; pending.append((kind,x.id.value,{"id":x.id.value,"version":x.version,"payload":thaw(x.payload),"evaluation_supported":x.evaluation_supported}))
                elif kind=="context":
                    if type(p.get("visible_scopes")) is not list or any(type(z) is not str for z in p["visible_scopes"]): raise ValidationError("context scopes must be an exact list")
                    if type(p.get("enabled_rules")) is not list: raise ValidationError("context rules must be an exact list")
                    x=Context(_id(ContextId,p["id"]),tuple(p["visible_scopes"]),tuple(_id(RuleId,z) for z in p["enabled_rules"])); _unique(contexts,x.id.value,"context")
                    if any(z.value not in rules for z in x.enabled_rules): raise ValidationError("unresolved context rule")
                    contexts[x.id.value]=x; pending.append((kind,x.id.value,p))
                else: raise ValidationError("unsupported admission record")
        except AtlasError:
            # Preserve structural validation errors (notably static rule type
            # errors) at the admission boundary instead of disguising them as
            # generic admission failures.
            raise
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
        ids=tuple(_id(KnowledgeId,x) for x in sorted(self.records)); description_ids=tuple(_id(DescriptionId,x) for x in sorted(self.descriptions));
        # A Snapshot records one exact vocabulary version per nominal identity.
        # Vocabulary history may retain older versions, but persisting all of
        # them would make the Snapshot map non-canonical.
        predicates=tuple(sorted(_latest_versions(self.vocabulary.predicates)))
        properties=tuple(sorted(_latest_versions(self.vocabulary.properties)))
        rules=tuple(sorted((r.id.value,r.version) for r in self.rules.values())); contexts=tuple(_id(ContextId,x) for x in sorted(self.contexts))
        context_definitions=tuple((x.id.value,x.visible_scopes,tuple(r.value for r in x.enabled_rules)) for x in (self.contexts[k] for k in sorted(self.contexts)))
        rule_definitions=tuple((r.id.value,r.version,json.dumps(thaw(r.payload),ensure_ascii=False,sort_keys=True,separators=(",",":")),r.evaluation_supported) for r in (self.rules[k] for k in sorted(self.rules)))
        snap=Snapshot(sid,_id(SnapshotId,parent) if parent else None,ids,predicates,properties,rules,contexts,context_definitions,rule_definitions,description_ids)
        try:
            self._persist("snapshot",sid.value,{"id":sid.value,"parent":str(snap.parent) if snap.parent else None,"record_ids":[str(x) for x in ids],"predicate_versions":[list(x) for x in predicates],"property_versions":[list(x) for x in properties],"rule_versions":[list(x) for x in rules],"context_ids":[str(x) for x in contexts],"context_definitions":[{"id":i,"visible_scopes":list(scopes),"enabled_rules":list(enabled)} for i,scopes,enabled in context_definitions],"rule_definitions":[{"id":i,"version":v,"payload":json.loads(payload),"evaluation_supported":supported} for i,v,payload,supported in rule_definitions],"description_ids":[str(x) for x in description_ids]})
            if _commit: self._db.commit()
        except Exception:
            if _commit: self._db.rollback()
            raise
        if _publish: self.snapshots[sid.value]=snap
        return sid

    def supersede(self, old, new, snapshot):
        """Admit one explicit replacement edge without mutating either record."""
        self._check()
        old, new, snapshot = _id(KnowledgeId, old), _id(KnowledgeId, new), _id(SnapshotId, snapshot)
        self._validate_supersession_candidate(old, new, snapshot, self.supersessions)
        if old.value in self.supersessions:
            raise AdmissionError("knowledge already has a supersession")
        edge=Supersession(old,new,snapshot)
        payload={"schema":SUPERSESSION_SCHEMA,"id":f"supersession:{old.value}","old":old.value,"new":new.value,"snapshot":snapshot.value}
        try:
            self._persist("supersession", payload["id"], payload); self._db.commit()
        except Exception:
            self._db.rollback(); raise
        self.supersessions[old.value]=edge
        self._supersession_claimants.append((payload["id"], edge))
        return edge

    def _snapshot_descends_from(self, descendant, ancestor):
        current=self.open_snapshot(descendant)
        seen=set()
        while True:
            if current.id == ancestor: return True
            if current.parent is None or current.parent.value in seen: return False
            seen.add(current.id.value); current=self.open_snapshot(current.parent)

    def _visible_supersessions(self, snapshot):
        visible={}
        for old, edge in sorted(self.supersessions.items()):
            if self._snapshot_descends_from(snapshot, edge.snapshot):
                visible[old]=edge
        return visible

    def _effective_record_ids(self, snapshot_id):
        """Return the pure semantic record view for one explicit snapshot.

        Physical snapshot membership remains historical. A replacement is
        semantic evidence only on the branch where its validated edge is
        visible; ordinary records are never inferred to replace anything.
        """
        snapshot = self.open_snapshot(snapshot_id)
        visible = self._visible_supersessions(snapshot.id)
        effective = {record_id.value for record_id in snapshot.record_ids}
        replacement_targets = {edge.new.value for edge in self.supersessions.values()}
        visible_targets = {edge.new.value for edge in visible.values()}

        # Every visible edge masks its old identity.  This also resolves a
        # visible chain (A -> B -> C): A and B are both removed, while C
        # remains effective.  Non-visible branch edges never participate.
        effective.difference_update(visible)
        effective.difference_update(replacement_targets - visible_targets)

        # A derivation is semantically reusable only while every exact
        # dependency it was proved from remains effective.  Repeat to a fixed
        # point so a stale derived dependency invalidates its own dependants.
        changed = True
        while changed:
            changed = False
            for knowledge_id, derivation in self.derivations.items():
                if knowledge_id in effective and any(
                        dependency.value not in effective
                        for dependency in derivation.dependencies):
                    effective.remove(knowledge_id)
                    changed = True

        return tuple(record_id for record_id in snapshot.record_ids
                     if record_id.value in effective)

    def _decision_dependency_closure(self, problem):
        direct=[]
        grounding = self.decision_groundings.get(problem.scope_id.value)
        if grounding is not None:
            for observation in grounding.observations:
                evidence = observation.discovery_evidence
                if evidence is not None:
                    # Included discovery identities are scope-admission
                    # evidence.  A supersession can therefore change the
                    # historical candidate population and must stale the
                    # decision that relied on it.
                    direct.extend(evidence.included)
        for candidate in problem.candidates:
            result=candidate.grounding_result
            if result is not None: direct.extend(result.effective_dependencies)
            if candidate.objective_value is not None: direct.append(candidate.objective_value.knowledge_id)
        closure=[]; seen=set()
        def visit(knowledge_id):
            if knowledge_id.value in seen: return
            seen.add(knowledge_id.value); closure.append(knowledge_id)
            derivation=self.derivations.get(knowledge_id.value)
            if derivation is not None:
                for dependency in derivation.dependencies: visit(dependency)
        for dependency in direct: visit(dependency)
        return tuple(closure)

    def status_of(self, decision_id, *, relative_to=None):
        """Classify one historical decision against an explicit snapshot."""
        self._check()
        if relative_to is None: raise ValidationError("status_of requires an explicit reference snapshot")
        reference=_id(SnapshotId, relative_to)
        if reference.value not in self.snapshots:
            if ("snapshot", reference.value) in self.isolated:
                return ArtifactStatus.INVALID
            raise GroundingError("unknown reference snapshot")
        decision=self.decisions.get(_id(DecisionId, decision_id).value)
        if decision is None: return ArtifactStatus.INVALID
        try:
            problem=self.grounded_decision_problems[decision.source.value]
            validate_persisted_grounded_decision_problem(self, problem)
            validate_persisted_decision(self, decision)
            source=self.open_snapshot(problem.snapshot.value)
            if not self._snapshot_descends_from(reference, source.id):
                raise ValidationError("reference snapshot is not the decision snapshot or a descendant")
            dependencies=self._decision_dependency_closure(problem)
            visible=self._visible_supersessions(reference)
            if any(dependency.value in visible for dependency in dependencies):
                return ArtifactStatus.STALE
            return ArtifactStatus.CURRENT
        except (AtlasError, KeyError, TypeError, ValueError):
            return ArtifactStatus.INVALID

    def open_snapshot(self, ident): self._check(); return self.snapshots[_id(SnapshotId,ident).value]
    def read(self, ident, snapshot=None):
        self._check(); record=self.records.get(_id(KnowledgeId,ident).value); return record if snapshot is None or record and record.id in self.open_snapshot(snapshot).record_ids else None
    def find(self, *, kind=None, snapshot=None):
        self._check(); allowed=None if snapshot is None else set(self._effective_record_ids(snapshot)); return tuple(r for r in self.records.values() if (allowed is None or r.id in allowed) and (kind is None or (kind=="property" and isinstance(r,PropertyAssertion)) or (kind=="relation" and isinstance(r,RelationAssertion))))
    def ground(self, rule_id, bindings, snapshot, context):
        from .rules import ground
        return ground(self, rule_id, bindings, snapshot, context)

    def create_decision_scope(self, scope_id, snapshot, context, *, intention, request, manifest):
        """Atomically admit an immutable finite M1c.1 scope declaration."""
        self._check()
        scope=DecisionScope(_id(DecisionScopeId, scope_id), _id(SnapshotId, snapshot), _id(ContextId, context), _id(DescriptionId, intention), _id(DescriptionId, request), manifest if type(manifest) is GroundingManifest else _manifest_for_store(manifest))
        if scope.id.value in self.decision_scopes: raise AdmissionError("duplicate decision scope identity")
        validate_grounding_manifest(scope.manifest)
        validate_scope_environment(self, scope)
        payload=scope_payload(scope)
        try:
            self._persist("decision_scope", scope.id.value, payload); self._db.commit()
        except Exception:
            self._db.rollback(); raise
        self.decision_scopes[scope.id.value]=scope
        return scope

    def decision_scope(self, scope_id):
        self._check(); ident=_id(DecisionScopeId, scope_id)
        scope=self.decision_scopes.get(ident.value)
        if scope is None: raise GroundingError("unknown decision scope")
        return scope

    def ground_decision_scope(self, scope_id):
        """Pure evaluation: it never discovers, selects or persists."""
        return evaluate_scope(self, self.decision_scope(scope_id))

    def evaluate_decision_scope(self, scope_id):
        """Evaluate and atomically publish one immutable grounding result."""
        self._check(); scope=self.decision_scope(scope_id)
        if scope.id.value in self.decision_groundings: raise AdmissionError("decision scope grounding already exists")
        grounding=evaluate_scope(self, scope)
        try:
            self._persist("decision_grounding", scope.id.value, grounding_payload(grounding)); self._db.commit()
        except Exception:
            self._db.rollback(); raise
        self.decision_groundings[scope.id.value]=grounding
        return grounding

    def decision_grounding(self, scope_id):
        self._check(); ident=_id(DecisionScopeId, scope_id)
        grounding=self.decision_groundings.get(ident.value)
        if grounding is None: raise GroundingError("unknown decision scope grounding")
        return grounding

    def ground_decision_problem(self, decision_scope_id):
        """Purely materialize a problem from an existing persisted run."""
        from .problem import build_grounded_decision_problem
        return build_grounded_decision_problem(self, decision_scope_id)

    def admit_grounded_decision_problem(self, problem_id, problem):
        """Explicitly and atomically admit one already-grounded M1 problem."""
        self._check()
        from .identity import DecisionProblemId
        from .problem import build_grounded_decision_problem
        ident = problem_id if type(problem_id) is DecisionProblemId else DecisionProblemId(problem_id)
        if type(problem) is not GroundedDecisionProblem:
            raise ValidationError("admit_grounded_decision_problem requires a GroundedDecisionProblem")
        if ident.value in self.grounded_decision_problems:
            raise AdmissionError("duplicate grounded decision problem identity")
        expected = build_grounded_decision_problem(self, problem.scope_id)
        if problem != expected:
            raise ValidationError("grounded decision problem is not coherent with its historical sources")
        payload = grounded_decision_problem_payload(ident, problem)
        try:
            self._persist("grounded_decision_problem", ident.value, payload)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self.grounded_decision_problems[ident.value] = problem
        return problem

    def decision_problem(self, problem_id):
        self._check()
        from .identity import DecisionProblemId
        ident = problem_id if type(problem_id) is DecisionProblemId else DecisionProblemId(problem_id)
        problem = self.grounded_decision_problems.get(ident.value)
        if problem is None:
            raise GroundingError("unknown grounded decision problem")
        return problem

    def select_m1(self, problem_id):
        """Purely select from the exact persisted GDP identified by problem_id."""
        from .problem import _select_m1
        ident = problem_id if type(problem_id) is DecisionProblemId else DecisionProblemId(problem_id)
        problem = self.decision_problem(ident)
        grounding = self.decision_groundings.get(problem.scope_id.value)
        current = grounding is not None and grounding.schema == DECISION_GROUNDING_CURRENT_SCHEMA
        return _select_m1(ident, problem, current_scope_semantics=current)

    def admit_m1_decision(self, decision_id, selection_result):
        """Explicitly and atomically persist one pure M1 selection outcome."""
        self._check()
        from .identity import DecisionId
        if type(selection_result) is not M1SelectionResult:
            raise ValidationError("admit_m1_decision requires an exact M1SelectionResult")
        ident = decision_id if type(decision_id) is DecisionId else DecisionId(decision_id)
        decision = Decision(ident, selection_result.source, selection_result.status,
                            selection_result.optimum, selection_result.co_optima)
        if ident.value in self.decisions:
            raise AdmissionError("duplicate decision identity")
        problem = self.grounded_decision_problems.get(decision.source.value)
        if problem is None:
            raise GroundingError("decision references an invalid source grounded decision problem")
        grounding = self.decision_groundings.get(problem.scope_id.value)
        current = grounding is not None and grounding.schema == DECISION_GROUNDING_CURRENT_SCHEMA
        validate_persisted_decision(self, decision, current_scope_semantics=current)
        try:
            self._persist("decision", ident.value, decision_payload(decision))
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self.decisions[ident.value] = decision
        return decision

    def decision(self, decision_id):
        self._check()
        from .identity import DecisionId
        ident = decision_id if type(decision_id) is DecisionId else DecisionId(decision_id)
        decision = self.decisions.get(ident.value)
        if decision is None:
            raise GroundingError("unknown decision")
        return decision

    def explain_m1(self, decision_id):
        """Purely explain one persisted Decision through its exact historical GDP."""
        self._check()
        ident = _id(DecisionId, decision_id)
        decision = self.decision(ident)
        problem = self.grounded_decision_problems.get(decision.source.value)
        if problem is None:
            raise GroundingError("decision references an absent historical grounded decision problem")
        validate_persisted_grounded_decision_problem(self, problem)
        validate_persisted_decision(self, decision)
        grounding = self.decision_groundings.get(problem.scope_id.value)
        current = grounding is not None and grounding.schema == DECISION_GROUNDING_CURRENT_SCHEMA
        return _explain_m1(ident, decision, problem, self, current_scope_semantics=current)

    def decision_observations(self, scope_id):
        return self.decision_grounding(scope_id).observations

    def encountered_candidates(self, scope_id):
        return tuple(x.candidate for x in self.decision_observations(scope_id) if x.traversed)

    def admit_derived(self, knowledge_id, grounding_result):
        """Persist exactly the proof already contained in a TRUE grounding."""
        self._check()
        if type(grounding_result) is not GroundingResult:
            raise ValidationError("admit_derived requires an exact GroundingResult")
        if grounding_result.truth is not EvaluationTruth.TRUE or type(grounding_result.conclusion) is not GroundedConclusion:
            raise ValidationError("only TRUE groundings with a conclusion can be admitted")
        derived_id=_id(KnowledgeId,knowledge_id)
        conclusion=grounding_result.conclusion
        if conclusion.dependencies != grounding_result.effective_dependencies:
            raise ValidationError("grounding conclusion dependencies disagree with result")
        if grounding_result.missing_reads or grounding_result.ambiguous_reads:
            raise ValidationError("derived grounding cannot contain failed reads")
        if len(set(grounding_result.effective_dependencies)) != len(grounding_result.effective_dependencies):
            raise ValidationError("grounding contains duplicate dependencies")
        if conclusion.rule_id != grounding_result.rule_id or conclusion.rule_version != grounding_result.rule_version:
            raise ValidationError("grounding rule metadata is inconsistent")
        if derived_id.value in self.records:
            raise AdmissionError("duplicate knowledge identity")
        snapshot=self.snapshots.get(grounding_result.snapshot.value)
        if snapshot is None:
            raise GroundingError("derivation snapshot does not exist")
        if grounding_result.context not in snapshot.context_ids:
            raise GroundingError("derivation context is not present in snapshot")
        rule_matches=[x for x in snapshot.rule_definitions if x[0] == grounding_result.rule_id.value]
        if len(rule_matches) != 1 or rule_matches[0][1] != grounding_result.rule_version:
            raise GroundingError("derivation rule version is not fixed by snapshot")
        try:
            historical=json.loads(rule_matches[0][2]); declared=tuple(historical["participants"]); head=historical["head"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GroundingError("invalid historical derivation rule") from exc
        bindings=grounding_result.bindings
        if not isinstance(bindings, Mapping):
            raise ValidationError("grounding bindings require a mapping")
        if tuple(bindings) != declared or any(type(name) is not str or type(value) is not DescriptionId for name,value in bindings.items()):
            raise ValidationError("grounding bindings do not exactly match the rule")
        validate_grounding_evidence(grounding_result, declared)
        if any(bindings[name] not in snapshot.description_ids for name in declared):
            raise GroundingError("derivation binding is outside the grounding snapshot")
        if tuple(bindings[name] for name in head.get("participants", ())) != conclusion.term.participants:
            raise ValidationError("grounded conclusion participants disagree with bindings")
        if conclusion.term.predicate.value != head.get("predicate") or conclusion.term.version != head.get("version") or conclusion.polarity != head.get("polarity"):
            raise ValidationError("grounded conclusion term disagrees with historical rule")
        if any(dep.value not in self.records or dep not in snapshot.record_ids for dep in grounding_result.effective_dependencies):
            raise GroundingError("derivation dependency is absent from the grounding snapshot")
        context_matches=[x for x in snapshot.context_definitions if x[0] == grounding_result.context.value]
        if len(context_matches) != 1:
            raise GroundingError("derivation context definition is absent from snapshot")
        expected_scope=context_matches[0][1][0] if len(context_matches[0][1]) == 1 else tuple(context_matches[0][1])
        if conclusion.scope != expected_scope:
            raise ValidationError("grounded conclusion scope disagrees with historical context")
        expected_provenance=canonical_provenance(
            source for dependency in grounding_result.effective_dependencies
            for source in self.records[dependency.value].provenance)
        canonical_conclusion_provenance = canonical_provenance(conclusion.provenance)
        if canonical_conclusion_provenance != expected_provenance or not canonical_conclusion_provenance:
            raise ValidationError("grounded conclusion provenance disagrees with dependencies")
        if any(source.value not in self.sources for source in canonical_conclusion_provenance):
            raise ValidationError("derived relation requires resolvable provenance")
        if self._would_cycle(derived_id, grounding_result.effective_dependencies):
            raise ValidationError("derivation dependency cycle")
        ordered_bindings=tuple((name, bindings[name]) for name in declared)
        relation_scope=conclusion.scope if type(conclusion.scope) is str else tuple(conclusion.scope)
        relation_payload={
            "id": derived_id.value, "predicate": conclusion.term.predicate.value,
            "version": conclusion.term.version, "participants":[x.value for x in conclusion.term.participants],
            "polarity": conclusion.polarity, "scope": relation_scope if type(relation_scope) is str else list(relation_scope),
            "epistemic_status": conclusion.epistemic_status,
            "provenance":[x.value for x in canonical_conclusion_provenance], "derivation_id": derived_id.value,
        }
        derivation_payload={
            "id": derived_id.value, "knowledge_id": derived_id.value,
            "rule_id": grounding_result.rule_id.value, "rule_version": grounding_result.rule_version,
            "bindings":[{"participant":name,"description":description.value} for name,description in ordered_bindings],
            "snapshot": grounding_result.snapshot.value, "context": grounding_result.context.value,
            "dependencies":[x.value for x in grounding_result.effective_dependencies],
            "grounding_evidence": grounding_result.grounding_evidence,
        }
        relation=RelationAssertion(derived_id, conclusion.term.predicate, conclusion.term.version,
                                   conclusion.term.participants, conclusion.polarity, relation_scope,
                                   conclusion.epistemic_status, canonical_conclusion_provenance, derived_id)
        derivation=Derivation(derived_id, grounding_result.rule_id, grounding_result.rule_version,
                              ordered_bindings, grounding_result.snapshot, grounding_result.context,
                              grounding_result.effective_dependencies, grounding_result.grounding_evidence)
        try:
            self._persist("relation", derived_id.value, relation_payload)
            self._persist("derivation", derived_id.value, derivation_payload)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self.records[derived_id.value]=relation
        self.derivations[derived_id.value]=derivation
        return relation

    def _would_cycle(self, proposed, dependencies):
        def reaches(current, target, seen):
            if current == target: return True
            if current in seen: return False
            seen.add(current)
            derivation=self.derivations.get(current.value)
            return derivation is not None and any(reaches(dep, target, seen) for dep in derivation.dependencies)
        return any(reaches(dep, proposed, set()) for dep in dependencies)

    def dependencies(self, knowledge_id, transitive=False):
        self._check(); ident=_id(KnowledgeId,knowledge_id)
        if ident.value not in self.records: raise GroundingError("unknown knowledge identity")
        direct=self.derivations[ident.value].dependencies if ident.value in self.derivations else ()
        if not transitive: return direct
        result=[]; seen=set()
        def visit(node):
            if node in seen: return
            seen.add(node); result.append(node)
            for child in self.dependencies(node, transitive=False): visit(child)
        for dep in direct: visit(dep)
        return tuple(result)

    def provenance(self, knowledge_id, transitive=False):
        self._check(); ident=_id(KnowledgeId,knowledge_id)
        record=self.records.get(ident.value)
        if record is None: raise GroundingError("unknown knowledge identity")
        sources={source for source in record.provenance}
        if transitive:
            for dep in self.dependencies(ident, transitive=True):
                sources.update(self.records[dep.value].provenance)
        return canonical_provenance(sources)
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

def _latest_versions(entries):
    latest={}
    for ident, version in entries:
        if ident not in latest or version > latest[ident]:
            latest[ident]=version
    return tuple((ident, version) for ident, version in latest.items())

def _rule_text(value):
    if type(value) is not str or not value or any(0xD800 <= ord(char) <= 0xDFFF for char in value): raise ValidationError("rule participant must be an exact non-empty string")
    return value

def _validate_rule_payload(body, vocabulary, require_exact=False):
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
            if requested is None and (require_exact or len(versions) != 1): raise ValidationError("rule property version is not resolved")
            version = requested if requested is not None else versions[0]
            return vocabulary.properties[(property_id.value, version)].value_kind
        elif op in {"set_union", "set_subset"}:
            left_type, right_type = check_expr(expr.get("left")), check_expr(expr.get("right"))
            # An unknown child makes the complete expression an unsupported
            # extension.  Known operators, however, must have the exact M1
            # operand types and may not fall through to UNKNOWN at runtime.
            if left_type is None or right_type is None:
                return None
            if left_type != "finite_set<symbol>" or right_type != "finite_set<symbol>":
                raise ValidationError("set operator requires finite_set<symbol> operands")
            return "finite_set<symbol>" if op == "set_union" else "truth"
        # Other operators remain persistable but unsupported in M1.
        return None
    root_type = check_expr(body.get("when"))
    if root_type is not None and root_type != "truth":
        raise ValidationError("rule condition must be a truth-valued expression")

def _normalize_rule_payload(body, vocabulary):
    """Resolve compact property references once, at rule admission."""
    normalized = _freeze_json(body)
    def normalize_expr(expr):
        if type(expr) is not dict: return expr
        result = dict(expr)
        op = result.get("op")
        if op == "property" and "version" not in result:
            prop = _id(PropertyId, result.get("property"))
            versions = [version for ident, version in vocabulary.properties if ident == prop.value]
            if len(versions) != 1: raise ValidationError("ambiguous rule property version")
            result["version"] = versions[0]
        if op in {"set_union", "set_subset"}:
            result["left"] = normalize_expr(result.get("left"))
            result["right"] = normalize_expr(result.get("right"))
        return result
    result = dict(normalized)
    result["when"] = normalize_expr(result.get("when"))
    _validate_rule_payload(result, vocabulary, require_exact=True)
    return result

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
    for name in ("descriptions", "sources", "records", "rules", "contexts", "snapshots", "derivations", "decision_scopes", "decision_groundings", "grounded_decision_problems", "isolated"):
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
    for name in ("vocabulary", "descriptions", "sources", "records", "rules", "contexts", "snapshots", "derivations", "decision_scopes", "decision_groundings", "grounded_decision_problems", "isolated"):
        setattr(store, name, getattr(candidate, name))
    return store
