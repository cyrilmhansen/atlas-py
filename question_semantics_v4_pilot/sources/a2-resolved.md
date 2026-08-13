An ordered index is used to answer lookups.

Question: Does rebuilding the index after each update preserve latency under sustained writes?

Yes. In this implementation the index is rebuilt after each update, and the bounded workload test reports stable latency under sustained writes. The question is therefore resolved within this passage.
