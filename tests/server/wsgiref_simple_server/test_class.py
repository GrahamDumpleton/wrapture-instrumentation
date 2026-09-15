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
from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.server.wsgiref_simple_server import (
    WSGIRefSimpleServerInstrumentation,
)


def test_class_data() -> None:
    assert WSGIRefSimpleServerInstrumentation.target == "wsgiref.simple_server"
    assert WSGIRefSimpleServerInstrumentation.removable is True
    assert WSGIRefSimpleServerInstrumentation.requires == ()
    assert WSGIRefSimpleServerInstrumentation.supports == ">=3.12"

    settings = WSGIRefSimpleServerInstrumentation.settings
    assert list(settings) == ["requests"]

    requests = settings["requests"]
    assert isinstance(requests, Aspect)
    assert requests.primary is True
    assert requests.defaults == {}
    assert set(requests.settings) == {"ignore_paths"}
    assert requests.settings["ignore_paths"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (WSGIRefSimpleServerInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request tracing for applications served by wsgiref.simple_server."
    )


def test_constructing_without_settings_works() -> None:
    instance = WSGIRefSimpleServerInstrumentation()

    requests = instance.settings["requests"]
    assert requests.enabled is True
    assert requests.options == {}
    assert requests.settings == {"ignore_paths": []}
    assert instance.applied == ()
    assert instance.pending == ("wsgiref.simple_server",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        WSGIRefSimpleServerInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': capture_result"):
        WSGIRefSimpleServerInstrumentation(requests={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': unknown keys"):
        WSGIRefSimpleServerInstrumentation(requests={"verbosity": 2})


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(WSGIRefSimpleServerInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("wsgiref.simple_server",)
            assert applied.pending == ()
