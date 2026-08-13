9.2.2. Idempotent Methods

A request method is considered idempotent if the intended effect on the server of multiple identical requests with that method is the same as the effect for a single such request. PUT, DELETE, and safe request methods are idempotent.

The idempotent property only applies to what has been requested by the user; a server is free to log each request separately or retain a revision control history. Idempotent methods are distinguished because the request can be repeated automatically if a communication failure occurs before the client is able to read the server's response.

A client SHOULD NOT automatically retry a request with a non-idempotent method unless it has some means to know that the request semantics are actually idempotent, or some means to detect that the original request was never applied.
