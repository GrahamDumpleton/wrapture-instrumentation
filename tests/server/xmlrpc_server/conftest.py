"""Fixtures for the xmlrpc.server suite: the local server, the
instrumentation applied, and a process-wide tape.

The tape is added as an installed sink rather than opened as a scoped
timeline: the server handles requests in its own thread, and only an
installed sink hears every thread.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from wrapture import Event, Tape, add_sink, instrumentation, remove_sink

from tests.xmlrpcserver import Server, serve
from wrapture_instrumentation.server.xmlrpc_server import XMLRPCServerInstrumentation


@pytest.fixture
def server() -> Iterator[Server]:
    yield from serve()


@pytest.fixture
def instrumented() -> Iterator[None]:
    with instrumentation(XMLRPCServerInstrumentation):
        yield


@pytest.fixture
def tape() -> Iterator[Tape]:
    recorded = Tape()
    add_sink(recorded)

    try:
        yield recorded
    finally:
        remove_sink(recorded)


def settled(tape: Tape, blocks: int = 1) -> list[Event]:
    """The tape's events once the expected number of request
    boundaries have closed.

    The client's call returns when it has read the response, which
    the handler sends before its do_POST returns, so the boundary can
    still be closing in the server's thread when the test resumes.
    """

    deadline = time.monotonic() + 2.0

    while time.monotonic() < deadline:
        boundaries = [event for event in tape.all if event.kind == "block"]

        if len(boundaries) >= blocks and all(
            event.duration is not None for event in boundaries
        ):
            return tape.all

        time.sleep(0.001)

    raise AssertionError("the server-side events did not settle in time")
