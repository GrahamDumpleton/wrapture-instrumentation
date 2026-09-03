"""An in-process ASGI driver: the server's side of the ASGI 3 HTTP
protocol, for tests.

The WSGI driver in tests/wsgi.py plays PEP 3333 exactly so the tests
own the moments a request event is tied to; this is its ASGI
counterpart. It builds a complete HTTP scope, supplies a receive
channel that hands over the request body and then reports
disconnect, collects every message the application sends, and awaits
the application to completion under asyncio.run, so a test stays
synchronous and the request event has closed by the time the driver
returns. An exception the application raises propagates to the
caller, exactly as an ASGI server would see it.

    response = request(app, "GET", "/quote/widget")
    assert response.code == 200
    assert response.body == b"..."
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

ASGIApplication = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Any],
    Awaitable[Any],
]


class Response:
    """What the driver hands back: the status and headers from the
    http.response.start message, the body assembled from every
    http.response.body message, and the raw message list."""

    def __init__(self) -> None:
        self.code: int | None = None
        self.headers: list[tuple[bytes, bytes]] | None = None
        self.messages: list[dict[str, Any]] = []

    @property
    def body(self) -> bytes:
        """Every body byte the application sent."""

        return b"".join(
            message.get("body", b"")
            for message in self.messages
            if message["type"] == "http.response.body"
        )

    @property
    def text(self) -> str:
        """The body decoded as UTF-8."""

        return self.body.decode("utf-8")

    def header(self, name: str) -> str | None:
        """The value of the named response header, matched without
        regard to case, or None."""

        if self.headers is None:
            return None

        wanted = name.lower().encode("latin-1")
        for key, value in self.headers:
            if key.lower() == wanted:
                return value.decode("latin-1")

        return None


def scope_for(
    method: str = "GET",
    path: str = "/",
    *,
    query: str = "",
    headers: Iterable[tuple[str, str]] = (),
    body: bytes = b"",
) -> dict[str, Any]:
    """Build a complete ASGI 3 HTTP scope for one request."""

    encoded = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in headers
    ]

    if body and not any(name == b"content-length" for name, _ in encoded):
        encoded.append((b"content-length", str(len(body)).encode("latin-1")))

    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": query.encode("latin-1"),
        "root_path": "",
        "headers": encoded,
        "client": ("127.0.0.1", 5000),
        "server": ("127.0.0.1", 80),
    }


def request(
    app: ASGIApplication,
    method: str = "GET",
    path: str = "/",
    *,
    query: str = "",
    headers: Iterable[tuple[str, str]] = (),
    body: bytes = b"",
    scope: dict[str, Any] | None = None,
) -> Response:
    """Call the application once, as a server would, and return the
    `Response` once its coroutine has completed.

    The receive channel hands the whole body over in one
    http.request message and answers http.disconnect afterwards. An
    exception out of the application propagates; the caller sees it
    exactly as an ASGI server would.
    """

    environ = (
        scope
        if scope is not None
        else scope_for(method, path, query=query, headers=headers, body=body)
    )

    response = Response()

    async def drive() -> None:
        delivered = False

        async def receive() -> dict[str, Any]:
            nonlocal delivered

            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            response.messages.append(message)

            if message["type"] == "http.response.start":
                response.code = int(message["status"])
                response.headers = list(message.get("headers", []))

        await app(environ, receive, send)

    asyncio.run(drive())

    return response
