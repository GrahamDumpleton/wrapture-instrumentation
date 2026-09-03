"""What the instrumentation records: the whole path through
wrapture.instrumentation() with a timeline tape hearing what the
bindings observe, requests driven through the ASGI test driver."""

from __future__ import annotations

import pytest
from wrapture import Tape

from tests.asgi import request
from tests.framework.starlette.shop import make_app

SHOP = "tests.framework.starlette.shop"

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-aaaaaaaaaaaaaaaa-01"

BOUNDARY = "starlette.applications:Starlette.__call__"


def test_a_request_records_one_tree_with_the_endpoint_beneath_it(
    tape: Tape,
) -> None:
    app = make_app()
    response = request(app, "GET", "/quote/widget")

    assert response.code == 200
    assert response.body == b"widget: 42 coins"

    # The request event carries the HTTP details plus the matched
    # route pattern and name; the endpoint nests beneath it as a
    # call, labelled by the route's name with its path still locating
    # the code.

    (seen, endpoint) = tape.all
    assert seen.kind == "request"
    assert seen.path == BOUNDARY
    assert seen.data["method"] == "GET"
    assert seen.data["path"] == "/quote/widget"
    assert seen.data["route"] == "/quote/{item}"
    assert seen.data["endpoint"] == "quoted"
    assert seen.result == "200 OK"

    assert endpoint.kind == "call"
    assert endpoint.label == "quoted"
    assert endpoint.path == f"{SHOP}:make_app.<locals>.quoted"
    assert tape.parent_of(endpoint) is seen


def test_a_sync_endpoint_records_beneath_its_request(tape: Tape) -> None:
    # starlette runs a sync endpoint in a threadpool; the call still
    # nests beneath the request, and the route's own name labels it.

    response = request(make_app(), "GET", "/pricing")

    assert response.code == 200

    (seen, endpoint) = tape.all
    assert seen.data["route"] == "/pricing"
    assert seen.data["endpoint"] == "prices"
    assert endpoint.label == "prices"
    assert endpoint.path == f"{SHOP}:make_app.<locals>.pricing"
    assert tape.parent_of(endpoint) is seen


def test_a_partial_endpoint_passes_through_unobserved(tape: Tape) -> None:
    # A functools.partial is not a plain function, so it is left for
    # starlette to handle and no call event records: the request
    # boundary and its route annotation still tell the story.

    response = request(make_app(), "GET", "/motd")

    assert response.code == 200
    assert response.body == b"welcome"

    (seen,) = tape.all
    assert seen.kind == "request"
    assert seen.data["route"] == "/motd"


def test_a_mounted_route_annotates_the_pattern_it_owns(tape: Tape) -> None:
    # The route inside a Mount knows only its own part of the path;
    # the pattern below the mount point is what it annotates.

    response = request(make_app(), "GET", "/reports/summary")

    assert response.code == 200

    (seen, endpoint) = tape.all
    assert seen.data["path"] == "/reports/summary"
    assert seen.data["route"] == "/summary"
    assert endpoint.label == "summary"


def test_the_query_is_recorded_with_secrets_masked(tape: Tape) -> None:
    request(make_app(), "GET", "/quote/widget", query="token=hunter2&item=widget")

    (seen, _) = tape.all
    assert "item=widget" in seen.data["query"]
    assert "hunter2" not in repr(seen.data)


def test_a_failing_endpoint_is_recorded_on_the_request(tape: Tape) -> None:
    # starlette's ServerErrorMiddleware answers 500 and then always
    # re-raises, so the driver sees the exception exactly as an ASGI
    # server would. The request event carries the exception rather
    # than a result: the application coroutine raised, so there is
    # nothing it returned, even though the 500 went out on the wire
    # first (the response body's size is on the event).

    with pytest.raises(KeyError):
        request(make_app(), "GET", "/quote/missing")

    (seen, endpoint) = tape.all
    assert isinstance(seen.exception, KeyError)
    assert seen.data["bytes"] > 0
    assert isinstance(endpoint.exception, KeyError)


def test_a_request_that_matches_no_route_has_no_route_annotation(
    tape: Tape,
) -> None:
    # A 404 never reached a route, so there is no pattern to group
    # by: the request records with its raw path and no route or
    # endpoint keys, rather than an empty or invented value.

    response = request(make_app(), "GET", "/nowhere")

    assert response.code == 404

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert seen.exception is None
    assert "route" not in seen.data
    assert "endpoint" not in seen.data


def test_a_traceparent_header_joins_the_callers_trace(tape: Tape) -> None:
    request(make_app(), "GET", "/", headers=[("traceparent", TRACEPARENT)])

    (seen, _) = tape.all
    assert seen.trace is not None
    assert seen.trace.slots["w3c"].trace_id == "0af7651916cd43dd8448eb211c80319c"
