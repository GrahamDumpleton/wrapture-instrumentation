"""What the instrumentation records: the whole path through
wrapture.instrumentation() with a timeline tape hearing what the
bindings observe, requests driven through the WSGI test driver."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import wrapture
from wrapture import Tape, instrumentation, timeline

from tests.framework_flask.shop import make_app
from tests.wsgi import request
from wrapture_instrumentation.framework_flask import FlaskInstrumentation

SHOP = "tests.framework_flask.shop"


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(FlaskInstrumentation), timeline() as recorded:
        yield recorded


def test_a_request_records_one_tree_with_the_view_beneath_it(tape: Tape) -> None:
    app = make_app()
    response = request(app, "GET", "/quote/widget")

    assert response.status == "200 OK"
    assert tape.tree() == (
        "GET /quote/widget (shop.wsgi_app)  -> '200 OK'\n"
        f"  {SHOP}.quoted(item='widget')  -> <Response 29 bytes [200 OK]>"
    )

    # The request event carries the HTTP details; the view nests
    # beneath it as a call.

    (seen, view) = tape.all
    assert seen.kind == "request"
    assert seen.label == "shop.wsgi_app"
    assert seen.data["method"] == "GET"
    assert seen.data["path"] == "/quote/widget"
    assert seen.result == "200 OK"
    assert view.kind == "call"
    assert view.path == f"{SHOP}:quoted"
    assert tape.parent_of(view) is seen


def test_every_kind_of_view_is_observed(tape: Tape) -> None:
    app = make_app()

    for path in ("/", "/catalog", "/reports/summary"):
        request(app, "GET", path)

    # A plain function, a MethodView's generated view and a blueprint
    # view each record beneath their request. (The MethodView's label
    # is Flask's generated closure name, a scope-pass item.)

    views = [event for event in tape.all if event.kind == "call"]
    assert [event.path for event in views] == [
        f"{SHOP}:index",
        f"{SHOP}:View.as_view.<locals>.view",
        f"{SHOP}:summary",
    ]
    assert all(tape.parent_of(event) is not None for event in views)


def test_a_failing_view_is_noted_on_the_request(tape: Tape) -> None:
    app = make_app()
    response = request(app, "GET", "/quote/missing")

    # Flask catches the KeyError and answers 500, so the request
    # completes normally from the server's point of view; the
    # handle_exception binding notes the exception against the
    # request, so its line says both.

    assert response.status == "500 INTERNAL SERVER ERROR"
    assert tape.tree() == (
        "GET /quote/missing (shop.wsgi_app)  -> '500 INTERNAL SERVER ERROR'"
        "  !! KeyError\n"
        f"  {SHOP}.quoted(item='missing')  !! KeyError"
    )

    (seen, view) = tape.all
    assert seen.exception is None
    assert [type(caught.exception) for caught in seen.caught] == [KeyError]
    assert isinstance(view.exception, KeyError)


def test_a_streaming_request_stays_open_until_the_body_closes(tape: Tape) -> None:
    app = make_app()
    response = request(app, "GET", "/export", consume=False)

    # The view has returned a streamed Response; the request is still
    # in flight until the server consumes and closes the body.

    (seen, view) = tape.all
    assert view.result is not wrapture.MISSING
    assert seen.result is wrapture.MISSING
    assert seen.duration is None

    response.read()
    response.close()

    (closed, _) = tape.all
    assert closed.result == "200 OK"
    assert closed.duration is not None
    assert closed.items == 2
    assert response.body == b"gadget,120\nwidget,25\n"


def test_two_applications_record_under_their_own_labels(tape: Tape) -> None:
    first = make_app("first")
    second = make_app("second")

    request(first, "GET", "/")
    request(second, "GET", "/")

    labels = [event.label for event in tape.all if event.kind == "request"]
    assert labels == ["first.wsgi_app", "second.wsgi_app"]


def test_nothing_records_outside_a_recording_scope() -> None:
    # Applied but with no sink listening, the middleware and the
    # observed views pass straight through.

    with instrumentation(FlaskInstrumentation):
        app = make_app()
        response = request(app, "GET", "/quote/widget")

    assert response.status == "200 OK"
    assert response.body == b'{"item":"widget","price":25}\n'


def test_views_registered_before_the_instrumentation_applies_are_not_observed() -> None:
    # The registrar binding intercepts registration; an application
    # built before the instrumentation applied already has its views
    # captured in its dispatch table and its wsgi_app unwrapped. This
    # is why the runner applies the config before the application
    # imports.

    app = make_app("early")

    with instrumentation(FlaskInstrumentation), timeline() as tape:
        request(app, "GET", "/quote/widget")

    assert tape.all == []
