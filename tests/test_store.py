import gc
import sqlite3
import warnings

import pytest

from atlas import open_store


def test_constructor_failure_closes_sqlite_connection(tmp_path, monkeypatch):
    path = tmp_path / "incompatible.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE records (id TEXT)")
    db.commit()
    db.close()

    real_connect = sqlite3.connect
    opened = []

    def tracked_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr("atlas.store.sqlite3.connect", tracked_connect)

    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        open_store(path)

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        opened[0].execute("SELECT 1")
