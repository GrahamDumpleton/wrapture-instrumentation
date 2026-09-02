"""One boundary per request, however many layers record: an inner
recording middleware, an application that is already the middleware,
and a Flask application under both instrumentations, served by the
server app.run() would start."""

from __future__ import annotations

import urllib.request
from collections.abc import Iterable
from typing import Any

import wrapture
from wrapture import Tape, instrumentation

from tests.server.werkzeug_serving.conftest import hello_app, serve, settled


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        body: bytes = response.read()

    return body


def test_an_inner_middleware_leaves_one_boundary(
    instrumented: None, tape: Tape
) -> None:
    # The application carries its own recording middleware inside,
    # invisible from the outside: the interposed outer middleware
    # records and marks the environ, the inner one sees the mark and
    # passes through.

    inner = wrapture.WSGIMiddleware(hello_app)

    def app(environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        body: Iterable[bytes] = inner(environ, start_response)

        return body

    serving = serve(app)
    url = next(serving)
    try:
        assert fetch(url) == b"hello"
    finally:
        next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert event.path == f"{app.__module__}:{app.__qualname__}"


def test_an_application_that_is_the_middleware_passes_through(
    instrumented: None, tape: Tape
) -> None:
    # Already a WSGIMiddleware: the interposition leaves it alone and
    # it records as itself, named by the application it wraps.

    serving = serve(wrapture.WSGIMiddleware(hello_app))
    url = next(serving)
    try:
        assert fetch(url) == b"hello"
    finally:
        next(serving, None)

    (event,) = [event for event in settled(tape) if event.kind == "request"]
    assert event.path == f"{hello_app.__module__}:{hello_app.__qualname__}"


def test_a_flask_application_records_once_with_its_route(tape: Tape) -> None:
    # The app.run() shape: Flask's instrumentation wraps the
    # application's own wsgi_app, the werkzeug instrumentation wraps
    # whatever the server is built with, and a request still records
    # as one tree, the framework's annotations landing on the one
    # boundary.

    import flask

    from wrapture_instrumentation.framework.flask import FlaskInstrumentation
    from wrapture_instrumentation.server.werkzeug_serving import (
        WerkzeugServingInstrumentation,
    )

    with (
        instrumentation(FlaskInstrumentation),
        instrumentation(WerkzeugServingInstrumentation),
    ):
        app = flask.Flask("shopfront")

        @app.route("/hello/<name>")
        def hello(name: str) -> str:
            return f"hi {name}"

        serving = serve(app)
        url = next(serving)
        try:
            assert fetch(f"{url}/hello/pat") == b"hi pat"
        finally:
            next(serving, None)

    events = settled(tape)
    (request,) = [event for event in events if event.kind == "request"]

    assert request.data["route"] == "/hello/<name>"
    assert request.data["endpoint"] == "hello"

    # The view records beneath the one boundary.

    labels = [event.label for event in events if event.label]
    assert "hello" in labels
