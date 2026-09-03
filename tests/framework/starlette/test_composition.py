"""One boundary per request, however many layers record: the
starlette application served by an instrumented uvicorn, both
instrumentations applied at once."""

from __future__ import annotations

import urllib.request

from wrapture import Tape, add_sink, instrumentation, remove_sink

from tests.framework.starlette.shop import make_app
from tests.server.uvicorn.conftest import serve, settled
from wrapture_instrumentation.framework.starlette import StarletteInstrumentation
from wrapture_instrumentation.server.uvicorn import UvicornInstrumentation


def test_under_an_instrumented_server_one_boundary_records() -> None:
    # The uvicorn target wraps what the server loads, the starlette
    # target wraps the application's own __call__, and a request
    # still records as one tree: the outer middleware records and
    # marks the scope, the inner one passes through, and the route
    # annotation lands on the one boundary.

    tape = Tape()
    add_sink(tape)

    try:
        with (
            instrumentation(UvicornInstrumentation),
            instrumentation(StarletteInstrumentation),
        ):
            serving = serve(make_app())
            url = next(serving)
            try:
                with urllib.request.urlopen(f"{url}/quote/widget") as response:
                    assert response.read() == b"widget: 42 coins"
            finally:
                next(serving, None)

        events = settled(tape)
    finally:
        remove_sink(tape)

    (seen,) = [event for event in events if event.kind == "request"]
    assert seen.data["route"] == "/quote/{item}"
    assert seen.data["endpoint"] == "quoted"
    assert seen.result == "200 OK"

    # The endpoint records beneath the one boundary.

    (endpoint,) = [event for event in events if event.kind == "call"]
    assert endpoint.label == "quoted"
