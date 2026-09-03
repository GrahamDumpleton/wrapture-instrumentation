"""What the instrumentation records: requests through the real WSGI
and ASGI handlers, the route annotation, every view shape, and the
exception rules."""

from __future__ import annotations

import pytest
from wrapture import Tape

from tests import asgi, wsgi
from tests.framework.django.shop import make_asgi_app, make_wsgi_app

VIEWS = "tests.framework.django.shop.views"

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-aaaaaaaaaaaaaaaa-01"

WSGI_BOUNDARY = "django.core.handlers.wsgi:WSGIHandler.__call__"
ASGI_BOUNDARY = "django.core.handlers.asgi:ASGIHandler.__call__"


def test_a_wsgi_request_records_one_tree_with_the_view_beneath_it(
    tape: Tape,
) -> None:
    response = wsgi.request(make_wsgi_app(), "GET", "/quote/widget/")

    assert response.status == "200 OK"
    assert response.body == b"widget: 42 coins"

    # The request event carries the HTTP details plus the matched
    # route pattern and view name; the view nests beneath it as a
    # call, labelled by the URL name with its path still locating the
    # code.

    (seen, view) = tape.all
    assert seen.kind == "request"
    assert seen.path == WSGI_BOUNDARY
    assert seen.data["method"] == "GET"
    assert seen.data["path"] == "/quote/widget/"
    assert seen.data["route"] == "quote/<str:item>/"
    assert seen.data["endpoint"] == "quoted"

    assert view.kind == "call"
    assert view.label == "quoted"
    assert view.path == f"{VIEWS}:quoted"
    assert tape.parent_of(view) is seen


def test_an_asgi_request_records_one_tree_with_the_async_view_beneath_it(
    tape: Tape,
) -> None:
    # The async view proves the observed proxy still reads as a
    # coroutine function to Django, which awaits it.

    response = asgi.request(make_asgi_app(), "GET", "/motd/")

    assert response.code == 200
    assert response.body == b"welcome"

    (seen, view) = tape.all
    assert seen.kind == "request"
    assert seen.path == ASGI_BOUNDARY
    assert seen.data["route"] == "motd/"
    assert seen.data["endpoint"] == "motd"

    assert view.kind == "call"
    assert view.label == "motd"
    assert view.path == f"{VIEWS}:motd"
    assert tape.parent_of(view) is seen


def test_a_sync_view_under_asgi_still_nests_beneath_its_request(
    tape: Tape,
) -> None:
    # Django runs a sync view on a worker thread under ASGI; the call
    # still nests beneath the request.

    response = asgi.request(make_asgi_app(), "GET", "/")

    assert response.code == 200

    (seen, view) = tape.all
    assert seen.path == ASGI_BOUNDARY
    assert view.label == "index"
    assert tape.parent_of(view) is seen


def test_an_int_converter_route_annotates_the_pattern_not_the_path(
    tape: Tape,
) -> None:
    response = wsgi.request(make_wsgi_app(), "GET", "/archive/1999/")

    assert response.status == "200 OK"

    (seen, _) = tape.all
    assert seen.data["path"] == "/archive/1999/"
    assert seen.data["route"] == "archive/<int:year>/"
    assert seen.data["endpoint"] == "year_archive"


def test_a_class_based_view_records_one_call_for_the_whole_view(
    tape: Tape,
) -> None:
    # The resolved callback for a CBV is the closure as_view()
    # returned; observing it gives one event labelled by the URL
    # name, with dispatch and the get method running inside it.

    response = wsgi.request(make_wsgi_app(), "GET", "/catalog/")

    assert response.status == "200 OK"
    assert response.body == b"catalog"

    (seen, view) = tape.all
    assert view.kind == "call"
    assert view.label == "catalog"
    assert tape.parent_of(view) is seen


def test_an_unnamed_pattern_keeps_the_derived_path_as_the_name(
    tape: Tape,
) -> None:
    response = wsgi.request(make_wsgi_app(), "GET", "/about/")

    assert response.status == "200 OK"

    (seen, view) = tape.all
    assert seen.data["route"] == "about/"
    assert view.label is None
    assert view.path == f"{VIEWS}:about"


def test_the_query_is_recorded_with_secrets_masked(tape: Tape) -> None:
    wsgi.request(
        make_wsgi_app(),
        "GET",
        "/quote/widget/",
        query="token=hunter2&item=widget",
    )

    (seen, view) = tape.all
    assert "item=widget" in seen.data["query"]
    assert "hunter2" not in repr(seen.data)

    # The request's repr carries the raw query string, so the view's
    # captured request argument reduces to its type; the URL-derived
    # item argument passes.

    assert view.arguments is not None
    assert view.arguments["request"] == "<WSGIRequest>"
    assert view.arguments["item"] == "widget"
    assert "hunter2" not in repr(view.arguments)


def test_a_streaming_response_still_records_one_request(tape: Tape) -> None:
    response = wsgi.request(make_wsgi_app(), "GET", "/export/")

    assert response.status == "200 OK"
    assert response.body == b"row1\nrow2\n"

    (seen, view) = tape.all
    assert seen.kind == "request"
    assert view.label == "export"


def test_an_unhandled_exception_is_noted_and_the_response_is_500(
    tape: Tape,
) -> None:
    # Django's catch-all turns the failure into a 500 and the request
    # completes normally, so the boundary sees no exception of its
    # own; the noting binding puts the failure on the request event
    # beside the status. The failing view's own event carries the
    # exception directly.

    response = wsgi.request(make_wsgi_app(), "GET", "/quote/missing/")

    assert response.code == 500

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert seen.exception is None
    assert [type(caught.exception) for caught in seen.caught] == [KeyError]

    (view,) = [event for event in tape.all if event.label == "quoted"]
    assert isinstance(view.exception, KeyError)


def test_an_http404_is_its_status_not_a_failure(tape: Tape) -> None:
    # Http404 is control flow that carries a status: converted to its
    # response upstream of the catch-all, so nothing is noted.

    response = wsgi.request(make_wsgi_app(), "GET", "/missing/")

    assert response.code == 404

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert seen.exception is None
    assert seen.caught == ()

    # The route still annotated: resolution succeeded, the view chose
    # the 404.

    assert seen.data["route"] == "missing/"


def test_a_request_that_matches_no_route_has_no_route_annotation(
    tape: Tape,
) -> None:
    response = wsgi.request(make_wsgi_app(), "GET", "/nowhere")

    assert response.code == 404

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert seen.exception is None
    assert seen.caught == ()
    assert "route" not in seen.data
    assert "endpoint" not in seen.data


@pytest.mark.parametrize("transport", ["wsgi", "asgi"])
def test_a_traceparent_header_joins_the_callers_trace(
    tape: Tape, transport: str
) -> None:
    if transport == "wsgi":
        wsgi.request(
            make_wsgi_app(), "GET", "/", headers=[("traceparent", TRACEPARENT)]
        )
    else:
        asgi.request(
            make_asgi_app(), "GET", "/", headers=[("traceparent", TRACEPARENT)]
        )

    (seen, _) = tape.all
    assert seen.trace is not None
    assert seen.trace.slots["w3c"].trace_id == "0af7651916cd43dd8448eb211c80319c"
