A priority queue is a common use for a heap, and it presents several implementation challenges:

How do you get two tasks with equal priorities to be returned in the order they were originally added?

Tuple comparison breaks for (priority, task) pairs if the priorities are equal and the tasks do not have a default comparison order.

If the priority of a task changes, how do you move it to a new position in the heap? Or if a pending task needs to be deleted, how do you find it and remove it from the queue?

A solution to the first two challenges is to store priority, an entry count, and the task. The entry count serves as a tie-breaker and prevents tuple comparison from directly comparing tasks.
