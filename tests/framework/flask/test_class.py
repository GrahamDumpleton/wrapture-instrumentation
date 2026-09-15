"""The class as wrapture reads it: its data, its aspects and
settings, and the installed Flask satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# Imported for its side: the class's triggers fire on flask's import,
# so the applying test below works with this file run on its own.
import flask  # noqa: F401
import pytest
from wrapture import Aspect, ConfigError, ConfigWarning, Setting, instrumentation

from wrapture_instrumentation.framework.flask import FlaskInstrumentation


def test_class_data() -> None:
    assert FlaskInstrumentation.target == "flask"
    assert FlaskInstrumentation.removable is True
    assert FlaskInstrumentation.supports == ">=3.0,<4"
    assert FlaskInstrumentation.requires == ()

    settings = FlaskInstrumentation.settings
    assert list(settings) == [
        "requests",
        "views",
        "lifecycle",
        "handlers",
        "templates",
        "handled_errors",
    ]

    requests = settings["requests"]
    assert isinstance(requests, Aspect)
    assert requests.primary is True
    assert requests.defaults == {}
    assert set(requests.settings) == {"ignore_paths"}
    assert requests.settings["ignore_paths"].default == []

    views = settings["views"]
    assert isinstance(views, Aspect)
    assert views.primary is False
    assert views.defaults == {"capture_result": "shape"}
    assert set(views.settings) == set()

    lifecycle = settings["lifecycle"]
    assert isinstance(lifecycle, Aspect)
    assert lifecycle.primary is False
    assert lifecycle.defaults == {}
    assert set(lifecycle.settings) == set()

    handlers = settings["handlers"]
    assert isinstance(handlers, Aspect)
    assert handlers.primary is False
    assert handlers.defaults == {"capture_result": "shape"}
    assert set(handlers.settings) == set()

    templates = settings["templates"]
    assert isinstance(templates, Aspect)
    assert templates.primary is False
    assert templates.defaults == {}
    assert set(templates.settings) == set()

    assert isinstance(settings["handled_errors"], Setting)
    assert settings["handled_errors"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    # A local construction has no distribution summary to fall back
    # on; the docstring is what the listing shows for one, and it
    # should read as the one-line description it is.

    assert (FlaskInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and view tracing for Flask applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = FlaskInstrumentation()

    requests = instance.settings["requests"]
    assert requests.enabled is True
    assert requests.options == {}
    assert requests.settings == {"ignore_paths": []}

    views = instance.settings["views"]
    assert views.enabled is True
    assert views.options == {"capture_result": "shape"}
    assert views.settings == {}

    lifecycle = instance.settings["lifecycle"]
    assert lifecycle.enabled is True
    assert lifecycle.options == {}
    assert lifecycle.settings == {}

    handlers = instance.settings["handlers"]
    assert handlers.enabled is True
    assert handlers.options == {"capture_result": "shape"}
    assert handlers.settings == {}

    templates = instance.settings["templates"]
    assert templates.enabled is True
    assert templates.options == {}
    assert templates.settings == {}

    assert instance.settings["handled_errors"] is True
    assert instance.applied == ()

    # The trigger set the decorators declared, all still to fire on a
    # fresh instance.

    assert instance.pending == (
        "flask.app",
        "flask.sansio.scaffold",
        "flask.sansio.blueprints",
        "flask",
    )


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        FlaskInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': capture_result"):
        FlaskInstrumentation(requests={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': unknown keys"):
        FlaskInstrumentation(requests={"verbosity": 2})


def test_a_key_the_boundary_cannot_honour_is_refused_when_applied() -> None:
    # The request boundary is wrapture's WSGI middleware, which takes
    # no stack; the refusal comes from configure(), so it surfaces as
    # the instrumentation applies rather than being silently ignored.

    with pytest.raises(ConfigError, match="aspect 'requests' cannot apply"):
        with instrumentation(FlaskInstrumentation, requests={"stack": "caller"}):
            pass


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
                "flask",
            )
            assert applied.pending == ()
