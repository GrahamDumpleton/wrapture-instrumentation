"""The class as wrapture reads it: its data, its settings, and the
installed fastapi satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# fastapi is imported for its side: the class's triggers fire on its
# import, so the applying test below works with this file run on its
# own.
import fastapi.applications  # noqa: F401
import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.framework.fastapi import FastAPIInstrumentation


def test_class_data() -> None:
    assert FastAPIInstrumentation.target == "fastapi"
    assert FastAPIInstrumentation.removable is True
    assert FastAPIInstrumentation.requires == ()
    assert FastAPIInstrumentation.supports == ">=0.110,<1"

    assert set(FastAPIInstrumentation.settings) == {"ignore_paths", "redact"}
    assert FastAPIInstrumentation.settings["ignore_paths"].default == []
    assert FastAPIInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (FastAPIInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and route tracing for FastAPI applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = FastAPIInstrumentation()

    assert instance.settings == {"ignore_paths": [], "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("fastapi.applications", "fastapi.routing")


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        FastAPIInstrumentation(leaf=False)


def test_the_installed_fastapi_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(FastAPIInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("fastapi")
            assert applied.applied == ("fastapi.applications", "fastapi.routing")
            assert applied.pending == ()
