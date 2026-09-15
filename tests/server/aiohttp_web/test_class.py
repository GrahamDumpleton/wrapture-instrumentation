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
from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation


def test_class_data() -> None:
    assert AiohttpWebInstrumentation.target == "aiohttp.web"
    assert AiohttpWebInstrumentation.removable is True
    assert AiohttpWebInstrumentation.requires == ()
    assert AiohttpWebInstrumentation.supports == ">=3.10,<4"

    settings = AiohttpWebInstrumentation.settings
    assert list(settings) == ["requests", "handlers"]

    requests = settings["requests"]
    assert isinstance(requests, Aspect)
    assert requests.primary is True
    assert requests.defaults == {}
    assert set(requests.settings) == {"join", "ignore_paths"}
    assert requests.settings["ignore_paths"].default == []
    assert requests.settings["join"].default is True

    handlers = settings["handlers"]
    assert isinstance(handlers, Aspect)
    assert handlers.primary is False
    assert handlers.defaults == {"capture_args": "types", "capture_result": "shape"}
    assert set(handlers.settings) == set()


def test_the_description_is_the_docstring_first_line() -> None:
    assert (AiohttpWebInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and route tracing for aiohttp.web server applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = AiohttpWebInstrumentation()

    requests = instance.settings["requests"]
    assert requests.enabled is True
    assert requests.options == {}
    assert requests.settings == {"ignore_paths": [], "join": True}

    handlers = instance.settings["handlers"]
    assert handlers.enabled is True
    assert handlers.options == {"capture_args": "types", "capture_result": "shape"}
    assert handlers.settings == {}
    assert instance.applied == ()
    assert instance.pending == ("aiohttp.web",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        AiohttpWebInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': capture_result"):
        AiohttpWebInstrumentation(requests={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': unknown keys"):
        AiohttpWebInstrumentation(requests={"verbosity": 2})


def test_a_result_key_under_the_boundary_is_refused_when_applied() -> None:
    # The boundary is a block that records the query through
    # capture_args but captures no result, so redact_result (which
    # composes into capture_result) can never act and is refused.

    with pytest.raises(ConfigError, match="aspect 'requests' cannot apply"):
        with instrumentation(AiohttpWebInstrumentation, redact_result=True):
            pass


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
