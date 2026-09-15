"""The class as wrapture reads it: its data, its settings, and that
its standard library target's version is the interpreter's."""

from __future__ import annotations

import platform

# sqlite3 is imported for its side: the class's trigger fires on its
# import, so the applying test below works with this file run on its
# own.
import sqlite3  # noqa: F401
import warnings

import pytest
from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation


def test_class_data() -> None:
    assert SQLite3Instrumentation.target == "sqlite3"
    assert SQLite3Instrumentation.removable is True
    assert SQLite3Instrumentation.requires == ()
    assert SQLite3Instrumentation.supports == ">=3.12"

    settings = SQLite3Instrumentation.settings
    assert list(settings) == ["statements", "connections"]

    statements = settings["statements"]
    assert isinstance(statements, Aspect)
    assert statements.primary is True
    assert statements.defaults == {"leaf": True}
    assert set(statements.settings) == {"statement"}
    assert statements.settings["statement"].default is False

    connections = settings["connections"]
    assert isinstance(connections, Aspect)
    assert connections.primary is False
    assert connections.defaults == {"leaf": True}
    assert set(connections.settings) == set()


def test_the_description_is_the_docstring_first_line() -> None:
    assert (SQLite3Instrumentation.__doc__ or "").splitlines()[0] == (
        "Query and transaction tracing for sqlite3."
    )


def test_constructing_without_settings_works() -> None:
    instance = SQLite3Instrumentation()

    statements = instance.settings["statements"]
    assert statements.enabled is True
    assert statements.options == {"leaf": True}
    assert statements.settings == {"statement": False}

    connections = instance.settings["connections"]
    assert connections.enabled is True
    assert connections.options == {"leaf": True}
    assert connections.settings == {}
    assert instance.applied == ()
    assert instance.pending == ("sqlite3",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        SQLite3Instrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'statements': capture_result"):
        SQLite3Instrumentation(statements={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'statements': unknown keys"):
        SQLite3Instrumentation(statements={"verbosity": 2})


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(SQLite3Instrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("sqlite3",)
            assert applied.pending == ()
