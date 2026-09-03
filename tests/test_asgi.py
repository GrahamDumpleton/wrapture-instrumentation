"""The ASGI driver's own tests: it plays the server's side of the
protocol correctly before any suite leans on it."""

from __future__ import annotations

from typing import Any

import pytest

from tests.asgi import request


async def hello_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"hello"})


async def echo_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    message = await receive()

    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": message["body"]})


async def broken_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    raise RuntimeError("boom")


def test_a_plain_response_is_assembled() -> None:
    response = request(hello_app, "GET", "/anything")

    assert response.code == 200
    assert response.header("Content-Type") == "text/plain"
    assert response.body == b"hello"
    assert response.text == "hello"


def test_the_body_is_delivered_through_receive() -> None:
    response = request(echo_app, "POST", "/echo", body=b"name=pat")

    assert response.code == 200
    assert response.body == b"name=pat"


def test_the_scope_carries_the_request_line() -> None:
    seen: dict[str, Any] = {}

    async def inspector(scope: dict[str, Any], receive: Any, send: Any) -> None:
        seen.update(scope)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    request(
        inspector,
        "GET",
        "/widget",
        query="item=widget",
        headers=[("X-Own", "yes")],
    )

    assert seen["method"] == "GET"
    assert seen["path"] == "/widget"
    assert seen["query_string"] == b"item=widget"
    assert (b"x-own", b"yes") in seen["headers"]


def test_an_application_exception_propagates() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        request(broken_app, "GET", "/")
