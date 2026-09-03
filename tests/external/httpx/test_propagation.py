"""Trace propagation: the identity of the tree a request is made in
travels in the request's headers, hop by hop, unless switched off or
already set by the application."""

from __future__ import annotations

import re

import httpx
import wrapture
from wrapture import Tape, instrumentation, timeline

from tests.httpserver import Server
from wrapture_instrumentation.external.httpx import HTTPXInstrumentation

TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def trace_id_of(tape: Tape) -> str:
    """The w3c trace id of the one tree on the tape."""

    (event,) = tape.roots()
    assert event.trace is not None

    return event.trace.slots["w3c"].trace_id


def test_the_request_carries_the_trees_trace_identity(
    server: Server, tape: Tape
) -> None:
    httpx.get(f"{server.url}/ok")

    header = server.header(0, "traceparent")
    assert header is not None

    matched = TRACEPARENT.match(header)
    assert matched is not None
    assert matched.group(1) == trace_id_of(tape)


def test_a_request_beneath_an_observed_root_joins_its_trace(
    server: Server, tape: Tape
) -> None:
    @wrapture.observed
    def place_order() -> None:
        httpx.get(f"{server.url}/ok")

    place_order()

    (root, call) = tape.all
    assert tape.parent_of(call) is root

    header = server.header(0, "traceparent")
    assert header is not None
    assert trace_id_of(tape) in header


def test_every_redirect_hop_carries_the_identity(server: Server, tape: Tape) -> None:
    httpx.get(f"{server.url}/redirect", follow_redirects=True)

    first = server.header(0, "traceparent")
    second = server.header(1, "traceparent")

    assert first is not None

    # A hop's request copies the headers of the one before it, so the
    # identity travels as the very same header rather than a fresh
    # one per hop.

    assert second == first
    assert first.split("-")[1] == trace_id_of(tape)


def test_an_applications_own_header_is_left_alone(server: Server, tape: Tape) -> None:
    own = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

    httpx.get(f"{server.url}/ok", headers={"traceparent": own})

    assert server.header(0, "traceparent") == own


def test_propagate_off_sends_no_trace_headers(server: Server) -> None:
    with instrumentation(HTTPXInstrumentation, propagate=False), timeline() as tape:
        httpx.get(f"{server.url}/ok")

    assert server.header(0, "traceparent") is None
    assert server.header(0, "tracestate") is None

    # Recording is unaffected by the switch.

    (event,) = tape.all
    assert event.data["status"] == 200


def test_nothing_recording_means_nothing_to_propagate(server: Server) -> None:
    # Applied but with no sink or tape hearing it: there is no tree,
    # so no identity, and the request goes out as the application
    # built it.

    with instrumentation(HTTPXInstrumentation):
        httpx.get(f"{server.url}/ok")

    assert server.header(0, "traceparent") is None
