"""Tests of the test-side WSGI driver, against hand-written applications.

The driver is the one stand-in the suites rely on, so its own
obligations are pinned here: the environ it builds, the
start_response rules, consumption on demand, and close() always
reached. Where a test needs to see that the application's iterable
was closed, a wrapture binding on the iterable's close() observes it
on a timeline, the same tool the instrumentation suites use.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any

import pytest
import wrapture
from wrapture import WSGIMiddleware, binding, timeline

from tests.wsgi import Response, environ_for, request


class Body:
    """A closable response iterable, the kind a framework returns."""

    def __init__(self, *chunks: bytes, fail_after: int | None = None) -> None:
        self.chunks = chunks
        self.fail_after = fail_after

    def __iter__(self) -> Iterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if self.fail_after is not None and index >= self.fail_after:
                raise OSError("stream broke")
            yield chunk

    def close(self) -> None:
        pass


def listing(environ: dict[str, Any], start_response: Any) -> Any:
    """A plain application returning a list body."""

    start_response("200 OK", [("Content-Type", "text/plain"), ("X-Kind", "list")])
    return [b"hello ", b"world"]


def streaming(environ: dict[str, Any], start_response: Any) -> Any:
    """A generator application: start_response runs on the first pull."""

    def generate() -> Iterator[bytes]:
        start_response("200 OK", [("Content-Type", "text/plain")])
        yield b"one,"
        yield b"two,"
        yield b"three"

    return generate()


def closable(environ: dict[str, Any], start_response: Any) -> Any:
    """Returns a Body, so close() has somewhere to land."""

    start_response("200 OK", [("Content-Type", "text/plain")])
    return Body(b"a", b"b", b"c")


def failing_body(environ: dict[str, Any], start_response: Any) -> Any:
    """Headers go out, then the body breaks after one chunk."""

    start_response("200 OK", [("Content-Type", "text/plain")])
    return Body(b"a", b"b", fail_after=1)


def echoing(environ: dict[str, Any], start_response: Any) -> Any:
    """Echoes the request environ back as the body, one key per line."""

    start_response("200 OK", [("Content-Type", "text/plain")])
    keys = sorted(k for k in environ if not k.startswith("wsgi."))
    payload = environ["wsgi.input"].read()
    lines = [f"{k}={environ[k]}".encode() for k in keys]
    return [b"\n".join(lines), b"\nbody=", payload]


# ---------------------------------------------------------------------------
# the happy paths
# ---------------------------------------------------------------------------


def test_a_list_body_is_read_and_the_response_describes_it() -> None:
    response = request(listing, "GET", "/")

    assert response.status == "200 OK"
    assert response.code == 200
    assert response.header("content-type") == "text/plain"
    assert response.header("X-Kind") == "list"
    assert response.header("missing") is None
    assert response.body == b"hello world"
    assert response.text == "hello world"
    assert response.chunks == [b"hello ", b"world"]
    assert response.closed is True


def test_a_generator_body_starts_the_response_on_the_first_pull() -> None:
    response = request(streaming, consume=False)

    # Nothing pulled yet: the application has not reached
    # start_response, so the status is still unknown.

    assert response.status is None
    assert response.code is None
    assert response.body == b""

    response.read()
    response.close()

    assert response.status == "200 OK"
    assert response.body == b"one,two,three"
    assert response.closed is True


def test_the_environ_carries_the_request_as_cgi_variables() -> None:
    response = request(
        echoing,
        "POST",
        "/orders/42",
        query="expand=items",
        headers=[("Accept", "text/plain"), ("Content-Type", "application/json")],
        body=b'{"n": 1}',
    )

    lines = dict(line.split("=", 1) for line in response.text.splitlines())
    assert lines["REQUEST_METHOD"] == "POST"
    assert lines["PATH_INFO"] == "/orders/42"
    assert lines["QUERY_STRING"] == "expand=items"
    assert lines["SCRIPT_NAME"] == ""
    assert lines["SERVER_PROTOCOL"] == "HTTP/1.1"
    assert lines["REMOTE_ADDR"] == "127.0.0.1"
    assert lines["HTTP_ACCEPT"] == "text/plain"
    assert lines["CONTENT_TYPE"] == "application/json"
    assert lines["CONTENT_LENGTH"] == "8"
    assert "HTTP_CONTENT_TYPE" not in lines
    assert lines["body"] == '{"n": 1}'


def test_environ_for_has_every_wsgi_key_and_overrides_apply_last() -> None:
    environ = environ_for()

    for key in ("version", "url_scheme", "input", "errors"):
        assert f"wsgi.{key}" in environ
    for key in ("multithread", "multiprocess", "run_once"):
        assert environ[f"wsgi.{key}"] is False
    assert environ["wsgi.version"] == (1, 0)

    response = request(echoing, environ={"REMOTE_ADDR": "10.0.0.9", "X": "y"})
    lines = dict(line.split("=", 1) for line in response.text.splitlines())
    assert lines["REMOTE_ADDR"] == "10.0.0.9"
    assert lines["X"] == "y"


def test_the_errors_stream_is_captured_on_the_response() -> None:
    def complaining(environ: dict[str, Any], start_response: Any) -> Any:
        environ["wsgi.errors"].write("something odd\n")
        start_response("200 OK", [])
        return []

    response = request(complaining)

    assert response.errors.getvalue() == "something odd\n"


# ---------------------------------------------------------------------------
# close() is always reached
# ---------------------------------------------------------------------------


def test_close_is_called_after_a_full_read() -> None:
    close = binding(Body, "close")

    with timeline(close) as tape:
        response = request(closable)

    assert response.body == b"abc"
    assert [event.kind for event in tape.all] == ["call"]
    assert tape.all[0].path.endswith("Body.close")


def test_close_is_called_exactly_once_even_if_called_again() -> None:
    close = binding(Body, "close")

    with timeline(close) as tape:
        response = request(closable)
        response.close()
        response.close()

    assert len(tape.all) == 1


def test_close_is_still_called_when_the_body_raises() -> None:
    close = binding(Body, "close")

    with timeline(close) as tape:
        with pytest.raises(OSError, match="stream broke"):
            request(failing_body)

    assert len(tape.all) == 1


def test_an_abandoned_body_is_closed_with_only_what_was_read() -> None:
    close = binding(Body, "close")

    with timeline(close) as tape:
        response = request(closable, consume=False)
        response.read(1)

        # One chunk in hand, the rest never pulled, as a client
        # disconnect would leave it; close() is the server's duty.

        assert response.chunks == [b"a"]
        assert tape.all == []

        response.close()

    assert len(tape.all) == 1
    assert response.closed is True


def test_consume_false_leaves_close_to_the_caller() -> None:
    close = binding(Body, "close")

    with timeline(close) as tape:
        response = request(closable, consume=False)
        response.read()

    assert response.body == b"abc"
    assert response.closed is False
    assert tape.all == []

    response.close()


# ---------------------------------------------------------------------------
# start_response rules
# ---------------------------------------------------------------------------


def test_exc_info_reinvocation_before_the_body_replaces_the_status() -> None:
    def app(environ: dict[str, Any], start_response: Any) -> Any:
        start_response("200 OK", [("Content-Type", "text/plain")])
        try:
            raise RuntimeError("late failure")
        except RuntimeError:
            start_response(
                "500 Internal Server Error",
                [("Content-Type", "text/html")],
                sys.exc_info(),
            )
        return [b"error body"]

    response = request(app)

    assert response.status == "500 Internal Server Error"
    assert response.header("Content-Type") == "text/html"
    assert response.exc_info is not None
    assert response.exc_info[0] is RuntimeError
    assert response.body == b"error body"


def test_exc_info_reinvocation_after_the_body_started_reraises() -> None:
    def app(environ: dict[str, Any], start_response: Any) -> Any:
        start_response("200 OK", [("Content-Type", "text/plain")])

        def generate() -> Iterator[bytes]:
            yield b"partial"
            try:
                raise RuntimeError("too late")
            except RuntimeError:
                start_response("500 Internal Server Error", [], sys.exc_info())
            yield b"never"

        return generate()

    with pytest.raises(RuntimeError, match="too late"):
        request(app)


def test_a_second_start_response_without_exc_info_is_refused() -> None:
    def app(environ: dict[str, Any], start_response: Any) -> Any:
        start_response("200 OK", [])
        start_response("201 Created", [])
        return []

    with pytest.raises(AssertionError, match="twice without exc_info"):
        request(app)


def test_a_body_chunk_before_start_response_is_refused() -> None:
    def app(environ: dict[str, Any], start_response: Any) -> Any:
        def generate() -> Iterator[bytes]:
            yield b"too early"
            start_response("200 OK", [])

        return generate()

    with pytest.raises(AssertionError, match="before start_response"):
        request(app)


def test_the_write_callable_delivers_bytes_ahead_of_the_iterable() -> None:
    def app(environ: dict[str, Any], start_response: Any) -> Any:
        write = start_response("200 OK", [("Content-Type", "text/plain")])
        write(b"written ")
        return [b"iterated"]

    response = request(app)

    assert response.body == b"written iterated"
    assert response.chunks == [b"iterated"]


def test_write_before_start_response_is_refused() -> None:
    # An application only ever gets write() from start_response, so
    # the rule is pinned on a fresh Response directly.

    response = Response(environ_for())
    with pytest.raises(AssertionError, match="before start_response"):
        response._write(b"x")


def test_reading_before_the_application_was_called_is_an_error() -> None:
    response = Response(environ_for())
    with pytest.raises(RuntimeError, match="has not been called"):
        response.read()


# ---------------------------------------------------------------------------
# with wrapture's middleware: the property the instrumentation suites need
# ---------------------------------------------------------------------------


def test_a_request_event_closes_when_the_driver_closes_the_body() -> None:
    wrapped = WSGIMiddleware(closable, label="closable")

    with timeline() as tape:
        response = request(wrapped, "GET", "/export", consume=False)

        # The application has returned but its body is unread, so the
        # request is in flight: the event exists without a closing
        # result or duration.

        (event,) = tape.all
        assert event.kind == "request"
        assert event.result is wrapture.MISSING
        assert event.duration is None

        response.read()
        response.close()

    # The same event, re-read from the tape now that it has closed.

    (closed,) = tape.all
    assert closed is event
    assert closed.result == "200 OK"
    assert closed.duration is not None
    assert closed.items == 3
    assert closed.data["method"] == "GET"
    assert closed.data["path"] == "/export"


def test_the_default_path_completes_the_request_event_before_returning() -> None:
    wrapped = WSGIMiddleware(streaming, label="streaming")

    with timeline() as tape:
        response = request(wrapped, "GET", "/stream")

    (event,) = tape.all
    assert response.body == b"one,two,three"
    assert event.result == "200 OK"
    assert event.items == 3
    assert event.duration is not None
