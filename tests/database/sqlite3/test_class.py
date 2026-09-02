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
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation


def test_class_data() -> None:
    assert SQLite3Instrumentation.target == "sqlite3"
    assert SQLite3Instrumentation.removable is True
    assert SQLite3Instrumentation.requires == ()
    assert SQLite3Instrumentation.supports == ">=3.12"

    assert set(SQLite3Instrumentation.settings) == {"statement"}
    assert SQLite3Instrumentation.settings["statement"].default is False


def test_the_description_is_the_docstring_first_line() -> None:
    assert (SQLite3Instrumentation.__doc__ or "").splitlines()[0] == (
        "Query and transaction tracing for sqlite3."
    )


def test_constructing_without_settings_works() -> None:
    instance = SQLite3Instrumentation()

    assert instance.settings == {"statement": False}
    assert instance.applied == ()
    assert instance.pending == ("sqlite3",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        SQLite3Instrumentation(leaf=False)


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(SQLite3Instrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("sqlite3",)
            assert applied.pending == ()
