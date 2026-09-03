"""Fixtures for the grpc suite: the instrumentation applied, the
local service built while it is applied (so the injected server
interceptor is riding), and a process-wide tape.

The tape is added as an installed sink rather than opened as a scoped
timeline: the server handles RPCs on its executor threads, and only
an installed sink hears every thread. grpc itself is imported only
inside the test modules and fixtures, each module skipping itself
where grpcio is not installed (it ships no free threaded or 3.15
wheels yet, so those builds go without).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from wrapture import Event, Tape, add_sink, instrumentation, remove_sink

from wrapture_instrumentation.rpc.grpc import GRPCInstrumentation


@pytest.fixture
def instrumented() -> Iterator[None]:
    with instrumentation(GRPCInstrumentation):
        yield


@pytest.fixture
def service(instrumented: None) -> Iterator[object]:
    from tests.rpc.grpc.service import serve

    yield from serve()


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

    The client's call returns when the response is in, but the
    server's boundary closes in its executor thread and can still be
    closing when the test resumes.
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
