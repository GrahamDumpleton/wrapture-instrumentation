"""What the instrumentation records: every statement at the dialect
seam, Core and ORM, sync and async, the connections the pool opens,
the transaction boundaries, and what stays out of capture."""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from wrapture import Event, Tape, instrumentation, timeline

from wrapture_instrumentation.database.sqlalchemy import SQLAlchemyInstrumentation

EXECUTE = "sqlalchemy.engine.default:DefaultDialect.do_execute"
EXECUTEMANY = "sqlalchemy.engine.default:DefaultDialect.do_executemany"
CONNECT = "sqlalchemy.engine.default:DefaultDialect.connect"
COMMIT = "sqlalchemy.engine.base:Connection._commit_impl"
ROLLBACK = "sqlalchemy.engine.base:Connection._rollback_impl"

SQLALCHEMY_2 = sqlalchemy.__version__.startswith("2.")


def at(tape: Tape, path: str) -> list[Event]:
    return [event for event in tape.all if event.path == path]


def items_table() -> tuple[MetaData, Table]:
    metadata = MetaData()

    table = Table(
        "items",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String),
    )

    return metadata, table


def test_a_select_records_a_database_leaf(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    engine.dispose()

    (event,) = [ev for ev in at(tape, EXECUTE) if ev.data["operation"] == "SELECT"]
    assert event.category == "database"
    assert event.label is None
    assert event.data == {
        "system": "sqlite",
        "operation": "SELECT",
        "database": ":memory:",
    }
    assert tape.children_of(event) == []

    # The SQL reduces to its length in the captured arguments, the
    # parameters to a count.

    assert event.arguments is not None
    assert event.arguments["statement"] == "<8 chars>"
    assert event.arguments["parameters"] == "<0 values>"


def test_the_pool_opening_a_connection_records(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    engine.dispose()

    # The connect's arguments are the driver's credentials, so
    # nothing of them is captured.

    (event,) = at(tape, CONNECT)
    assert event.category == "database"
    assert event.data == {"system": "sqlite", "operation": "CONNECT"}
    assert event.arguments is None


def test_the_statement_setting_records_the_compiled_text() -> None:
    with (
        instrumentation(SQLAlchemyInstrumentation, statement=True),
        timeline() as tape,
    ):
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as connection:
            connection.execute(text("CREATE TABLE items (name TEXT)"))
            connection.execute(
                text("INSERT INTO items VALUES (:name)"), {"name": "widget"}
            )
        engine.dispose()

    # The compiled text carries the placeholder, never the value.

    (event,) = [ev for ev in tape.all if ev.data.get("operation") == "INSERT"]
    assert event.data["statement"] == "INSERT INTO items VALUES (?)"
    assert "widget" not in repr(event.data)
    assert "widget" not in repr(event.arguments)


def test_parameters_never_reach_the_record(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        connection.execute(text("CREATE TABLE items (name TEXT)"))
        connection.execute(
            text("INSERT INTO items VALUES (:name)"), {"name": "a-secret-value"}
        )
    engine.dispose()

    (event,) = [ev for ev in tape.all if ev.data.get("operation") == "INSERT"]
    assert event.arguments is not None
    assert event.arguments["parameters"] == "<1 values>"
    assert "a-secret-value" not in repr(event.arguments)
    assert "a-secret-value" not in repr(event.data)


def test_an_executemany_records_one_event(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        connection.execute(text("CREATE TABLE items (name TEXT)"))
        connection.execute(
            text("UPDATE items SET name = :new WHERE name = :old"),
            [{"new": "a", "old": "b"}, {"new": "c", "old": "d"}],
        )
    engine.dispose()

    (event,) = at(tape, EXECUTEMANY)
    assert event.data["operation"] == "UPDATE"
    assert event.arguments is not None
    assert event.arguments["parameters"] == "<2 values>"


def test_an_insert_construct_with_many_rows_records(tape: Tape) -> None:
    metadata, items = items_table()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(insert(items), [{"name": "a"}, {"name": "b"}, {"name": "c"}])
    engine.dispose()

    inserts = [ev for ev in at(tape, EXECUTEMANY) if ev.data["operation"] == "INSERT"]
    assert len(inserts) == 1
    assert inserts[0].data["system"] == "sqlite"


def test_an_orm_session_records_its_work(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")

    with Session(engine) as session:
        session.execute(text("SELECT 1"))
        session.commit()
    engine.dispose()

    selects = [ev for ev in at(tape, EXECUTE) if ev.data["operation"] == "SELECT"]
    assert len(selects) == 1

    (commit,) = at(tape, COMMIT)
    assert commit.data["operation"] == "COMMIT"


def test_commit_and_rollback_record_their_operations(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()

    transaction = connection.begin()
    connection.execute(text("CREATE TABLE items (name TEXT)"))
    transaction.commit()

    transaction = connection.begin()
    connection.execute(text("INSERT INTO items VALUES ('dropped')"))
    transaction.rollback()

    connection.close()
    engine.dispose()

    (commit,) = at(tape, COMMIT)
    assert commit.category == "database"
    assert commit.data == {
        "system": "sqlite",
        "operation": "COMMIT",
        "database": ":memory:",
    }

    (rollback,) = at(tape, ROLLBACK)
    assert rollback.data["operation"] == "ROLLBACK"


def test_a_pooled_checkin_reset_is_not_recorded(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    engine.dispose()

    # The pool rolls the connection back as it goes back to the pool,
    # below the recorded seam. What records is only the transaction
    # SQLAlchemy itself ends: on 2.0 the close rolls back the
    # autobegun transaction, on 1.4 a bare select opens none.

    expected = 1 if SQLALCHEMY_2 else 0
    assert len(at(tape, ROLLBACK)) == expected


def test_a_failing_statement_records_the_driver_exception(tape: Tape) -> None:
    engine = create_engine("sqlite:///:memory:")

    # The application catches SQLAlchemy's wrapper; the seam sees,
    # and the event records, the driver's own exception beneath it.

    with engine.connect() as connection:
        with pytest.raises(OperationalError):
            connection.execute(text("SELECT nope FROM nowhere"))
    engine.dispose()

    (event,) = [ev for ev in at(tape, EXECUTE) if ev.data["operation"] == "SELECT"]
    assert isinstance(event.exception, sqlite3.OperationalError)


def test_an_async_engine_records_through_the_same_seam(tape: Tape) -> None:
    pytest.importorskip("aiosqlite")
    pytest.importorskip("greenlet")

    from sqlalchemy.ext.asyncio import create_async_engine

    async def work() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        await engine.dispose()

    asyncio.run(work())

    # The async engine runs the same synchronous dialect underneath,
    # so the one seam records both.

    selects = [ev for ev in at(tape, EXECUTE) if ev.data["operation"] == "SELECT"]
    assert len(selects) == 1
    assert selects[0].data["system"] == "sqlite"
    assert len(at(tape, CONNECT)) == 1
