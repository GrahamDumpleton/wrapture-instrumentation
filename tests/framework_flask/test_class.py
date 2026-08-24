"""The class as wrapture reads it: its data, its (absence of)
settings, and the installed Flask satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.framework_flask import FlaskInstrumentation


def test_class_data() -> None:
    assert FlaskInstrumentation.target == "flask"
    assert FlaskInstrumentation.removable is True
    assert FlaskInstrumentation.supports == ">=3.0,<4"
    assert FlaskInstrumentation.requires == ()
    assert FlaskInstrumentation.settings == {}


def test_the_description_is_the_docstring_first_line() -> None:
    # A local construction has no distribution summary to fall back
    # on; the docstring is what the listing shows for one, and it
    # should read as the one-line description it is.

    assert (FlaskInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and view tracing for Flask applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = FlaskInstrumentation()

    assert instance.settings == {}
    assert instance.applied == ()

    # The trigger set the decorators declared, all still to fire on a
    # fresh instance.

    assert instance.pending == ("flask.app",)


def test_any_setting_is_refused_because_none_are_declared() -> None:
    # The first cut declares no settings, so an [[instrument]] entry
    # carrying any extra key fails at config load rather than being
    # silently ignored.

    with pytest.raises(ConfigError, match="ignore_paths"):
        FlaskInstrumentation(ignore_paths=["/health"])


def test_the_installed_flask_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(FlaskInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("flask")
            assert applied.applied == ("flask.app",)
            assert applied.pending == ()
