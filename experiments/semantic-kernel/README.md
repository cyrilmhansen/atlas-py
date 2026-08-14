# Semantic Kernel POC — step 1

The prototype uses egglog to store descriptions and facts for one intent:
lookup(collection,key). It compares linear lookup with binary lookup over an
existing or newly built sorted representation.

From the repository root:

    python3 -m venv /tmp/atlas-semantic-kernel-venv
    /tmp/atlas-semantic-kernel-venv/bin/pip install -r experiments/semantic-kernel/requirements.txt
    PYTHONPATH=experiments/semantic-kernel /tmp/atlas-semantic-kernel-venv/bin/python experiments/semantic-kernel/run.py

The step-4 surprise tests are run separately and intentionally do not extend
the composition search layer:

    PYTHONPATH=experiments/semantic-kernel /tmp/atlas-semantic-kernel-venv/bin/python experiments/semantic-kernel/surprise_tests.py

The two closing tests are also separate and do not generalize composition
discovery:

    PYTHONPATH=experiments/semantic-kernel /tmp/atlas-semantic-kernel-venv/bin/python experiments/semantic-kernel/closure_tests.py

The e-graph contains the semantic facts. The Python code only evaluates the
small abstract cost equations for the fixed scenarios.
