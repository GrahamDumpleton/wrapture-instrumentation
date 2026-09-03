"""Trace propagation in the request headers: the identity added to
each request, a header the application set left alone, and the
setting to turn it off."""

from __future__ import annotations

import urllib3
from wrapture import Tape, instrumentation, timeline

from tests.httpserver import Server
from wrapture_instrumentation.external.urllib3 import Urllib3Instrumentation

CLAIMED = "00-11111111111111111111111111111111-2222222222222222-01"


def test_the_trace_identity_rides_in_the_headers(server: Server, tape: Tape) -> None:
    with urllib3.PoolManager() as manager:
        manager.request("GET", f"{server.url}/ok")

    carried = server.header(0, "traceparent")
    assert carried is not None
    assert carried.startswith("00-")


def test_a_bare_pool_request_propagates_too(server: Server, tape: Tape) -> None:
    authority = server.url.rpartition("/")[2]
    host, _, port = authority.rpartition(":")

    with urllib3.HTTPConnectionPool(host, int(port)) as pool:
        pool.urlopen("GET", "/ok")

    assert server.header(0, "traceparent") is not None


def test_a_header_the_application_set_is_left_alone(server: Server, tape: Tape) -> None:
    with urllib3.PoolManager() as manager:
        manager.request("GET", f"{server.url}/ok", headers={"traceparent": CLAIMED})

    assert server.header(0, "traceparent") == CLAIMED


def test_a_redirect_carries_the_identity_on_every_hop(
    server: Server, tape: Tape
) -> None:
    with urllib3.PoolManager() as manager:
        manager.request("GET", f"{server.url}/redirect")

    # Both the first hop and the followed one reached the server with
    # the identity.

    assert server.header(0, "traceparent") is not None
    assert server.header(1, "traceparent") is not None


def test_propagate_off_sends_nothing(server: Server) -> None:
    with (
        instrumentation(Urllib3Instrumentation, propagate=False),
        timeline(),
    ):
        with urllib3.PoolManager() as manager:
            manager.request("GET", f"{server.url}/ok")

    assert server.header(0, "traceparent") is None
