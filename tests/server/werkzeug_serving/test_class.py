"""The class as wrapture reads it: its data, its settings, and that
its target's version is the werkzeug distribution's."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

# werkzeug.serving is imported for its side: the class's trigger
# fires on its import, so the applying test below works with this
# file run on its own.
import werkzeug.serving  # noqa: F401
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.server.werkzeug_serving import (
    WerkzeugServingInstrumentation,
)


def test_class_data() -> None:
    assert WerkzeugServingInstrumentation.target == "werkzeug.serving"
    assert WerkzeugServingInstrumentation.removable is True
    assert WerkzeugServingInstrumentation.requires == ()
    assert WerkzeugServingInstrumentation.supports == ">=3.0,<4"

    assert set(WerkzeugServingInstrumentation.settings) == {
        "ignore_paths",
        "redact",
    }
    assert WerkzeugServingInstrumentation.settings["ignore_paths"].default == []
    assert WerkzeugServingInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (WerkzeugServingInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request tracing for applications served by werkzeug's development server."
    )


def test_constructing_without_settings_works() -> None:
    instance = WerkzeugServingInstrumentation()

    assert instance.settings == {"ignore_paths": [], "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("werkzeug.serving",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        WerkzeugServingInstrumentation(leaf=False)


def test_the_installed_werkzeug_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(WerkzeugServingInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("werkzeug")
            assert applied.applied == ("werkzeug.serving",)
            assert applied.pending == ()
