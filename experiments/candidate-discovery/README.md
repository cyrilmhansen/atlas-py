# Candidate discovery / semantic explosion POC

This experiment starts from the committed Semantic Kernel checkpoint and keeps
its catalogue idea, but uses a small standard-library-only search layer. The
search code knows only generic catalogue fields:

- a realization realizes one intent and requires zero or more resources;
- a producer builds one resource at a cost;
- a scenario may already contain resources.

The fixture names (`lookup`, `scan`, `S`, `H`, and so on) are data. They are not
branches in the discovery algorithm.

For each requested intent, the runner enumerates its realizations, resolves
each distinct required resource once, canonicalizes producer order, and sums
realization plus producer costs. This makes a shared producer emerge from
resource identity rather than from a special shared-sorted path.

This step only validates the known lookup/scan regressions and one shared
resource. It deliberately does not measure search-space growth or add pruning,
scheduling, mutation, lifetimes, uncertain costs, or a planner framework.

Step 2 tests are available separately. They add no branch to the planner and
exercise three consumers, 1/2/3/5/10 shared consumers, and H/D joint plans:

    PYTHONPATH=experiments/candidate-discovery \
      python3 experiments/candidate-discovery/step2_tests.py

Step 3 is a separate synthetic experiment. It measures a bounded naive search,
canonicalization, memoization and simple cost pruning over anonymous generated
catalogues:

    PYTHONPATH=experiments/candidate-discovery \
      python3 experiments/candidate-discovery/step3_explosion.py

From the repository root:

    PYTHONPATH=experiments/candidate-discovery \
      python3 experiments/candidate-discovery/run.py

The previous Semantic Kernel POC remains independently reproducible under
`experiments/semantic-kernel/`.
