#!/usr/bin/env python3
"""Reproduce the semantic-kernel step-1 scenarios."""

import json

from semantic_kernel_poc import run


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
