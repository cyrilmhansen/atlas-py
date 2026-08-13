"""Create the fixed claims/questions stress corpus from authoritative excerpts."""
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).parent
SOURCES = ROOT / "sources"

CASES = [
    {
        "id": "rfc9110-safe-methods",
        "source": "IETF RFC 9110, HTTP Semantics",
        "locator": "section 9.2.1 Safe Methods",
        "url": "https://www.rfc-editor.org/rfc/rfc9110.html#name-safe-methods",
        "why_selected": "Explicit comparison of read-only intent with implementation side effects.",
        "pressure": "qualified comparison; exception; negative statement",
        "text": """9.2.1. Safe Methods

Request methods are considered safe if their defined semantics are essentially read-only; that is, the client does not request, and does not expect, any state change on the origin server as a result of applying a safe method to a target resource.

This definition of safe methods does not prevent an implementation from including behavior that is potentially harmful, that is not entirely read-only, or that causes side effects while invoking a safe method. What is important, however, is that the client did not request that additional behavior and cannot be held accountable for it.

Of the request methods defined by this specification, GET, HEAD, OPTIONS, and TRACE are defined to be safe.""",
    },
    {
        "id": "rfc9110-idempotent-retry",
        "source": "IETF RFC 9110, HTTP Semantics",
        "locator": "section 9.2.2 Idempotent Methods",
        "url": "https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods",
        "why_selected": "Conditional conclusion about retries and a distinction between intended effects and incidental effects.",
        "pressure": "conditional conclusion; exception",
        "text": """9.2.2. Idempotent Methods

A request method is considered idempotent if the intended effect on the server of multiple identical requests with that method is the same as the effect for a single such request. PUT, DELETE, and safe request methods are idempotent.

The idempotent property only applies to what has been requested by the user; a server is free to log each request separately or retain a revision control history. Idempotent methods are distinguished because the request can be repeated automatically if a communication failure occurs before the client is able to read the server's response.

A client SHOULD NOT automatically retry a request with a non-idempotent method unless it has some means to know that the request semantics are actually idempotent, or some means to detect that the original request was never applied.""",
    },
    {
        "id": "sqlite-index-statistics",
        "source": "SQLite Query Planning",
        "locator": "sections 1.5 and 1.6, index choice and ANALYZE",
        "url": "https://www.sqlite.org/queryplanner.html#_multiple_result_rows",
        "why_selected": "Competing indexes can produce different choices; the conclusion depends on collected statistics.",
        "pressure": "explicit comparison; conditional conclusion",
        "text": """Suppose a query can use more than one index. If ANALYZE has been run, SQLite can know that one index usually narrows the search to fewer rows than another. If all else is equal, SQLite chooses the index with the hope of narrowing the search to as small a number of rows as possible. This choice is only possible because of the statistics provided by ANALYZE. If ANALYZE has not been run then the choice of which index to use is arbitrary.

A multi-column index uses the left-most column to order rows and later columns to break ties. With a suitable multi-column index, SQLite can find a constrained row with fewer searches than with separate lookups.""",
    },
    {
        "id": "sqlite-or-union",
        "source": "SQLite Query Planning",
        "locator": "section 1.8, OR-connected terms",
        "url": "https://www.sqlite.org/queryplanner.html#_or_connected_terms_in_the_where_clause",
        "why_selected": "A proposed alternative is explicitly limited by an unindexed term and described as a possible future feature.",
        "pressure": "competing mechanisms; negative statement; future question",
        "text": """When confronted with OR-connected terms, SQLite examines each OR term separately and tries to use an index to find the rowids associated with each term. It then takes the union of the resulting rowid sets.

For the OR-by-UNION technique to be useful, there must be an index available that helps resolve every OR-connected term. If even a single OR-connected term is not indexed, a full table scan would have to be done for that term, and a full table scan may be preferable to the union operation and follow-on searches.

One can see how the OR-by-UNION technique could also be leveraged for AND-connected terms by using an intersect operator in place of union. The performance gain is slight, so SQLite does not implement that technique at this time. A future version might be enhanced to support AND-by-INTERSECT.""",
    },
    {
        "id": "sqlite-indexed-sort",
        "source": "SQLite Query Planning",
        "locator": "sections 2.1–2.3, sorting by index",
        "url": "https://www.sqlite.org/queryplanner.html#_sorting_by_index",
        "why_selected": "Two plans have similar asymptotic work but different temporary-storage consequences, so the preferred plan is contextual.",
        "pressure": "explicit comparison; representation trade-off; conditional conclusion",
        "text": """When no appropriate index is available, an ORDER BY query gathers the output and runs it through a sorter, which can require substantial temporary storage. If an index is available on the ORDER BY column, SQLite can scan that index and perform rowid lookups instead.

The index scan and the indexless sort can both require work proportional to N log N. SQLite uses a cost-based query planner and estimates the total time for each plan. The choice can therefore depend on table size and WHERE-clause constraints. The indexed sort generally uses less temporary storage because it does not accumulate the entire result before sorting.

A covering index can avoid the rowid lookups and reduce the cost further.""",
    },
    {
        "id": "python-sort-stability",
        "source": "Python Sorting Techniques documentation",
        "locator": "Sorting Basics; Sort Stability and Complex Sorts",
        "url": "https://docs.python.org/3/howto/sorting.html#sort-stability-and-complex-sorts",
        "why_selected": "The source states a guarantee, then derives a compositional use from it; stable and in-place forms have different contracts.",
        "pressure": "qualified comparison; mechanism equivalence",
        "text": """A simple ascending sort can use sorted(), which returns a new sorted list, or list.sort(), which modifies the list in-place. list.sort() is only defined for lists, while sorted() accepts any iterable.

Sorts are guaranteed to be stable. When multiple records have the same key, their original order is preserved. This property lets a programmer build complex sorts in a series of sorting steps. The Timsort algorithm used in Python can take advantage of any ordering already present in a dataset.""",
    },
    {
        "id": "python-heapq-merge",
        "source": "Python heapq documentation",
        "locator": "heapq.merge and nsmallest/nlargest",
        "url": "https://docs.python.org/3/library/heapq.html#heapq.merge",
        "why_selected": "The same ordered result can be produced by streaming merge or materialized sorting, with different memory assumptions and size regimes.",
        "pressure": "competing mechanisms; representation trade-off; conditional conclusion",
        "text": """heapq.merge merges multiple sorted inputs into a single sorted output. It returns an iterator, does not pull the data into memory all at once, and assumes each input stream is already sorted.

heapq.nsmallest and heapq.nlargest perform best for smaller values of n. For larger values, it is more efficient to use sorted(). When n is one, min() or max() is more efficient. If repeated usage is required, consider turning the iterable into an actual heap.""",
    },
    {
        "id": "python-heapq-open-questions",
        "source": "Python heapq documentation",
        "locator": "Priority Queue Implementation Notes",
        "url": "https://docs.python.org/3/library/heapq.html#priority-queue-implementation-notes",
        "why_selected": "The source contains explicit design questions and a concrete evidence-bearing implementation response.",
        "pressure": "explicit open question; evidence requirement; exception",
        "text": """A priority queue is a common use for a heap, and it presents several implementation challenges:

How do you get two tasks with equal priorities to be returned in the order they were originally added?

Tuple comparison breaks for (priority, task) pairs if the priorities are equal and the tasks do not have a default comparison order.

If the priority of a task changes, how do you move it to a new position in the heap? Or if a pending task needs to be deleted, how do you find it and remove it from the queue?

A solution to the first two challenges is to store priority, an entry count, and the task. The entry count serves as a tie-breaker and prevents tuple comparison from directly comparing tasks.""",
    },
    {
        "id": "cpp-stable-sort",
        "source": "cppreference, std::stable_sort",
        "locator": "Effects and complexity notes",
        "url": "https://en.cppreference.com/cpp/algorithm/stable_sort",
        "why_selected": "A standard-library contract explicitly preserves equivalent-element order and has preconditions distinct from ordinary sorting.",
        "pressure": "explicit comparison; precondition; local guarantee",
        "text": """std::stable_sort sorts the elements in a range in non-descending order. The order of equivalent elements is guaranteed to be preserved. The comparison function must impose the required ordering and must not modify the objects passed to it.

If the iterator value type does not satisfy the required move, assignment, or swappable conditions, the behavior is undefined. The stability guarantee is therefore not a claim that applies without the algorithm's stated preconditions.""",
    },
    {
        "id": "sqlite-concurrency",
        "source": "SQLite Frequently Asked Questions",
        "locator": "FAQ 5, concurrent access",
        "url": "https://sqlite.org/faq.html#q5",
        "why_selected": "The source compares embedded-file concurrency with client/server systems and explicitly limits the conclusion by workload.",
        "pressure": "qualified comparison; local exception",
        "text": """Multiple processes can have the same SQLite database open at the same time, and multiple processes can be doing a SELECT at the same time. Only one process can be making changes to the database at any moment.

Client/server database engines usually support a higher level of concurrency and allow multiple processes to write at the same time. If an application needs a lot of concurrency, it should consider a client/server database. Experience suggests that most applications need much less concurrency than their designers imagine.""",
    },
    {
        "id": "sqlite-dynamic-typing",
        "source": "SQLite Frequently Asked Questions",
        "locator": "FAQ 2–3, datatypes and affinity",
        "url": "https://sqlite.org/faq.html#q3",
        "why_selected": "An apparent contradiction is resolved by an explicit exception and a qualified description of type affinity.",
        "pressure": "explicit question; exception; non-affirmation",
        "text": """What datatypes does SQLite support? SQLite uses dynamic typing. Content can be stored as INTEGER, REAL, TEXT, BLOB, or NULL.

SQLite does not enforce data type constraints in the usual way. Data of any type can usually be inserted into any column. There is one exception: columns declared INTEGER PRIMARY KEY may only hold a 64-bit signed integer. SQLite uses a declared type as a hint, called type affinity, and attempts conversions when possible.""",
    },
    {
        "id": "sqlite-explain-evidence",
        "source": "SQLite Requirement Matrix, EXPLAIN",
        "locator": "EXPLAIN QUERY PLAN requirement R-01592-27714",
        "url": "https://www2.sqlite.org/draft/matrix/matrix_dlang_explain.html",
        "why_selected": "The requirement explicitly ties a statement about planner behavior to a named evidence test.",
        "pressure": "explicit evidence requirement; source-to-test relation",
        "text": """EVIDENCE-OF: R-01592-27714

When the EXPLAIN QUERY PLAN phrase appears, the statement returns high-level information regarding the query plan that would have been used.

The requirement is accompanied by a test reference in the SQLite test suite.""",
    },
]


def main() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    manifest = []
    for case in CASES:
        path = SOURCES / f"{case['id']}.md"
        path.write_text(case["text"].strip() + "\n", encoding="utf-8")
        manifest.append({
            key: case[key] for key in ("id", "source", "locator", "url", "why_selected", "pressure")
        } | {"local_path": str(path), "content_hash": sha256(path.read_bytes()).hexdigest()})
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"created {len(manifest)} fixed sources")


if __name__ == "__main__":
    main()
