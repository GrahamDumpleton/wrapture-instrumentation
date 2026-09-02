"""The boundary and distributed trace identity: joining what a
traceparent header carries, minting without one, the join setting,
and both sides of an instrumented call sharing one trace."""

from __future__ import annotations

import xmlrpc.client

from wrapture import Event, Tape, instrumentation

from tests.server.xmlrpc_server.conftest import settled
from tests.xmlrpcserver import Server
from wrapture_instrumentation.server.xmlrpc_server import XMLRPCServerInstrumentation

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-aaaaaaaaaaaaaaaa-01"


def boundary(tape: Tape) -> Event:
    (event,) = [event for event in settled(tape) if event.kind == "block"]

    return event


def test_a_traceparent_header_joins_the_callers_trace(
    server: Server, instrumented: None, tape: Tape
) -> None:
    proxy = xmlrpc.client.ServerProxy(
        server.url, headers=[("traceparent", TRACEPARENT)]
    )

    proxy.echo("hello")

    event = boundary(tape)
    assert event.trace is not None
    slot = event.trace.slots["w3c"]
    assert slot.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert not slot.claimed


def test_a_request_without_headers_mints(
    server: Server, instrumented: None, tape: Tape
) -> None:
    xmlrpc.client.ServerProxy(server.url).echo("hello")

    event = boundary(tape)
    assert event.trace is not None
    assert event.trace.slots["w3c"].headers == {}


def test_join_off_never_joins(server: Server, tape: Tape) -> None:
    with instrumentation(XMLRPCServerInstrumentation, join=False):
        proxy = xmlrpc.client.ServerProxy(
            server.url, headers=[("traceparent", TRACEPARENT)]
        )

        proxy.echo("hello")

        event = boundary(tape)
        assert event.trace is not None
        assert event.trace.slots["w3c"].trace_id != "0af7651916cd43dd8448eb211c80319c"


def test_both_sides_of_an_instrumented_call_share_one_trace(
    server: Server, instrumented: None, tape: Tape
) -> None:
    # The client's leaf propagates the identity in the traceparent
    # header, the server's boundary joins it: one trace id across the
    # two sides, carried by nothing but the header.

    with instrumentation("xmlrpc.client"):
        xmlrpc.client.ServerProxy(server.url).echo("hello")

    events = settled(tape)
    (call,) = [event for event in events if event.category == "external"]
    (block,) = [event for event in events if event.kind == "block"]

    assert call.trace is not None
    assert block.trace is not None
    assert block.trace.slots["w3c"].trace_id == call.trace.slots["w3c"].trace_id
