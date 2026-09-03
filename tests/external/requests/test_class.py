"""The class as wrapture reads it: its data, its settings, and the
installed requests satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

# requests is imported for its side: the class's trigger fires on its
# import, so the applying test below works with this file run on its
# own.
import requests  # noqa: F401
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.external.requests import RequestsInstrumentation


def test_class_data() -> None:
    assert RequestsInstrumentation.target == "requests"
    assert RequestsInstrumentation.removable is True
    assert RequestsInstrumentation.requires == ()
    assert RequestsInstrumentation.supports == ">=2.31,<3"

    assert set(RequestsInstrumentation.settings) == {"leaf", "propagate", "redact"}
    assert RequestsInstrumentation.settings["leaf"].default is True
    assert RequestsInstrumentation.settings["propagate"].default is True
    assert RequestsInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (RequestsInstrumentation.__doc__ or "").splitlines()[0] == (
        "Outbound request tracing and trace propagation for requests."
    )


def test_constructing_without_settings_works() -> None:
    instance = RequestsInstrumentation()

    assert instance.settings == {"leaf": True, "propagate": True, "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("requests.sessions",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="ignore_hosts"):
        RequestsInstrumentation(ignore_hosts=["localhost"])


def test_a_setting_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        RequestsInstrumentation(leaf="no")


def test_the_installed_requests_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(RequestsInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("requests")
            assert applied.applied == ("requests.sessions",)
            assert applied.pending == ()
