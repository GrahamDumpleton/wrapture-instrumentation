"""ORM queries and transaction ends as database events: the contract
keys, the statement setting, the queries switch, and leaf composition
over the sqlite3 driver instrumentation."""

from __future__ import annotations

from django.db import connection
from wrapture import Event, Tape, instrumentation, timeline

from tests.framework.django.shop import make_wsgi_app
from tests.framework.django.shop.models import Item
from tests.wsgi import request
from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation
from wrapture_instrumentation.framework.django import DjangoInstrumentation

CURSOR = "django.db.backends.utils:CursorWrapper"


def database_events(tape: Tape) -> list[Event]:
    """The events the database bindings recorded, in order."""

    return [event for event in tape.all if event.category == "database"]


def test_an_orm_query_records_a_database_event(database: None, tape: Tape) -> None:
    response = request(make_wsgi_app(), "GET", "/stocked/")

    assert response.status == "200 OK"
    assert response.body == b"0 items stocked"

    (seen, view, *queries) = tape.all
    assert seen.kind == "request"
    assert view.label == "stocked"

    (query,) = [event for event in queries if event.data.get("operation") == "SELECT"]
    assert query.path == f"{CURSOR}.execute"
    assert query.category == "database"
    assert query.data["system"] == "sqlite"
    assert query.data["database"] == ":memory:"
    assert "host" not in query.data
    assert "port" not in query.data

    # The statement setting is off: the SQL reduces to its length in
    # the captured arguments and no statement key is annotated.

    assert query.arguments is not None
    assert query.arguments["sql"].endswith(" chars>")
    assert "statement" not in query.data

    # Each query is a terminal node by default.

    assert tape.children_of(query) == []


def test_the_statement_setting_records_the_sql_without_parameters(
    database: None,
) -> None:
    with (
        instrumentation(DjangoInstrumentation, statement=True),
        timeline() as tape,
    ):
        response = request(make_wsgi_app(), "GET", "/restock/")

    assert response.status == "200 OK"

    (insert,) = [event for event in tape.all if event.data.get("operation") == "INSERT"]
    assert "shop_item" in insert.data["statement"]

    # The ORM parameterizes: the SQL text carries placeholders, and
    # the values themselves never reach the record.

    assert "widget" not in repr(insert.data)
    assert "widget" not in repr(insert.arguments)


def test_a_transaction_end_records_beside_its_statements(
    database: None, tape: Tape
) -> None:
    # restock runs inside atomic(): the INSERT and the COMMIT that
    # ends the block both record, each carrying the contract keys.

    response = request(make_wsgi_app(), "GET", "/restock/")

    assert response.status == "200 OK"

    operations = [event.data.get("operation") for event in database_events(tape)]
    assert "INSERT" in operations
    assert "COMMIT" in operations

    (commit,) = [event for event in tape.all if event.data.get("operation") == "COMMIT"]
    assert commit.path == ("django.db.backends.base.base:BaseDatabaseWrapper.commit")
    assert commit.data["system"] == "sqlite"


def test_queries_off_silences_the_database_events(database: None) -> None:
    with (
        instrumentation(DjangoInstrumentation, queries=False),
        timeline() as tape,
    ):
        response = request(make_wsgi_app(), "GET", "/restock/")

    assert response.status == "200 OK"
    assert database_events(tape) == []
    assert [event.kind for event in tape.all] == ["request", "call"]


def _driven_composed(leaf: bool) -> Tape:
    """Drive /stocked/ with the django and sqlite3 instrumentations
    composed. Django ignores close() on an in-memory sqlite
    connection, so connect() forces a fresh connection instead: made
    under both instrumentations it goes through the patched
    sqlite3.connect and comes back proxied (with a fresh, empty
    database), and the reconnect in the finally leaves a raw one, and
    an empty database, behind for later tests."""

    try:
        with (
            instrumentation(DjangoInstrumentation, leaf=leaf),
            instrumentation(SQLite3Instrumentation),
            timeline() as tape,
        ):
            connection.connect()

            with connection.schema_editor() as editor:
                editor.create_model(Item)

            request(make_wsgi_app(), "GET", "/stocked/")
    finally:
        connection.connect()

    return tape


def _django_selects(tape: Tape) -> list[Event]:
    return [
        event
        for event in tape.all
        if event.data.get("operation") == "SELECT"
        and event.path.startswith("django.db")
    ]


def test_leaf_folds_an_instrumented_driver_beneath_a_query() -> None:
    tape = _driven_composed(leaf=True)

    selects = _django_selects(tape)
    assert selects

    for query in selects:
        assert tape.children_of(query) == []


def test_leaf_off_nests_the_instrumented_driver_beneath_a_query() -> None:
    tape = _driven_composed(leaf=False)

    selects = _django_selects(tape)
    assert selects

    nested = [child for query in selects for child in tape.children_of(query)]
    assert nested

    for child in nested:
        assert (child.label or "").startswith("sqlite3:")
