"""The class as wrapture reads it: its data, its settings, and the
installed starlette satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

# starlette is imported for its side: the class's triggers fire on
# its import, so the applying test below works with this file run on
# its own.
import starlette.applications  # noqa: F401
from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.framework.starlette import StarletteInstrumentation


def test_class_data() -> None:
    assert StarletteInstrumentation.target == "starlette"
    assert StarletteInstrumentation.removable is True
    assert StarletteInstrumentation.requires == ()
    assert StarletteInstrumentation.supports == ">=0.47,<2"

    settings = StarletteInstrumentation.settings
    assert list(settings) == ["requests", "views"]

    requests = settings["requests"]
    assert isinstance(requests, Aspect)
    assert requests.primary is True
    assert requests.defaults == {}
    assert set(requests.settings) == {"ignore_paths"}
    assert requests.settings["ignore_paths"].default == []

    views = settings["views"]
    assert isinstance(views, Aspect)
    assert views.primary is False
    assert views.defaults == {"capture_args": "types", "capture_result": "shape"}
    assert set(views.settings) == set()


def test_the_description_is_the_docstring_first_line() -> None:
    assert (StarletteInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and route tracing for Starlette applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = StarletteInstrumentation()

    requests = instance.settings["requests"]
    assert requests.enabled is True
    assert requests.options == {}
    assert requests.settings == {"ignore_paths": []}

    views = instance.settings["views"]
    assert views.enabled is True
    assert views.options == {"capture_args": "types", "capture_result": "shape"}
    assert views.settings == {}
    assert instance.applied == ()
    assert instance.pending == ("starlette.applications", "starlette.routing")


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        StarletteInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': capture_result"):
        StarletteInstrumentation(requests={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': unknown keys"):
        StarletteInstrumentation(requests={"verbosity": 2})


def test_the_installed_starlette_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(StarletteInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("starlette")
            assert applied.applied == ("starlette.applications", "starlette.routing")
            assert applied.pending == ()
