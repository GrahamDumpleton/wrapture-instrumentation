"""Applying and removing: the patched names on the module and on the
package's own proxy classes, and that removal leaves them all as
they were whatever the settings."""

from __future__ import annotations

import sqlite3
import sqlite3.dbapi2

import pytest
from wrapture import instrumentation

from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation, dbapi2


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "connect": sqlite3.connect,
        "dbapi2_connect": sqlite3.dbapi2.connect,
        "cursor_execute": dbapi2.Cursor.execute,
        "connection_execute": dbapi2.Connection.execute,
        "commit": dbapi2.Connection.commit,
        "exit": dbapi2.Connection.__exit__,
    }


@pytest.mark.parametrize("statement", [False, True])
def test_apply_then_remove_leaves_everything_as_it_was(statement: bool) -> None:
    # The statement setting shapes the recorded data, not the patch,
    # so the patched set is the same either way.

    before = choke_points()

    with instrumentation(SQLite3Instrumentation, statement=statement) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("sqlite3",)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied


def test_after_removal_connections_come_back_bare() -> None:
    with instrumentation(SQLite3Instrumentation):
        wrapped = sqlite3.connect(":memory:")
        assert isinstance(wrapped, dbapi2.Connection)
        wrapped.close()

    bare = sqlite3.connect(":memory:")
    try:
        assert type(bare) is sqlite3.Connection
    finally:
        bare.close()
