Multiple processes can have the same SQLite database open at the same time, and multiple processes can be doing a SELECT at the same time. Only one process can be making changes to the database at any moment.

Client/server database engines usually support a higher level of concurrency and allow multiple processes to write at the same time. If an application needs a lot of concurrency, it should consider a client/server database. Experience suggests that most applications need much less concurrency than their designers imagine.
