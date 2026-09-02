"""Applying and removing: the patched name, that removal leaves
wsgiref.simple_server as it was whatever the settings, and that the
wrapper cache never outlives the server that made it."""

from __future__ import annotations

import gc
import urllib.request
import weakref
import wsgiref.simple_server
from collections.abc import Iterable
from typing import Any

import pytest
from wrapture import instrumentation

from tests.server.wsgiref_simple_server.conftest import serve
from wrapture_instrumentation.server.wsgiref_simple_server import (
    WSGIRefSimpleServerInstrumentation,
)


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {"get_app": wsgiref.simple_server.WSGIServer.get_app}


@pytest.mark.parametrize("ignore_paths", [[], ["/health"]])
def test_apply_then_remove_leaves_the_module_as_it_was(
    ignore_paths: list[str],
) -> None:
    # The settings shape the middleware, not the patch, so the
    # patched set is the same either way.

    before = choke_points()

    with instrumentation(
        WSGIRefSimpleServerInstrumentation, ignore_paths=ignore_paths
    ) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("wsgiref.simple_server",)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied


def test_the_wrapper_does_not_outlive_its_server() -> None:
    # The middleware is cached on the server instance, so once the
    # server and application are dropped, nothing of either survives,
    # the instrumentation still applied. No sink is active: the
    # interposition happens regardless, which is exactly what would
    # pin the application if the cache held it.

    def app(environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        start_response("200 OK", [("Content-Type", "text/plain")])

        return [b"here and gone"]

    grave = weakref.ref(app)

    with instrumentation(WSGIRefSimpleServerInstrumentation):
        serving = serve(app)
        url = next(serving)
        try:
            urllib.request.urlopen(url).close()
        finally:
            next(serving, None)

        del serving, app
        gc.collect()

        assert grave() is None
