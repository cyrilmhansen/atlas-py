A simple ascending sort can use sorted(), which returns a new sorted list, or list.sort(), which modifies the list in-place. list.sort() is only defined for lists, while sorted() accepts any iterable.

Sorts are guaranteed to be stable. When multiple records have the same key, their original order is preserved. This property lets a programmer build complex sorts in a series of sorting steps. The Timsort algorithm used in Python can take advantage of any ordering already present in a dataset.
