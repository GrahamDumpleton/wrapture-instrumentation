"""Fixtures for the wsgiref.simple_server suite: a real socket
server for one application, the instrumentation applied, and a
process-wide tape.

The tape is added as an installed sink rather than opened as a scoped
timeline: the server handles requests in its own thread, and only an
installed sink hears every thread.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Iterator
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
from wrapture import Event, Tape, add_sink, instrumentation, remove_sink

from wrapture_instrumentation.server.wsgiref_simple_server import (
    WSGIRefSimpleServerInstrumentation,
)


def hello_app(environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
    """The smallest useful application: 200 and a body, any path."""

    start_response("200 OK", [("Content-Type", "text/plain")])

    return [b"hello"]


def serve(app: Any) -> Iterator[str]:
    """Run the application on a loopback port for the duration of the
    iteration, yielding the server's URL."""

    class Handler(WSGIRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = make_server("127.0.0.1", 0, app, handler_class=Handler)
    url = f"http://127.0.0.1:{server.server_port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def instrumented() -> Iterator[None]:
    with instrumentation(WSGIRefSimpleServerInstrumentation):
        yield


@pytest.fixture
def tape() -> Iterator[Tape]:
    recorded = Tape()
    add_sink(recorded)

    try:
        yield recorded
    finally:
        remove_sink(recorded)


def settled(tape: Tape, requests: int = 1) -> list[Event]:
    """The tape's events once the expected number of request events
    have closed.

    The client's call returns when it has read the response, which
    the handler sends before the middleware closes its event, so the
    request can still be closing in the server's thread when the
    test resumes.
    """

    deadline = time.monotonic() + 2.0

    while time.monotonic() < deadline:
        recorded = [event for event in tape.all if event.kind == "request"]

        if len(recorded) >= requests and all(
            event.duration is not None for event in recorded
        ):
            return tape.all

        time.sleep(0.001)

    raise AssertionError("the server-side events did not settle in time")
