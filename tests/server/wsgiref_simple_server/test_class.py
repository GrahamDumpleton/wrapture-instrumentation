"""The class as wrapture reads it: its data, its settings, and that
its standard library target's version is the interpreter's."""

from __future__ import annotations

import platform
import warnings

# wsgiref.simple_server is imported for its side: the class's trigger
# fires on its import, so the applying test below works with this
# file run on its own.
import wsgiref.simple_server  # noqa: F401

import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.server.wsgiref_simple_server import (
    WSGIRefSimpleServerInstrumentation,
)


def test_class_data() -> None:
    assert WSGIRefSimpleServerInstrumentation.target == "wsgiref.simple_server"
    assert WSGIRefSimpleServerInstrumentation.removable is True
    assert WSGIRefSimpleServerInstrumentation.requires == ()
    assert WSGIRefSimpleServerInstrumentation.supports == ">=3.12"

    assert set(WSGIRefSimpleServerInstrumentation.settings) == {
        "ignore_paths",
        "redact",
    }
    assert WSGIRefSimpleServerInstrumentation.settings["ignore_paths"].default == []
    assert WSGIRefSimpleServerInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (WSGIRefSimpleServerInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request tracing for applications served by wsgiref.simple_server."
    )


def test_constructing_without_settings_works() -> None:
    instance = WSGIRefSimpleServerInstrumentation()

    assert instance.settings == {"ignore_paths": [], "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("wsgiref.simple_server",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        WSGIRefSimpleServerInstrumentation(leaf=False)


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(WSGIRefSimpleServerInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("wsgiref.simple_server",)
            assert applied.pending == ()
