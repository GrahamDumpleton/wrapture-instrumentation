"""One boundary per request, however many layers record: an inner
recording middleware, an application that is already the middleware,
and an instrumented client joining the server's trace across the
socket."""

from __future__ import annotations

import urllib.request
from typing import Any

import wrapture
from wrapture import Tape, instrumentation

from tests.server.uvicorn.conftest import hello_app, serve, settled


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        body: bytes = response.read()

    return body


def test_an_inner_middleware_leaves_one_boundary(
    instrumented: None, tape: Tape
) -> None:
    # The application carries its own recording middleware inside,
    # invisible from the outside: the interposed outer middleware
    # records and marks the scope, the inner one sees the mark and
    # passes through.

    inner = wrapture.ASGIMiddleware(hello_app)

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        await inner(scope, receive, send)

    serving = serve(app)
    url = next(serving)
    try:
        assert fetch(url) == b"hello"
    finally:
        next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert event.path == f"{app.__module__}:{app.__qualname__}"


def test_an_application_that_is_the_middleware_passes_through(
    instrumented: None, tape: Tape
) -> None:
    # Already an ASGIMiddleware: the interposition leaves it alone and
    # it records as itself, named by the application it wraps.

    serving = serve(wrapture.ASGIMiddleware(hello_app))
    url = next(serving)
    try:
        assert fetch(url) == b"hello"
    finally:
        next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert event.path == f"{hello_app.__module__}:{hello_app.__qualname__}"


def test_an_instrumented_client_joins_the_servers_trace(tape: Tape) -> None:
    # Both sides in one process over a real socket: the client's
    # external leaf propagates the trace identity in its headers, and
    # the server's request boundary joins it, so the two events share
    # one trace id carried by nothing but the traceparent header.

    import requests

    from wrapture_instrumentation.external.requests import RequestsInstrumentation
    from wrapture_instrumentation.server.uvicorn import UvicornInstrumentation

    with (
        instrumentation(RequestsInstrumentation),
        instrumentation(UvicornInstrumentation),
    ):
        serving = serve(hello_app)
        url = next(serving)
        try:

            @wrapture.observed
            def place_order() -> None:
                requests.get(f"{url}/order")

            place_order()
        finally:
            next(serving, None)

    events = settled(tape)
    (request_event,) = [event for event in events if event.kind == "request"]
    (client_event,) = [event for event in events if event.category == "external"]

    assert request_event.trace is not None
    assert client_event.trace is not None
    assert (
        request_event.trace.slots["w3c"].trace_id
        == client_event.trace.slots["w3c"].trace_id
    )
