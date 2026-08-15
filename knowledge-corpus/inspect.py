#!/usr/bin/env python3
"""Generic human-readable inspection of the atomic Atlas corpus."""

import json
import sys
from pathlib import Path


CORPUS = Path(__file__).with_name("associative-search.json")


def load():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def matches(item, mode, value):
    if mode == "all":
        return True
    if mode == "id":
        return item.get("id") == value
    if mode == "status":
        return item.get("status") == value
    if mode == "source":
        return item.get("provenance", {}).get("source_id") == value
    return item.get(mode) == value


def show(data, mode, value):
    descriptions = {item["id"]: item for item in data["descriptions"]}
    sources = {item["id"]: item for item in data["sources"]}
    rows = [item for item in data["assertions"] if matches(item, mode, value)]
    if not rows:
        print("no matching assertions")
        return
    for item in rows:
        subject_id = item["subject"]
        object_id = item.get("object")
        subject = descriptions.get(subject_id, {}).get("label", subject_id)
        target = descriptions.get(object_id, {}).get("label", object_id)
        source_id = item["provenance"]["source_id"]
        source = sources[source_id]
        provenance = item["provenance"]
        kind = provenance.get("kind", "source")
        print(f"{item['id']} [{item['status']}] {subject_id} ({subject}) --{item['predicate']}--> {object_id or '-'} ({target or '-'})")
        if "value" in item:
            print(f"  value: {item['value']}")
        print(f"  source: {source_id} / {source['title']}")
        print(f"  provenance_kind: {kind}")
        if kind == "derived":
            for basis_id in provenance["basis"]:
                basis = next(row for row in data["assertions"] if row["id"] == basis_id)
                basis_subject = descriptions[basis["subject"]]["label"]
                basis_object = descriptions.get(basis.get("object"), {}).get("label", basis.get("object", "-"))
                print(f"  basis: {basis_id} ({basis_subject} --{basis['predicate']}--> {basis_object})")
        print(f"  url: {source['url']}")
        print(f"  locator: {item['provenance']['locator']}")
        print(f"  evidence: {item['provenance']['evidence']}")
        print(f"  scope: {json.dumps(item['scope'], ensure_ascii=False, sort_keys=True)}")
        print(f"  assumptions: {json.dumps(item['assumptions'], ensure_ascii=False)}")


def main():
    modes = {"all", "id", "predicate", "subject", "object", "status", "source"}
    if len(sys.argv) not in {2, 3} or sys.argv[1] not in modes:
        raise SystemExit("usage: inspect.py all | id|predicate|subject|object|status|source VALUE")
    mode = sys.argv[1]
    value = sys.argv[2] if len(sys.argv) == 3 else None
    if mode == "all" and value is not None:
        raise SystemExit("usage: inspect.py all")
    if mode != "all" and value is None:
        raise SystemExit(f"usage: inspect.py {mode} VALUE")
    show(load(), mode, value)


if __name__ == "__main__":
    main()
