"""Drive sqlite3 with the instrumentation applied, in memory.

The instrumentation is resolved by its entry point name. One pass
with the default settings covers the shapes that matter: the
connect, cursor and shortcut queries, parameterized inserts, a
chained execute, an explicit commit and rollback, the
commit-or-rollback context manager on both its paths, and a failing
query recorded with its exception. A second pass switches
statement = true, showing the SQL text riding on each event where
the first pass reduced it to a length.

Each pass runs inside a block() naming the pass, so the workload's
events form one tree under that root rather than each query rooting
its own trace.

Two views of the run always print: the live stream and the trees
reconstructed with timings. With --otel the same events also export
as OpenTelemetry spans to a local OTLP endpoint
(http://localhost:4318 unless OTEL_EXPORTER_OTLP_ENDPOINT says
otherwise).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-sqlite3 --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-sqlite3-demo"))


def workload() -> None:
    """The database work both passes perform."""

    connection = sqlite3.connect(":memory:")

    connection.execute("CREATE TABLE items (name TEXT, price INTEGER)")
    connection.executemany(
        "INSERT INTO items VALUES (?, ?)", [("widget", 42), ("gadget", 17)]
    )
    connection.commit()

    cursor = connection.cursor()
    print(cursor.execute("SELECT name, price FROM items ORDER BY name").fetchall())

    # The commit-or-rollback context manager, both ways.

    with connection:
        connection.execute("INSERT INTO items VALUES ('kept', 1)")

    try:
        with connection:
            connection.execute("INSERT INTO items VALUES ('dropped', 0)")
            raise RuntimeError("abandon the transaction")
    except RuntimeError:
        pass

    print(connection.execute("SELECT count(*) FROM items").fetchone())

    try:
        connection.execute("SELECT nope FROM nowhere")
    except sqlite3.OperationalError as error:
        print(f"OperationalError: {error}")

    connection.close()


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, run the workload with
    each setting, print the live stream and the trees, and flush any
    exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.database_sqlite3",
        description="Drive sqlite3 with the instrumentation applied,"
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
    # the block is the root span and every query nests beneath it,
    # the shape the events take in a real application, rather than
    # each leaf query rooting a trace of its own.

    print("==== default: no SQL text recorded ====")
    with wrapture.instrumentation("sqlite3"), wrapture.timeline() as tape:
        with wrapture.block("sqlite3-demo-default"):
            workload()
    trees.append(("no SQL text recorded", tape.tree(times=True)))

    print("\n==== statement = true: the text as written ====")
    with (
        wrapture.instrumentation("sqlite3", statement=True),
        wrapture.timeline() as tape,
    ):
        with wrapture.block("sqlite3-demo-statement"):
            workload()
    trees.append(("statement = true", tape.tree(times=True)))

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
        print("spans flushed to", endpoint, "as service wrapture-sqlite3-demo")


if __name__ == "__main__":
    main()
