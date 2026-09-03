"""What the instrumentation records: the whole path through
wrapture.instrumentation() with a timeline tape hearing what the
bindings observe, requests driven through the ASGI test driver."""

from __future__ import annotations

import pytest
from wrapture import Tape

from tests.asgi import request
from tests.framework.fastapi.shop import make_app

SHOP = "tests.framework.fastapi.shop"

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-aaaaaaaaaaaaaaaa-01"

BOUNDARY = "fastapi.applications:FastAPI.__call__"


def test_a_request_records_one_tree_with_the_endpoint_beneath_it(
    tape: Tape,
) -> None:
    app = make_app()
    response = request(app, "GET", "/quote/widget")

    assert response.code == 200
    assert response.body == b'{"item":"widget","price":42}'

    # The request event carries the HTTP details plus the matched
    # route pattern and name; the endpoint, its typed parameter
    # converted and its response model applied, nests beneath it as a
    # call labelled by the route's name.

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
    # FastAPI runs a sync endpoint in a threadpool; the call still
    # nests beneath the request, and the route's own name labels it.

    response = request(make_app(), "GET", "/pricing")

    assert response.code == 200

    (seen, endpoint) = tape.all
    assert seen.data["route"] == "/pricing"
    assert seen.data["endpoint"] == "prices"
    assert endpoint.label == "prices"
    assert endpoint.path == f"{SHOP}:make_app.<locals>.pricing"
    assert tape.parent_of(endpoint) is seen


def test_a_dependency_using_endpoint_records_normally(tape: Tape) -> None:
    # Depends() is resolved by FastAPI around the observed endpoint;
    # the endpoint records with the resolved value as its argument.

    response = request(make_app(), "GET", "/basket")

    assert response.code == 200
    assert response.body == b'{"shopper":"pat"}'

    (seen, endpoint) = tape.all
    assert seen.data["endpoint"] == "basket"
    assert endpoint.label == "basket"


def test_a_router_included_route_annotates_its_full_pattern(tape: Tape) -> None:
    # include_router folds the router's prefix into the route it
    # copies, so the annotated pattern is the full path; the copy is
    # registered through the same constructor, and the already
    # observed endpoint is not wrapped again.

    response = request(make_app(), "GET", "/reports/summary")

    assert response.code == 200

    (seen, endpoint) = tape.all
    assert seen.data["route"] == "/reports/summary"
    assert seen.data["endpoint"] == "summary"
    assert endpoint.label == "summary"
    assert tape.parent_of(endpoint) is seen


def test_the_query_is_recorded_with_secrets_masked(tape: Tape) -> None:
    request(make_app(), "GET", "/", query="token=hunter2&item=widget")

    (seen, _) = tape.all
    assert "item=widget" in seen.data["query"]
    assert "hunter2" not in repr(seen.data)


def test_a_failing_endpoint_is_recorded_on_the_request(tape: Tape) -> None:
    # starlette's ServerErrorMiddleware answers 500 and then always
    # re-raises, so the driver sees the exception exactly as an ASGI
    # server would, and the request event carries it beside the
    # response's size; the endpoint's own event carries it too.

    with pytest.raises(KeyError):
        request(make_app(), "GET", "/quote/missing")

    (seen, endpoint) = tape.all
    assert isinstance(seen.exception, KeyError)
    assert seen.data["bytes"] > 0
    assert isinstance(endpoint.exception, KeyError)


def test_a_validation_failure_is_a_status_not_an_exception(tape: Tape) -> None:
    # A parameter that fails validation never reaches the endpoint:
    # FastAPI answers 422 through its own handler, control flow
    # rather than a failure, so the request records the status and
    # nothing else.

    from typing import cast

    from fastapi import FastAPI

    app = cast(FastAPI, make_app())

    @app.get("/count/{amount}")
    async def counted(amount: int) -> dict[str, int]:
        return {"amount": amount}

    response = request(app, "GET", "/count/plenty")

    assert response.code == 422

    # The reason phrase for 422 differs across Python versions, so
    # only the code is asserted.

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert seen.exception is None
    assert seen.result is not None
    assert str(seen.result).startswith("422")


def test_a_request_that_matches_no_route_has_no_route_annotation(
    tape: Tape,
) -> None:
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
