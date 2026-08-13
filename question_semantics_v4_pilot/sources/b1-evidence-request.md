The implementation batches writes to reduce per-operation overhead.

Question: At what batch size does batching become faster than one-by-one writes?

Evidence needed: a benchmark varying batch size from 1 to 1024 under the sustained-write workload.
