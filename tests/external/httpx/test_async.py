"""The async client mirrors the sync one: one external leaf per
request on AsyncClient.send, the same contract keys, the same
propagation, the event covering the await."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from wrapture import Event, Tape

from tests.httpserver import Server

SEND = "httpx:AsyncClient.send"


def only(tape: Tape) -> Event:
    """The one event on the tape."""

    (event,) = tape.all

    return event


def test_a_request_records_one_external_leaf(server: Server, tape: Tape) -> None:
    async def fetch() -> httpx.Response:
        async with httpx.AsyncClient() as client:
            return await client.get(f"{server.url}/ok")

    response = asyncio.run(fetch())
    assert response.text == "ok"

    event = only(tape)
    assert event.path == SEND
    assert event.label is None
    assert event.category == "external"
    assert event.exception is None
    assert tape.children_of(event) == []


def test_the_event_carries_the_external_contract_keys(
    server: Server, tape: Tape
) -> None:
    async def fetch() -> None:
        async with httpx.AsyncClient() as client:
            await client.get(f"{server.url}/ok?token=hunter2&page=3")

    asyncio.run(fetch())

    port = int(server.url.rpartition(":")[2])

    event = only(tape)
    assert event.data == {
        "method": "GET",
        "url": f"{server.url}/ok",
        "host": "127.0.0.1",
        "port": port,
        "path": "/ok",
        "query": "token=<redacted>&page=3",
        "status": 200,
    }
    assert "hunter2" not in repr(event.arguments)


def test_an_error_status_is_a_status_not_an_exception(
    server: Server, tape: Tape
) -> None:
    async def fetch() -> httpx.Response:
        async with httpx.AsyncClient() as client:
            return await client.get(f"{server.url}/missing")

    assert asyncio.run(fetch()).status_code == 404

    event = only(tape)
    assert event.data["status"] == 404
    assert event.exception is None


def test_a_connection_failure_records_the_error_with_no_status(tape: Tape) -> None:
    # A refused connection is a ConnectError and a filtered port
    # (Windows) times out as a ConnectTimeout; both are the
    # TransportError family, recorded the same way.

    async def fetch() -> None:
        async with httpx.AsyncClient() as client:
            await client.get("http://127.0.0.1:9/ok", timeout=1)

    with pytest.raises(httpx.TransportError):
        asyncio.run(fetch())

    event = only(tape)
    assert "status" not in event.data
    assert isinstance(event.exception, httpx.TransportError)


def test_a_followed_redirect_is_one_event_named_by_the_original_url(
    server: Server, tape: Tape
) -> None:
    async def fetch() -> httpx.Response:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await client.get(f"{server.url}/redirect")

    assert asyncio.run(fetch()).status_code == 200
    assert [seen.path for seen in server.received] == ["/redirect", "/ok"]

    event = only(tape)
    assert event.data["url"] == f"{server.url}/redirect"
    assert event.data["status"] == 200


def test_the_request_carries_the_trees_trace_identity(
    server: Server, tape: Tape
) -> None:
    async def fetch() -> None:
        async with httpx.AsyncClient() as client:
            await client.get(f"{server.url}/ok")

    asyncio.run(fetch())

    (event,) = tape.roots()
    assert event.trace is not None

    header = server.header(0, "traceparent")
    assert header is not None
    assert event.trace.slots["w3c"].trace_id in header
