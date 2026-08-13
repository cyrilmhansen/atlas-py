std::stable_sort sorts the elements in a range in non-descending order. The order of equivalent elements is guaranteed to be preserved. The comparison function must impose the required ordering and must not modify the objects passed to it.

If the iterator value type does not satisfy the required move, assignment, or swappable conditions, the behavior is undefined. The stability guarantee is therefore not a claim that applies without the algorithm's stated preconditions.
