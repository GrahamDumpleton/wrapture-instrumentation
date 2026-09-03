"""The class as wrapture reads it: its data, its settings, and the
installed aiohttp satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# aiohttp.web is imported for its side: the class's triggers fire on
# its modules' import, so the applying test below works with this
# file run on its own.
import aiohttp.web  # noqa: F401
import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation


def test_class_data() -> None:
    assert AiohttpWebInstrumentation.target == "aiohttp.web"
    assert AiohttpWebInstrumentation.removable is True
    assert AiohttpWebInstrumentation.requires == ()
    assert AiohttpWebInstrumentation.supports == ">=3.10,<4"

    assert set(AiohttpWebInstrumentation.settings) == {
        "ignore_paths",
        "join",
        "redact",
    }
    assert AiohttpWebInstrumentation.settings["ignore_paths"].default == []
    assert AiohttpWebInstrumentation.settings["join"].default is True
    assert AiohttpWebInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (AiohttpWebInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and route tracing for aiohttp.web server applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = AiohttpWebInstrumentation()

    assert instance.settings == {"ignore_paths": [], "join": True, "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("aiohttp.web",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        AiohttpWebInstrumentation(leaf=False)


def test_the_installed_aiohttp_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(AiohttpWebInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("aiohttp")
            assert applied.applied == ("aiohttp.web",)
            assert applied.pending == ()
