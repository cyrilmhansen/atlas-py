#!/usr/bin/env python3
"""Small buffered batch program."""

import json


BLOCK = 64


def make_input(count):
    result = []
    for index in range(count):
        result.append((index, (index * 17 + 3) % 1009))
    return result


def select(data, mode):
    if mode == "sparse":
        return [record for record in data if record[0] % 8 == 0]
    return [record for record in data if record[0] % 8 != 0]


def convert(block, effort):
    result = []
    for _, original in block:
        value = original
        for step in range(effort):
            value = (value * 3 + step + 1) % 1_000_003
        result.append(value)
    return result


def run(count, mode, effort):
    selected = select(make_input(count), mode)
    converted = []
    for start in range(0, len(selected), BLOCK):
        converted.extend(convert(selected[start:start + BLOCK], effort))
    return {"accepted": len(selected), "checksum": sum(converted)}


if __name__ == "__main__":
    print(json.dumps({
        "sparse": run(4096, "sparse", 2),
        "dense": run(4096, "dense", 8),
    }, sort_keys=True))
