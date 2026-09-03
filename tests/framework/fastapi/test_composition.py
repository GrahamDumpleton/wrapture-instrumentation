"""One boundary per request, however many layers record: the fastapi
and starlette targets applied together, and the whole stack under an
instrumented uvicorn."""

from __future__ import annotations

import urllib.request

from wrapture import Tape, add_sink, instrumentation, remove_sink, timeline

from tests.asgi import request
from tests.framework.fastapi.shop import make_app
from wrapture_instrumentation.framework.fastapi import FastAPIInstrumentation
from wrapture_instrumentation.framework.starlette import StarletteInstrumentation


def test_with_the_starlette_target_one_boundary_records() -> None:
    # FastAPI subclasses Starlette, so with both targets applied both
    # __call__s are decorated and the two middlewares stack, each
    # with its own per-instance cache. The outer one records and
    # marks the scope, the inner passes through, and the route
    # annotation lands on the one boundary.

    with (
        instrumentation(FastAPIInstrumentation),
        instrumentation(StarletteInstrumentation),
        timeline() as tape,
    ):
        response = request(make_app(), "GET", "/quote/widget")

    assert response.code == 200

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert seen.data["route"] == "/quote/{item}"
    assert seen.data["endpoint"] == "quoted"

    # The endpoint records once, beneath the one boundary.

    (endpoint,) = [event for event in tape.all if event.kind == "call"]
    assert endpoint.label == "quoted"


def test_under_an_instrumented_server_one_boundary_records() -> None:
    from tests.server.uvicorn.conftest import serve, settled
    from wrapture_instrumentation.server.uvicorn import UvicornInstrumentation

    tape = Tape()
    add_sink(tape)

    try:
        with (
            instrumentation(UvicornInstrumentation),
            instrumentation(FastAPIInstrumentation),
        ):
            serving = serve(make_app())
            url = next(serving)
            try:
                with urllib.request.urlopen(f"{url}/quote/widget") as response:
                    assert b"widget" in response.read()
            finally:
                next(serving, None)

        events = settled(tape)
    finally:
        remove_sink(tape)

    (seen,) = [event for event in events if event.kind == "request"]
    assert seen.data["route"] == "/quote/{item}"
    assert seen.result == "200 OK"

    (endpoint,) = [event for event in events if event.kind == "call"]
    assert endpoint.label == "quoted"
