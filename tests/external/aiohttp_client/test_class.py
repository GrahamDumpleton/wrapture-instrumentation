"""The class as wrapture reads it: its data, its settings, and the
installed aiohttp satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# aiohttp is imported for its side: the class's trigger fires on the
# client module's import, so the applying test below works with this
# file run on its own.
import aiohttp.client  # noqa: F401
import pytest
from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.external.aiohttp_client import (
    AiohttpClientInstrumentation,
)


def test_class_data() -> None:
    assert AiohttpClientInstrumentation.target == "aiohttp.client"
    assert AiohttpClientInstrumentation.removable is True
    assert AiohttpClientInstrumentation.requires == ()
    assert AiohttpClientInstrumentation.supports == ">=3.10,<4"

    settings = AiohttpClientInstrumentation.settings
    assert list(settings) == ["requests"]

    requests = settings["requests"]
    assert isinstance(requests, Aspect)
    assert requests.primary is True
    assert requests.defaults == {"leaf": True}
    assert set(requests.settings) == {"propagate"}
    assert requests.settings["propagate"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    assert (AiohttpClientInstrumentation.__doc__ or "").splitlines()[0] == (
        "Outbound request tracing and trace propagation for aiohttp's client."
    )


def test_constructing_without_settings_works() -> None:
    instance = AiohttpClientInstrumentation()

    requests = instance.settings["requests"]
    assert requests.enabled is True
    assert requests.options == {"leaf": True}
    assert requests.settings == {"propagate": True}
    assert instance.applied == ()
    assert instance.pending == ("aiohttp.client",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        AiohttpClientInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': capture_result"):
        AiohttpClientInstrumentation(requests={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': unknown keys"):
        AiohttpClientInstrumentation(requests={"verbosity": 2})


def test_a_setting_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        AiohttpClientInstrumentation(leaf="no")


def test_the_installed_aiohttp_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(AiohttpClientInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("aiohttp")
            assert applied.applied == ("aiohttp.client",)
            assert applied.pending == ()
