#!/usr/bin/env python3
"""Specialized batch program derived after composition selection."""

import json


BLOCK = 64


def load(count):
    return [(index, (index * 17 + 3) % 1009) for index in range(count)]


def select(data, mode):
    if mode == "sparse":
        return [record for record in data if record[0] % 8 == 0]
    return [record for record in data if record[0] % 8 != 0]


def transform_block(block, effort):
    result = []
    for _, original in block:
        value = original
        for step in range(effort):
            value = (value * 3 + step + 1) % 1_000_003
        result.append(value)
    return result


def run(count, mode, effort):
    selected = select(load(count), mode)
    total = 0
    for start in range(0, len(selected), BLOCK):
        for value in transform_block(selected[start:start + BLOCK], effort):
            total += value
    return {"accepted": len(selected), "checksum": total}


if __name__ == "__main__":
    print(json.dumps({
        "sparse": run(4096, "sparse", 2),
        "dense": run(4096, "dense", 8),
    }, sort_keys=True))
