"""The class as wrapture reads it: its data, its settings, and the
installed httpx satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# httpx is imported for its side: the class's trigger fires on its
# import, so the applying test below works with this file run on its
# own.
import httpx  # noqa: F401
import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.external.httpx import HTTPXInstrumentation


def test_class_data() -> None:
    assert HTTPXInstrumentation.target == "httpx"
    assert HTTPXInstrumentation.removable is True
    assert HTTPXInstrumentation.requires == ()
    assert HTTPXInstrumentation.supports == ">=0.27,<1"

    assert set(HTTPXInstrumentation.settings) == {"leaf", "propagate", "redact"}
    assert HTTPXInstrumentation.settings["leaf"].default is True
    assert HTTPXInstrumentation.settings["propagate"].default is True
    assert HTTPXInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (HTTPXInstrumentation.__doc__ or "").splitlines()[0] == (
        "Outbound request tracing and trace propagation for httpx."
    )


def test_constructing_without_settings_works() -> None:
    instance = HTTPXInstrumentation()

    assert instance.settings == {"leaf": True, "propagate": True, "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("httpx",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="ignore_hosts"):
        HTTPXInstrumentation(ignore_hosts=["localhost"])


def test_a_setting_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        HTTPXInstrumentation(leaf="no")


def test_the_installed_httpx_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(HTTPXInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("httpx")
            assert applied.applied == ("httpx",)
            assert applied.pending == ()
