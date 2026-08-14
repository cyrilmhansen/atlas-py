#!/usr/bin/env python3
"""Reproduce the candidate-discovery experiment."""

import json

from candidate_discovery import run


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
