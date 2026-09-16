"""Test-only tracking for Store instances which outlive their test body."""

from contextvars import ContextVar


_stores = ContextVar("test_store_cleanup", default=None)


def start_store_cleanup():
    """Start a registry for the current test and return its reset token."""
    return _stores.set([])


def stop_store_cleanup(token):
    """Close every Store registered since *token* was created."""
    stores = _stores.get()
    failure = None
    try:
        for store in reversed(stores or ()):
            try:
                store.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
    finally:
        _stores.reset(token)
    if failure is not None:
        raise failure


def track_store(store):
    """Register a successfully constructed Store and return it unchanged."""
    stores = _stores.get()
    if stores is not None:
        stores.append(store)
    return store
