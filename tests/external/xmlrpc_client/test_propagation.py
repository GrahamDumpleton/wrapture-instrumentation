"""Trace propagation: the identity of the tree a call is made in
travels in the request's headers, unless switched off or already
supplied by the application."""

from __future__ import annotations

import re
import xmlrpc.client

from wrapture import Tape, instrumentation, timeline

from tests.xmlrpcserver import Server
from wrapture_instrumentation.external.xmlrpc_client import XMLRPCClientInstrumentation

TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def trace_id_of(tape: Tape) -> str:
    """The w3c trace id of the one tree on the tape."""

    (event,) = tape.roots()
    assert event.trace is not None

    return event.trace.slots["w3c"].trace_id


def test_the_call_carries_the_trees_trace_identity(server: Server, tape: Tape) -> None:
    xmlrpc.client.ServerProxy(server.url).echo("hello")

    header = server.header(0, "traceparent")
    assert header is not None

    matched = TRACEPARENT.match(header)
    assert matched is not None
    assert matched.group(1) == trace_id_of(tape)


def test_an_applications_own_header_is_left_alone(server: Server, tape: Tape) -> None:
    own = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    proxy = xmlrpc.client.ServerProxy(server.url, headers=[("traceparent", own)])

    proxy.echo("hello")

    assert server.header(0, "traceparent") == own


def test_propagate_off_sends_no_trace_headers(server: Server) -> None:
    with (
        instrumentation(XMLRPCClientInstrumentation, propagate=False),
        timeline() as tape,
    ):
        xmlrpc.client.ServerProxy(server.url).echo("hello")

    assert server.header(0, "traceparent") is None
    assert server.header(0, "tracestate") is None

    # Recording is unaffected by the switch.

    (event,) = tape.all
    assert event.data["status"] == 200


def test_nothing_recording_means_nothing_to_propagate(server: Server) -> None:
    with instrumentation(XMLRPCClientInstrumentation):
        xmlrpc.client.ServerProxy(server.url).echo("hello")

    assert server.header(0, "traceparent") is None
