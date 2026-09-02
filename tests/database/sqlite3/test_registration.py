"""The entry point: resolving the instrumentation by its name, and
what the listing tool says about it."""

from __future__ import annotations

import platform
import sqlite3

from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from wrapture_instrumentation import __version__
from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation


def test_the_name_resolves_to_the_class() -> None:
    with instrumentation("sqlite3") as record:
        (instance,) = record.instrumentations

        assert type(instance) is SQLite3Instrumentation
        assert instance.name == "sqlite3"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == "Query and transaction tracing for sqlite3."


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("sqlite3")]).apply()
    try:
        report = applied.report()
        assert "sqlite3" in report
        assert (
            "target sqlite3 (standard library,"
            f" python {platform.python_version()})" in report
        )
        assert "applied sqlite3" in report

        with timeline() as tape:
            connection = sqlite3.connect(":memory:")
            connection.execute("SELECT 1").fetchone()
            connection.close()

        assert [event.data.get("operation") for event in tape.all] == [
            "CONNECT",
            "SELECT",
        ]
    finally:
        applied.revert()

    with timeline() as tape:
        connection = sqlite3.connect(":memory:")
        connection.execute("SELECT 1").fetchone()
        connection.close()

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"sqlite3  ({DISTRIBUTION} {__version__})" in output
    assert "  Query and transaction tracing for sqlite3." in output
    assert (
        "  target: sqlite3 (standard library,"
        f" python {platform.python_version()}), supported (>=3.12)" in output
    )
    assert "  modules: sqlite3" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    statement = false " in output
    assert "record the SQL text as written on each query event" in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "sqlite3"\nenabled = false' in output
    assert "# statement = false" in output
