"""Drive SQLAlchemy with the instrumentation applied, in memory.

The instrumentation is resolved by its entry point name. One pass
with the default settings covers the shapes that matter: the pool
opening its connection, Core statements through text() and the
expression language, a multi-row insert, an ORM session's query and
commit, an explicit rollback, and a failing statement recorded with
the driver's exception. A second pass switches statement = true,
showing the compiled SQL riding on each event where the first pass
reduced it to a length. A third pass applies the sqlite3 driver
instrumentation alongside with leaf = false, the driver's own events
nesting beneath each dialect-level statement.

Each pass runs inside a block() naming the pass, so the workload's
events form one tree under that root rather than each statement
rooting its own trace.

Two views of the run always print: the live stream and the trees
reconstructed with timings. With --otel the same events also export
as OpenTelemetry spans to a local OTLP endpoint
(http://localhost:4318 unless OTEL_EXPORTER_OTLP_ENDPOINT says
otherwise).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys

import wrapture
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-sqlalchemy --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-sqlalchemy-demo"))


def workload() -> None:
    """The database work every pass performs."""

    metadata = MetaData()
    items = Table(
        "items",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String),
        Column("price", Integer),
    )

    engine = create_engine("sqlite:///:memory:")

    # Core: the schema, a multi-row insert and a query, all inside
    # one committed transaction.

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            insert(items),
            [{"name": "widget", "price": 42}, {"name": "gadget", "price": 17}],
        )
        rows = connection.execute(select(items).order_by(items.c.name)).fetchall()
        print([tuple(row) for row in rows])

    # An explicit transaction rolled back.

    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(insert(items), {"name": "dropped", "price": 0})
        transaction.rollback()

    # The ORM: a session's query and commit end on the same seams.

    with Session(engine) as session:
        count = session.execute(select(items.c.name)).all()
        print(f"{len(count)} items")
        session.commit()

    # A failing statement: the event carries the driver's exception,
    # the application catches SQLAlchemy's wrapper above it.

    with engine.connect() as connection:
        with contextlib.suppress(OperationalError):
            connection.execute(text("SELECT nope FROM nowhere"))

    engine.dispose()


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, run the workload with
    each setting, print the live stream and the trees, and flush any
    exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.database_sqlalchemy",
        description="Drive SQLAlchemy with the instrumentation applied,"
        " printing the live stream and the trees.",
    )
    parser.add_argument(
        "--otel",
        action="store_true",
        help="also export the events as OpenTelemetry spans over OTLP",
    )
    options = parser.parse_args(arguments)

    if options.otel:
        add_otel_sink()

    wrapture.add_sink(wrapture.Printer(stream=sys.stdout))

    trees: list[tuple[str, str]] = []

    # Each pass runs under a block so the whole workload is one tree:
    # the block is the root span and every statement nests beneath
    # it, the shape the events take in a real application.

    print("==== default: no SQL text recorded ====")
    with wrapture.instrumentation("sqlalchemy"), wrapture.timeline() as tape:
        with wrapture.block("sqlalchemy-demo-default"):
            workload()
    trees.append(("no SQL text recorded", tape.tree(times=True)))

    print("\n==== statement = true: the compiled text ====")
    with (
        wrapture.instrumentation("sqlalchemy", statement=True),
        wrapture.timeline() as tape,
    ):
        with wrapture.block("sqlalchemy-demo-statement"):
            workload()
    trees.append(("statement = true", tape.tree(times=True)))

    print("\n==== leaf = false with the sqlite3 driver instrumented ====")
    with (
        wrapture.instrumentation("sqlite3"),
        wrapture.instrumentation("sqlalchemy", leaf=False),
        wrapture.timeline() as tape,
    ):
        with wrapture.block("sqlalchemy-demo-composed"):
            workload()
    trees.append(("leaf = false over sqlite3", tape.tree(times=True)))

    for name, tree in trees:
        print(f"\n==== tree: {name} ====")
        print(tree)

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print("spans flushed to", endpoint, "as service wrapture-sqlalchemy-demo")


if __name__ == "__main__":
    main()
