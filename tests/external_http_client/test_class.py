"""The class as wrapture reads it: its data, its settings, and that
its standard library target's version is the interpreter's."""

from __future__ import annotations

# http.client is imported for its side: the class's trigger fires on
# its import, so the applying test below works with this file run on
# its own.
import http.client  # noqa: F401
import platform
import warnings

import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.external_http_client import HTTPClientInstrumentation


def test_class_data() -> None:
    assert HTTPClientInstrumentation.target == "http.client"
    assert HTTPClientInstrumentation.removable is True
    assert HTTPClientInstrumentation.requires == ()
    assert HTTPClientInstrumentation.supports == ">=3.12"

    assert set(HTTPClientInstrumentation.settings) == {"redact"}
    assert HTTPClientInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (HTTPClientInstrumentation.__doc__ or "").splitlines()[0] == (
        "Wire-level tracing for http.client."
    )


def test_constructing_without_settings_works() -> None:
    instance = HTTPClientInstrumentation()

    assert instance.settings == {"redact": []}
    assert instance.applied == ()
    assert instance.pending == ("http.client",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        HTTPClientInstrumentation(leaf=False)


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(HTTPClientInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("http.client",)
            assert applied.pending == ()
