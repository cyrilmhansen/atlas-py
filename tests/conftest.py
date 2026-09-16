"""Keep the local W1 command package importable without changing core packaging."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest

from atlas import Store
from store_cleanup import start_store_cleanup, stop_store_cleanup, track_store


@pytest.fixture(autouse=True)
def close_test_stores(monkeypatch):
    """Close all Stores made by a test, including Stores made by helpers."""
    token = start_store_cleanup()
    original_init = Store.__init__

    def tracked_init(store, path):
        original_init(store, path)
        track_store(store)

    monkeypatch.setattr(Store, "__init__", tracked_init)
    try:
        yield
    finally:
        stop_store_cleanup(token)
