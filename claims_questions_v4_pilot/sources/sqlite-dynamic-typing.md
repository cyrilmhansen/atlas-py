What datatypes does SQLite support? SQLite uses dynamic typing. Content can be stored as INTEGER, REAL, TEXT, BLOB, or NULL.

SQLite does not enforce data type constraints in the usual way. Data of any type can usually be inserted into any column. There is one exception: columns declared INTEGER PRIMARY KEY may only hold a 64-bit signed integer. SQLite uses a declared type as a hint, called type affinity, and attempts conversions when possible.
