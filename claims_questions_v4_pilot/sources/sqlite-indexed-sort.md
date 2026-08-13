When no appropriate index is available, an ORDER BY query gathers the output and runs it through a sorter, which can require substantial temporary storage. If an index is available on the ORDER BY column, SQLite can scan that index and perform rowid lookups instead.

The index scan and the indexless sort can both require work proportional to N log N. SQLite uses a cost-based query planner and estimates the total time for each plan. The choice can therefore depend on table size and WHERE-clause constraints. The indexed sort generally uses less temporary storage because it does not accumulate the entire result before sorting.

A covering index can avoid the rowid lookups and reduce the cost further.
