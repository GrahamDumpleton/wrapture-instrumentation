"""The boundary and distributed trace identity: joining what a
traceparent header carries, minting without one, and the join
setting."""

from __future__ import annotations

from wrapture import Event, Tape, instrumentation

from tests.server.aiohttp_web.conftest import drive
from tests.server.aiohttp_web.shop import make_app
from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-aaaaaaaaaaaaaaaa-01"


def boundary(events: list[Event]) -> Event:
    (event,) = [event for event in events if event.kind == "block"]

    return event


def test_a_traceparent_header_joins_the_callers_trace(
    instrumented: None, tape: Tape
) -> None:
    drive(make_app(), ("/", {"traceparent": TRACEPARENT}))

    event = boundary(tape.all)
    assert event.trace is not None

    slot = event.trace.slots["w3c"]
    assert slot.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert not slot.claimed


def test_a_request_without_headers_mints(instrumented: None, tape: Tape) -> None:
    drive(make_app(), "/")

    event = boundary(tape.all)
    assert event.trace is not None
    assert event.trace.slots["w3c"].headers == {}


def test_join_off_never_joins(tape: Tape) -> None:
    with instrumentation(AiohttpWebInstrumentation, join=False):
        drive(make_app(), ("/", {"traceparent": TRACEPARENT}))

    event = boundary(tape.all)
    assert event.trace is not None
    assert event.trace.slots["w3c"].trace_id != "0af7651916cd43dd8448eb211c80319c"
