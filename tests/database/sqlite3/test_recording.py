"""What the instrumentation records: the connect, the execute family
on cursors and connection shortcuts, the transaction boundaries and
the context manager, and what stays out of capture."""

from __future__ import annotations

import sqlite3

import pytest
from wrapture import Event, Tape, instrumentation, timeline

from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation


def labelled(tape: Tape, label: str) -> list[Event]:
    return [event for event in tape.all if event.label == label]


def test_connect_records_a_database_leaf(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    connection.close()

    (event,) = [event for event in tape.all if event.path == "sqlite3:connect"]
    assert event.category == "database"
    assert event.label is None
    assert event.data == {
        "system": "sqlite",
        "operation": "CONNECT",
        "database": ":memory:",
    }
    assert event.result == "<Connection>"
    assert tape.children_of(event) == []


def test_the_dbapi2_spelling_records_by_its_own_path(tape: Tape) -> None:
    connection = sqlite3.dbapi2.connect(":memory:")
    connection.close()

    (event,) = [event for event in tape.all if event.path == "sqlite3.dbapi2:connect"]
    assert event.data["operation"] == "CONNECT"


def test_a_cursor_execute_records_operation_but_no_statement(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    cursor = connection.cursor()

    cursor.execute("CREATE TABLE secrets (value TEXT)")
    cursor.execute("INSERT INTO secrets VALUES ('hunter2')")

    (create,) = [
        event
        for event in labelled(tape, "sqlite3:Cursor.execute")
        if event.data["operation"] == "CREATE"
    ]
    (insert,) = [
        event
        for event in labelled(tape, "sqlite3:Cursor.execute")
        if event.data["operation"] == "INSERT"
    ]

    for event in (create, insert):
        assert event.category == "database"
        assert event.data["system"] == "sqlite"
        assert "statement" not in event.data

    # The SQL reduces to its length in the captured arguments, so the
    # interpolated literal never reaches the record.

    assert insert.arguments is not None
    assert insert.arguments["sql"] == "<38 chars>"
    assert "hunter2" not in repr(insert.arguments)
    assert "hunter2" not in repr(insert.data)

    connection.close()


def test_the_statement_setting_records_the_text_as_written() -> None:
    with (
        instrumentation(SQLite3Instrumentation, statement=True),
        timeline() as tape,
    ):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE items (name TEXT)")
        connection.execute("INSERT INTO items VALUES (?)", ("widget",))
        connection.close()

    (insert,) = [event for event in tape.all if event.data.get("operation") == "INSERT"]
    assert insert.data["statement"] == "INSERT INTO items VALUES (?)"


def test_parameters_never_reach_the_record(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE items (name TEXT)")

    connection.execute("INSERT INTO items VALUES (?)", ("a-secret-value",))

    (insert,) = [event for event in tape.all if event.data.get("operation") == "INSERT"]
    assert insert.arguments is not None
    assert insert.arguments["parameters"] == "<1 values>"
    assert "a-secret-value" not in repr(insert.arguments)

    connection.close()


def test_connection_shortcuts_record_and_hand_back_working_cursors(
    tape: Tape,
) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE items (name TEXT)")
    connection.executemany("INSERT INTO items VALUES (?)", [("widget",), ("gadget",)])

    rows = connection.execute("SELECT name FROM items ORDER BY name").fetchall()
    assert rows == [("gadget",), ("widget",)]

    assert [
        event.data["operation"]
        for event in labelled(tape, "sqlite3:Connection.execute")
    ] == ["CREATE", "SELECT"]
    (many,) = labelled(tape, "sqlite3:Connection.executemany")
    assert many.data["operation"] == "INSERT"

    connection.close()


def test_cursor_chaining_keeps_recording(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    cursor = connection.cursor()

    # execute returns the cursor for chaining; the proxy hands back
    # itself so the chained call still records.

    assert cursor.execute("SELECT 1").execute("SELECT 2").fetchone() == (2,)

    assert [
        event.data["operation"] for event in labelled(tape, "sqlite3:Cursor.execute")
    ] == ["SELECT", "SELECT"]

    connection.close()


def test_iteration_passes_through_the_proxy(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE items (name TEXT)")
    connection.execute("INSERT INTO items VALUES ('widget')")

    cursor = connection.cursor()
    cursor.execute("SELECT name FROM items")

    assert [row for row in cursor] == [("widget",)]

    connection.close()


def test_executescript_records_its_leading_keyword(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")

    connection.executescript("CREATE TABLE a (x INT); CREATE TABLE b (y INT);")

    (script,) = labelled(tape, "sqlite3:Connection.executescript")
    assert script.data["operation"] == "CREATE"

    connection.close()


def test_commit_and_rollback_record_their_operations(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE items (name TEXT)")

    connection.execute("INSERT INTO items VALUES ('kept')")
    connection.commit()
    connection.execute("INSERT INTO items VALUES ('dropped')")
    connection.rollback()

    (commit,) = labelled(tape, "sqlite3:Connection.commit")
    assert commit.data == {"system": "sqlite", "operation": "COMMIT"}
    (rollback,) = labelled(tape, "sqlite3:Connection.rollback")
    assert rollback.data == {"system": "sqlite", "operation": "ROLLBACK"}

    rows = connection.execute("SELECT name FROM items").fetchall()
    assert rows == [("kept",)]

    connection.close()


def test_the_context_manager_records_its_commit(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE items (name TEXT)")

    with connection as inside:
        inside.execute("INSERT INTO items VALUES ('kept')")

    (exit_event,) = labelled(tape, "sqlite3:Connection.__exit__")
    assert exit_event.data == {"system": "sqlite", "operation": "COMMIT"}

    connection.close()


def test_the_context_manager_records_its_rollback(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE items (name TEXT)")

    with pytest.raises(RuntimeError):
        with connection as inside:
            inside.execute("INSERT INTO items VALUES ('dropped')")
            raise RuntimeError("abandon the transaction")

    (exit_event,) = labelled(tape, "sqlite3:Connection.__exit__")
    assert exit_event.data["operation"] == "ROLLBACK"

    # The exception's message is application data: the exit's captured
    # arguments carry types, never the value.

    assert exit_event.arguments is not None
    assert exit_event.arguments["exc_value"] == "<RuntimeError>"
    assert "abandon the transaction" not in repr(exit_event.arguments)

    rows = connection.execute("SELECT name FROM items").fetchall()
    assert rows == []

    connection.close()


def test_a_failing_query_records_its_exception(tape: Tape) -> None:
    connection = sqlite3.connect(":memory:")

    with pytest.raises(sqlite3.OperationalError):
        connection.execute("SELECT nope FROM nowhere")

    (event,) = labelled(tape, "sqlite3:Connection.execute")
    assert event.data["operation"] == "SELECT"
    assert isinstance(event.exception, sqlite3.OperationalError)

    connection.close()
