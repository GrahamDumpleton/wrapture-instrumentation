"""With the requests instrumentation applied above: urllib3 is the
layer requests does its wire work through, so the requests leaf
silences it, and switching that leaf off exposes it beneath."""

from __future__ import annotations

import pytest

pytest.importorskip("requests")

import requests
from wrapture import Event, Tape, instrumentation, timeline

from tests.httpserver import Server
from wrapture_instrumentation.external.requests import RequestsInstrumentation
from wrapture_instrumentation.external.urllib3 import Urllib3Instrumentation

SEND = "requests.sessions:Session.send"


def urllib3_events(tape: Tape) -> list[Event]:
    return [event for event in tape.all if event.path and "urllib3" in event.path]


def test_the_requests_leaf_silences_urllib3_beneath_it(server: Server) -> None:
    with (
        instrumentation(RequestsInstrumentation),
        instrumentation(Urllib3Instrumentation),
        timeline() as tape,
    ):
        requests.get(f"{server.url}/ok")

    # One requests leaf, and urllib3's own work beneath it stays out.

    (send,) = [event for event in tape.all if event.path == SEND]
    assert send.data["status"] == 200
    assert urllib3_events(tape) == []


def test_requests_leaf_off_exposes_urllib3(server: Server) -> None:
    with (
        instrumentation(RequestsInstrumentation, leaf=False),
        instrumentation(Urllib3Instrumentation),
        timeline() as tape,
    ):
        requests.get(f"{server.url}/ok")

    # With the requests leaf off, urllib3's request records beneath
    # the send, itself a leaf that then hides http.client below it.

    (send,) = [event for event in tape.all if event.path == SEND]
    nested = urllib3_events(tape)
    assert nested
    assert all(tape.parent_of(event) is not None for event in nested)


def test_raw_urllib3_use_beside_requests_still_records(server: Server) -> None:
    import urllib3

    with (
        instrumentation(RequestsInstrumentation),
        instrumentation(Urllib3Instrumentation),
        timeline() as tape,
    ):
        requests.get(f"{server.url}/ok")

        with urllib3.PoolManager() as manager:
            manager.request("GET", f"{server.url}/ok")

    # The direct urllib3 call is nobody's child, so it records its own
    # leaf even while the requests one silences its internal use.

    roots = [event for event in tape.all if tape.parent_of(event) is None]
    assert any("urllib3" in (event.path or "") for event in roots)
