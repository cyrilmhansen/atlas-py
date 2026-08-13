heapq.merge merges multiple sorted inputs into a single sorted output. It returns an iterator, does not pull the data into memory all at once, and assumes each input stream is already sorted.

heapq.nsmallest and heapq.nlargest perform best for smaller values of n. For larger values, it is more efficient to use sorted(). When n is one, min() or max() is more efficient. If repeated usage is required, consider turning the iterable into an actual heap.
