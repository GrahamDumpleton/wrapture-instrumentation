"""With the sqlite3 driver instrumentation applied alongside: the
default leaf keeps the driver's events out of the tree, leaf off
nests them beneath each statement, and raw driver use beside the
engine still records."""

from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text
from wrapture import Event, Tape, instrumentation, timeline

from wrapture_instrumentation.database.sqlalchemy import SQLAlchemyInstrumentation
from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation

EXECUTE = "sqlalchemy.engine.default:DefaultDialect.do_execute"
CONNECT = "sqlalchemy.engine.default:DefaultDialect.connect"
COMMIT = "sqlalchemy.engine.base:Connection._commit_impl"


def labelled(tape: Tape, label: str) -> list[Event]:
    return [event for event in tape.all if event.label == label]


def workload() -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE items (name TEXT)"))
        connection.execute(text("INSERT INTO items VALUES ('widget')"))
        connection.execute(text("SELECT name FROM items")).fetchall()

    engine.dispose()


def test_the_default_leaf_keeps_the_driver_out() -> None:
    with (
        instrumentation(SQLite3Instrumentation),
        instrumentation(SQLAlchemyInstrumentation),
        timeline() as tape,
    ):
        workload()

    # Every statement and the connect run beneath a sqlalchemy leaf,
    # so the driver's own events stay out of the workload's queries.
    # What may remain is SQLAlchemy's own raw driver work outside the
    # recorded seams: the dialect's connection setup (an
    # isolation-level PRAGMA on SQLite) and the pool's
    # reset-on-return rollback.

    strays = labelled(tape, "sqlite3:Cursor.execute")
    assert all(event.data["operation"] == "PRAGMA" for event in strays)
    assert labelled(tape, "sqlite3:Connection.commit") == []
    assert [ev for ev in tape.all if ev.path == "sqlite3.dbapi2:connect"] == []

    assert len([ev for ev in tape.all if ev.path == EXECUTE]) == 3


def test_leaf_off_shows_the_driver_beneath() -> None:
    with (
        instrumentation(SQLite3Instrumentation),
        instrumentation(SQLAlchemyInstrumentation, leaf=False),
        timeline() as tape,
    ):
        workload()

    # Each dialect-level event now carries the driver's own event
    # beneath it: the cursor execute under do_execute, the driver
    # connect under the dialect's, the driver commit under the
    # transaction boundary.

    (select,) = [
        ev for ev in tape.all if ev.path == EXECUTE and ev.data["operation"] == "SELECT"
    ]
    assert [child.label for child in tape.children_of(select)] == [
        "sqlite3:Cursor.execute"
    ]

    (opened,) = [ev for ev in tape.all if ev.path == CONNECT]
    assert [child.path for child in tape.children_of(opened)] == [
        "sqlite3.dbapi2:connect"
    ]

    (commit,) = [ev for ev in tape.all if ev.path == COMMIT]
    assert [child.label for child in tape.children_of(commit)] == [
        "sqlite3:Connection.commit"
    ]


def test_raw_driver_use_beside_the_engine_still_records() -> None:
    with (
        instrumentation(SQLite3Instrumentation),
        instrumentation(SQLAlchemyInstrumentation),
        timeline() as tape,
    ):
        workload()

        connection = sqlite3.connect(":memory:")
        connection.execute("SELECT 1")
        connection.close()

    (event,) = labelled(tape, "sqlite3:Connection.execute")
    assert event.data["operation"] == "SELECT"
