#!/usr/bin/env python3
"""Small streaming batch program."""

import json


def records(count):
    return [(index, (index * 17 + 3) % 1009) for index in range(count)]


def keep(record, mode):
    if mode == "sparse":
        return record[0] % 8 == 0
    return record[0] % 8 != 0


def transform(record, effort):
    value = record[1]
    for step in range(effort):
        value = (value * 3 + step + 1) % 1_000_003
    return value


def run(count, mode, effort):
    total = 0
    accepted = 0
    for record in records(count):
        if keep(record, mode):
            total += transform(record, effort)
            accepted += 1
    return {"accepted": accepted, "checksum": total}


if __name__ == "__main__":
    print(json.dumps({
        "sparse": run(4096, "sparse", 2),
        "dense": run(4096, "dense", 8),
    }, sort_keys=True))
