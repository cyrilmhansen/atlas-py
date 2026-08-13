9.2.1. Safe Methods

Request methods are considered safe if their defined semantics are essentially read-only; that is, the client does not request, and does not expect, any state change on the origin server as a result of applying a safe method to a target resource.

This definition of safe methods does not prevent an implementation from including behavior that is potentially harmful, that is not entirely read-only, or that causes side effects while invoking a safe method. What is important, however, is that the client did not request that additional behavior and cannot be held accountable for it.

Of the request methods defined by this specification, GET, HEAD, OPTIONS, and TRACE are defined to be safe.
