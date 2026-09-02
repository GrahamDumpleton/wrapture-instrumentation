"""The class as wrapture reads it: its data, its settings, and the
installed Jinja2 satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# Imported for its side: the class's trigger fires on jinja2's import,
# so the applying test below works with this file run on its own.
import jinja2  # noqa: F401
import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.template.jinja2 import Jinja2Instrumentation


def test_class_data() -> None:
    assert Jinja2Instrumentation.target == "jinja2"
    assert Jinja2Instrumentation.removable is True
    assert Jinja2Instrumentation.supports == ">=3.0,<4"
    assert Jinja2Instrumentation.requires == ()

    # One switch: the loading pipeline. The renders are the point
    # and have none.

    assert set(Jinja2Instrumentation.settings) == {"loading"}
    assert Jinja2Instrumentation.settings["loading"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    assert (Jinja2Instrumentation.__doc__ or "").splitlines()[0] == (
        "Template rendering tracing for Jinja2."
    )


def test_constructing_without_settings_works() -> None:
    instance = Jinja2Instrumentation()

    assert instance.settings == {"loading": True}
    assert instance.applied == ()
    assert instance.pending == ("jinja2.environment",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="ignore_names"):
        Jinja2Instrumentation(ignore_names=["base.html"])


def test_the_installed_jinja2_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(Jinja2Instrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("jinja2")
            assert applied.applied == ("jinja2.environment",)
            assert applied.pending == ()
