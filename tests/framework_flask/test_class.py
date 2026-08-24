"""The class as wrapture reads it: its data, its (absence of)
settings, and the installed Flask satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# Imported for its side: the class's triggers fire on flask's import,
# so the applying test below works with this file run on its own.
import flask  # noqa: F401
import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.framework_flask import FlaskInstrumentation


def test_class_data() -> None:
    assert FlaskInstrumentation.target == "flask"
    assert FlaskInstrumentation.removable is True
    assert FlaskInstrumentation.supports == ">=3.0,<4"
    assert FlaskInstrumentation.requires == ()

    # The two category switches, both on by default; the core layers
    # (requests, routes, views, unhandled errors) have no switch.

    assert set(FlaskInstrumentation.settings) == {"lifecycle", "handled_errors"}
    assert FlaskInstrumentation.settings["lifecycle"].default is True
    assert FlaskInstrumentation.settings["handled_errors"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    # A local construction has no distribution summary to fall back
    # on; the docstring is what the listing shows for one, and it
    # should read as the one-line description it is.

    assert (FlaskInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and view tracing for Flask applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = FlaskInstrumentation()

    assert instance.settings == {"lifecycle": True, "handled_errors": True}
    assert instance.applied == ()

    # The trigger set the decorators declared, all still to fire on a
    # fresh instance.

    assert instance.pending == (
        "flask.app",
        "flask.sansio.scaffold",
        "flask.sansio.blueprints",
    )


def test_an_undeclared_setting_is_refused() -> None:
    # Only the declared switches are accepted: an [[instrument]] entry
    # carrying any other key fails at config load rather than being
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
            assert applied.applied == (
                "flask.app",
                "flask.sansio.scaffold",
                "flask.sansio.blueprints",
            )
            assert applied.pending == ()
