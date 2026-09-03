"""Fixtures for the uvicorn suite: a real socket server for one
application, the instrumentation applied, and a process-wide tape.

The tape is added as an installed sink rather than opened as a scoped
timeline: the server handles requests on its own thread's event
loop, and only an installed sink hears every thread.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from wrapture import Event, Tape, add_sink, instrumentation, remove_sink

from wrapture_instrumentation.server.uvicorn import UvicornInstrumentation


async def hello_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """The smallest useful application: 200 and a body, any path."""

    if scope["type"] != "http":
        return

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"hello"})


def serve(app: Any) -> Iterator[str]:
    """Run the application under uvicorn on a loopback port for the
    duration of the iteration, yielding the server's URL.

    The server runs on its own thread with its own event loop; the
    lifespan protocol is off so a bare application needs no lifespan
    handling, and startup is awaited by polling the server's own
    started flag.
    """

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="critical",
        lifespan="off",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 5.0
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the uvicorn server did not start in time")
        time.sleep(0.001)

    (listener,) = server.servers
    (sock,) = listener.sockets
    port = sock.getsockname()[1]

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def instrumented() -> Iterator[None]:
    with instrumentation(UvicornInstrumentation):
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
    the server sends before the middleware closes its event, so the
    request can still be closing on the server's loop when the test
    resumes.
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
