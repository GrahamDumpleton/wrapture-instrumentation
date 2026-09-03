"""The class as wrapture reads it: its data, its settings, and the
installed SQLAlchemy satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

# Imported for its side as much as its name: the class's engine
# triggers fire on sqlalchemy's import, so the applying test below
# works with this file run on its own; and the whole module skips
# where sqlalchemy cannot install (the free threaded 3.13 build).
sqlalchemy = pytest.importorskip("sqlalchemy")

from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.database.sqlalchemy import SQLAlchemyInstrumentation

DIALECT_MODULES = (
    "sqlalchemy.dialects.mssql.pyodbc",
    "sqlalchemy.dialects.mysql.mysqldb",
    "sqlalchemy.dialects.oracle.cx_oracle",
    "sqlalchemy.dialects.postgresql.psycopg2",
)


def test_class_data() -> None:
    assert SQLAlchemyInstrumentation.target == "sqlalchemy"
    assert SQLAlchemyInstrumentation.removable is True
    assert SQLAlchemyInstrumentation.requires == ()
    assert SQLAlchemyInstrumentation.supports == ">=1.4,<3"

    assert set(SQLAlchemyInstrumentation.settings) == {"leaf", "statement"}
    assert SQLAlchemyInstrumentation.settings["leaf"].default is True
    assert SQLAlchemyInstrumentation.settings["statement"].default is False


def test_the_description_is_the_docstring_first_line() -> None:
    assert (SQLAlchemyInstrumentation.__doc__ or "").splitlines()[0] == (
        "Query and transaction tracing for SQLAlchemy engines."
    )


def test_constructing_without_settings_works() -> None:
    instance = SQLAlchemyInstrumentation()

    assert instance.settings == {"leaf": True, "statement": False}
    assert instance.applied == ()
    assert instance.pending == (
        "sqlalchemy.engine.default",
        "sqlalchemy.engine.base",
        *DIALECT_MODULES,
    )


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="propagate"):
        SQLAlchemyInstrumentation(propagate=True)


def test_the_installed_sqlalchemy_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(SQLAlchemyInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("sqlalchemy")

            # The engine hooks fire on sqlalchemy's import; the driver
            # dialect hooks fire only if their modules ever load, so
            # whatever stays pending must be one of those.

            assert {"sqlalchemy.engine.default", "sqlalchemy.engine.base"} <= set(
                applied.applied
            )
            assert set(applied.pending) <= set(DIALECT_MODULES)
