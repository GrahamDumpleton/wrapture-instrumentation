"""The class as wrapture reads it: its data, its settings, and the
installed uvicorn satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

# uvicorn is imported for its side: the class's trigger fires on its
# import, so the applying test below works with this file run on its
# own.
import uvicorn  # noqa: F401
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.server.uvicorn import UvicornInstrumentation


def test_class_data() -> None:
    assert UvicornInstrumentation.target == "uvicorn"
    assert UvicornInstrumentation.removable is True
    assert UvicornInstrumentation.requires == ()
    assert UvicornInstrumentation.supports == ">=0.30,<1"

    assert set(UvicornInstrumentation.settings) == {"ignore_paths", "redact"}
    assert UvicornInstrumentation.settings["ignore_paths"].default == []
    assert UvicornInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (UvicornInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request tracing for applications served by uvicorn."
    )


def test_constructing_without_settings_works() -> None:
    instance = UvicornInstrumentation()

    assert instance.settings == {"ignore_paths": [], "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("uvicorn.config",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        UvicornInstrumentation(leaf=False)


def test_the_installed_uvicorn_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(UvicornInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("uvicorn")
            assert applied.applied == ("uvicorn.config",)
            assert applied.pending == ()
