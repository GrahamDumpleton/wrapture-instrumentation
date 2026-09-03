"""Applying and removing: the patched name, that removal leaves
uvicorn as it was whatever the settings, and where the interposition
lands in the loaded chain."""

from __future__ import annotations

from typing import Any

import pytest
import uvicorn
import uvicorn.config
import wrapture
from wrapture import instrumentation

from tests.server.uvicorn.conftest import hello_app
from wrapture_instrumentation.server.uvicorn import UvicornInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {"load": uvicorn.config.Config.load}


@pytest.mark.parametrize("ignore_paths", [[], ["/health"]])
def test_apply_then_remove_leaves_the_module_as_it_was(
    ignore_paths: list[str],
) -> None:
    # The settings shape the middleware, not the patch, so the
    # patched set is the same either way.

    before = choke_points()

    with instrumentation(UvicornInstrumentation, ignore_paths=ignore_paths) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("uvicorn.config",)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied


def test_the_middleware_lands_inside_uvicorns_own(instrumented: None) -> None:
    # uvicorn wraps the application in its proxy-headers middleware by
    # default; the recording middleware lands beneath it, around the
    # application itself, so the event is named by the application and
    # the recorded scope is the one the application sees.

    config = uvicorn.Config(hello_app, port=0, log_level="critical")
    config.load()

    outer: Any = config.loaded_app
    assert type(outer).__name__ == "ProxyHeadersMiddleware"
    assert isinstance(outer.app, wrapture.ASGIMiddleware)
    assert outer.app.__wrapped__ is hello_app


def test_without_proxy_headers_the_application_is_wrapped_directly(
    instrumented: None,
) -> None:
    config = uvicorn.Config(
        hello_app, port=0, log_level="critical", proxy_headers=False
    )
    config.load()

    assert isinstance(config.loaded_app, wrapture.ASGIMiddleware)
    assert config.loaded_app.__wrapped__ is hello_app


def test_a_config_loaded_after_removal_is_untouched() -> None:
    with instrumentation(UvicornInstrumentation):
        pass

    config = uvicorn.Config(hello_app, port=0, log_level="critical")
    config.load()

    outer: Any = config.loaded_app
    assert not isinstance(outer, wrapture.ASGIMiddleware)
    assert not isinstance(getattr(outer, "app", None), wrapture.ASGIMiddleware)
