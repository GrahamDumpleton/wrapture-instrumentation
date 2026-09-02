"""What the interposed middleware records: one request event per
request, named by the application, its data and redaction, the
ignore_paths filter, the trace join, and removal un-wrapping a
running server."""

from __future__ import annotations

import time
import urllib.request

from wrapture import Tape, instrumentation

from tests.server.wsgiref_simple_server.conftest import hello_app, serve, settled
from wrapture_instrumentation.server.wsgiref_simple_server import (
    WSGIRefSimpleServerInstrumentation,
)

APP = f"{hello_app.__module__}:{hello_app.__qualname__}"

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-aaaaaaaaaaaaaaaa-01"


def fetch(url: str, headers: dict[str, str] | None = None) -> None:
    request = urllib.request.Request(url, headers=headers or {})

    with urllib.request.urlopen(request) as response:
        response.read()


def test_a_request_records_one_event_named_by_the_application(
    instrumented: None, tape: Tape
) -> None:
    serving = serve(hello_app)
    url = next(serving)
    try:
        fetch(f"{url}/widget?item=widget&token=hunter2")
    finally:
        next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert event.path == APP
    assert event.data["method"] == "GET"
    assert event.data["path"] == "/widget"
    assert event.result == "200 OK"

    # The query is recorded with the built-in sensitive names masked.

    assert "item=widget" in event.data["query"]
    assert "hunter2" not in repr(event.data)


def test_ignore_paths_records_nothing_at_all(tape: Tape) -> None:
    with instrumentation(WSGIRefSimpleServerInstrumentation, ignore_paths=["/health"]):
        serving = serve(hello_app)
        url = next(serving)
        try:
            fetch(f"{url}/health")
            fetch(f"{url}/work")
        finally:
            next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert event.data["path"] == "/work"


def test_redact_masks_named_parameters(tape: Tape) -> None:
    with instrumentation(WSGIRefSimpleServerInstrumentation, redact=["voucher"]):
        serving = serve(hello_app)
        url = next(serving)
        try:
            fetch(f"{url}/buy?voucher=SECRET99")
        finally:
            next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert "voucher" in event.data["query"]
    assert "SECRET99" not in repr(event.data)


def test_a_traceparent_header_joins_the_callers_trace(
    instrumented: None, tape: Tape
) -> None:
    serving = serve(hello_app)
    url = next(serving)
    try:
        fetch(url, headers={"traceparent": TRACEPARENT})
    finally:
        next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert event.trace is not None
    assert event.trace.slots["w3c"].trace_id == "0af7651916cd43dd8448eb211c80319c"


def test_removal_unwraps_a_running_server(tape: Tape) -> None:
    serving = serve(hello_app)
    url = next(serving)
    try:
        with instrumentation(WSGIRefSimpleServerInstrumentation):
            fetch(url)
            settled(tape)

        # The same server, after removal: get_app hands back the bare
        # application again, so nothing further records.

        fetch(url)
        time.sleep(0.05)
    finally:
        next(serving, None)

    assert len([event for event in tape.all if event.kind == "request"]) == 1
