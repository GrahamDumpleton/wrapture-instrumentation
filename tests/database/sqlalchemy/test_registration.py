"""The entry point: resolving the instrumentation by its name, and
what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text
from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from wrapture_instrumentation import __version__
from wrapture_instrumentation.database.sqlalchemy import SQLAlchemyInstrumentation

EXECUTE = "sqlalchemy.engine.default:DefaultDialect.do_execute"


def test_the_name_resolves_to_the_class() -> None:
    with instrumentation("sqlalchemy") as record:
        (instance,) = record.instrumentations

        assert type(instance) is SQLAlchemyInstrumentation
        assert instance.name == "sqlalchemy"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Query and transaction tracing for SQLAlchemy engines."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("sqlalchemy")]).apply()
    try:
        report = applied.report()
        assert "sqlalchemy" in report
        assert f"target sqlalchemy {metadata.version('sqlalchemy')}" in report
        assert "applied sqlalchemy.engine.default, sqlalchemy.engine.base" in report

        with timeline() as tape:
            engine = create_engine("sqlite:///:memory:")
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            engine.dispose()

        selects = [ev for ev in tape.all if ev.path == EXECUTE]
        assert [ev.data["operation"] for ev in selects] == ["SELECT"]
    finally:
        applied.revert()

    with timeline() as tape:
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"sqlalchemy  ({DISTRIBUTION} {__version__})" in output
    assert "  Query and transaction tracing for SQLAlchemy engines." in output
    assert (
        f"  target: sqlalchemy {metadata.version('sqlalchemy')},"
        " supported (>=1.4,<3)" in output
    )

    # The modules line carries all six triggers; the engine pair lead
    # and the driver dialect modules follow.

    assert "  modules: sqlalchemy.engine.default, sqlalchemy.engine.base," in output
    assert "sqlalchemy.dialects.postgresql.psycopg2" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    leaf = true " in output
    assert (
        "record each statement as a terminal node, so anything recorded"
        " beneath it" in output
    )
    assert "    statement = false " in output
    assert "record the SQL text as compiled on each statement event" in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "sqlalchemy"\nenabled = false' in output
    assert "# leaf = true" in output
    assert "# statement = false" in output
