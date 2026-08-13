When confronted with OR-connected terms, SQLite examines each OR term separately and tries to use an index to find the rowids associated with each term. It then takes the union of the resulting rowid sets.

For the OR-by-UNION technique to be useful, there must be an index available that helps resolve every OR-connected term. If even a single OR-connected term is not indexed, a full table scan would have to be done for that term, and a full table scan may be preferable to the union operation and follow-on searches.

One can see how the OR-by-UNION technique could also be leveraged for AND-connected terms by using an intersect operator in place of union. The performance gain is slight, so SQLite does not implement that technique at this time. A future version might be enhanced to support AND-by-INTERSECT.
