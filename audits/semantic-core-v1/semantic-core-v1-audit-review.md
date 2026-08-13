Review of Laguna audit
The Laguna audit is preserved verbatim in semantic-core-v1-audit-laguna.md.

Its central conclusion is retained: Semantic Core v1 improves the semantic mechanism, but the committed N=66/N=119 values are not demonstrated physical QuickDraw break-even points.

Qualifications:

F1 should be weakened. The Python B0→runs conversion does preserve its own source logical Region through round-trip. What fails for sparse is the asserted identity between that source specimen and the QuickDraw 3 B0 result. Distinguish transformation preservation from specimen identity.

F3 should be MAJOR rather than CRITICAL. The observed 4.9–12.3 ms inter-run variation demonstrates that the present protocol does not support a stable N=66 claim; five runs are insufficient to characterize the underlying distribution.

The predicted speedup of a C conversion is a hypothesis, not an audited result. Only the incompatibility of the Python conversion timing with a claimed native QuickDraw lifecycle is established.

The strongest remaining semantic counterexample was not identified by Laguna. repeat constrains the count to ReuseCount, but does not relate that count to the operation whose occurrences it counts. Thus repeat(reuse_count, build_time) appears semantically admissible although the scenario's reuse count denotes repeated application, not rebuilding. The unresolved distinction is therefore not merely generalizing Repeat beyond ReuseCount; it is relating an occurrence count to its counted event.

The transformed workload label sparse_sparse_intersection vs case=sparse_sparse, op=intersect is considered a reversible representation choice, not a meaningful provenance defect.

The v0 sparse bbox discrepancy is real but is not evidence against the v1 break-even experiment.

Retained status:

Confirmed: ReuseCount vs RunCount is a necessary distinction and v1 fixes the precise v0 multiplication defect.

Disproved: kind/unit/workload/file-source metadata alone are sufficient to establish compatibility of physical observations.

Unknown: the minimal representation needed for specimen identity, measurement lineage, and count↔event relations without introducing a general provenance/type ontology.

N=66 and N=119 remain historical outputs of Semantic Core v1, not QuickDraw performance knowledge.
