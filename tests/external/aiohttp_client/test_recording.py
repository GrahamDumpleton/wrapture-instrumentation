"""What the instrumentation records: one external leaf per request,
the contract keys it carries, an error status being a status rather
than an exception, a followed redirect resolving inside the one
event, and what stays out of capture."""

from __future__ import annotations

import pytest
from aiohttp import ClientConnectorError, ClientSession
from wrapture import Event, Tape, instrumentation, timeline

from tests.external.aiohttp_client.conftest import run
from tests.httpserver import Server
from wrapture_instrumentation.external.aiohttp_client import (
    AiohttpClientInstrumentation,
)

REQUEST = "aiohttp.client:ClientSession._request"


def only(tape: Tape) -> Event:
    """The one event on the tape."""

    (event,) = tape.all

    return event


async def text_of_get(session: ClientSession, url: str) -> str:
    async with session.get(url) as response:
        return await response.text()


def test_a_request_records_one_external_leaf(server: Server, tape: Tape) -> None:
    body = run(lambda s: text_of_get(s, f"{server.url}/ok"))
    assert body == "ok"

    event = only(tape)
    assert event.path == REQUEST
    assert event.label is None
    assert event.category == "external"
    assert event.exception is None
    assert tape.children_of(event) == []


def test_the_event_carries_the_external_contract_keys(
    server: Server, tape: Tape
) -> None:
    run(lambda s: text_of_get(s, f"{server.url}/ok"))

    port = int(server.url.rpartition(":")[2])

    assert only(tape).data == {
        "method": "GET",
        "url": f"{server.url}/ok",
        "host": "127.0.0.1",
        "port": port,
        "path": "/ok",
        "status": 200,
    }


def test_the_arguments_are_not_captured_and_the_result_is_its_type(
    server: Server, tape: Tape
) -> None:
    # _request's signature is wide, and the method and URL it matters
    # on are already the event's contract keys, so the arguments are
    # not captured; the response reduces to its type.

    run(lambda s: text_of_get(s, f"{server.url}/ok"))

    event = only(tape)
    assert event.arguments is None
    assert event.result == "<ClientResponse>"


def test_the_query_is_recorded_apart_from_the_url_with_secrets_masked(
    server: Server, tape: Tape
) -> None:
    run(lambda s: text_of_get(s, f"{server.url}/ok?token=hunter2&page=3"))

    event = only(tape)
    assert event.data["url"] == f"{server.url}/ok"
    assert event.data["query"] == "token=<redacted>&page=3"
    assert "hunter2" not in repr(event.data)

    # The server still received the query untouched; only the record
    # is masked.

    assert server.received[0].path == "/ok?token=hunter2&page=3"


def test_redact_masks_further_query_parameters_by_name(server: Server) -> None:
    with (
        instrumentation(AiohttpClientInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        run(lambda s: text_of_get(s, f"{server.url}/ok?voucher=SAVE10&page=3"))

    assert only(tape).data["query"] == "voucher=<redacted>&page=3"


def test_a_post_records_its_method_and_never_its_body(
    server: Server, tape: Tape
) -> None:
    async def post(session: ClientSession) -> str:
        async with session.post(
            f"{server.url}/echo", data={"card": "4111111111111111"}
        ) as response:
            return await response.text()

    body = run(post)
    assert "4111111111111111" in body

    event = only(tape)
    assert event.data["method"] == "POST"
    assert event.data["status"] == 200

    # The card number, nowhere: the arguments are not captured, and
    # the body never reaches the recorded data.

    assert event.arguments is None
    assert "4111111111111111" not in repr(event.data)


def test_url_credentials_are_never_recorded(server: Server, tape: Tape) -> None:
    host = server.url.removeprefix("http://")

    run(lambda s: text_of_get(s, f"http://user:hunter2@{host}/ok"))

    event = only(tape)
    assert event.data["url"] == f"{server.url}/ok"
    assert event.data["host"] == "127.0.0.1"
    assert "hunter2" not in repr(event.data)


def test_an_error_status_is_a_status_not_an_exception(
    server: Server, tape: Tape
) -> None:
    async def fetch(session: ClientSession) -> int:
        async with session.get(f"{server.url}/missing") as response:
            return response.status

    assert run(fetch) == 404

    event = only(tape)
    assert event.data["status"] == 404
    assert event.exception is None


def test_a_server_failure_is_recorded_the_same_way(server: Server, tape: Tape) -> None:
    async def fetch(session: ClientSession) -> int:
        async with session.get(f"{server.url}/broken") as response:
            return response.status

    assert run(fetch) == 500

    assert only(tape).data["status"] == 500
    assert only(tape).exception is None


def test_a_connection_failure_records_the_error_with_no_status(tape: Tape) -> None:
    # Nothing listens on port 9 on the loopback, so aiohttp fails to
    # connect with a ClientConnectorError before any status exists.

    async def fetch(session: ClientSession) -> None:
        async with session.get("http://127.0.0.1:9/ok") as response:
            await response.read()

    with pytest.raises(ClientConnectorError):
        run(fetch)

    event = only(tape)
    assert event.data["method"] == "GET"
    assert "status" not in event.data
    assert isinstance(event.exception, ClientConnectorError)


def test_a_followed_redirect_is_one_event_named_by_the_original_url(
    server: Server, tape: Tape
) -> None:
    async def fetch(session: ClientSession) -> int:
        async with session.get(f"{server.url}/redirect") as response:
            return response.status

    # aiohttp follows redirects by default; the caller made one
    # request and the hops resolve inside the one _request call.

    assert run(fetch) == 200
    assert [seen.path for seen in server.received] == ["/redirect", "/ok"]

    event = only(tape)
    assert event.data["url"] == f"{server.url}/redirect"
    assert event.data["status"] == 200


def test_with_leaf_off_a_followed_redirect_is_still_one_event(server: Server) -> None:
    # The hops are a loop inside _request rather than nested calls, so
    # leaf off exposes nothing further from aiohttp itself.

    async def fetch(session: ClientSession) -> None:
        async with session.get(f"{server.url}/redirect") as response:
            await response.read()

    with instrumentation(AiohttpClientInstrumentation, leaf=False), timeline() as tape:
        run(fetch)

    event = only(tape)
    assert event.data["url"] == f"{server.url}/redirect"
    assert event.data["status"] == 200


def test_an_unfollowed_redirect_carries_its_own_status(
    server: Server, tape: Tape
) -> None:
    async def fetch(session: ClientSession) -> int:
        async with session.get(
            f"{server.url}/redirect", allow_redirects=False
        ) as response:
            return response.status

    assert run(fetch) == 302
    assert [seen.path for seen in server.received] == ["/redirect"]
    assert only(tape).data["status"] == 302


def test_two_requests_record_two_events(server: Server, tape: Tape) -> None:
    async def both(session: ClientSession) -> None:
        async with session.get(f"{server.url}/ok") as response:
            await response.read()
        async with session.get(f"{server.url}/missing") as response:
            await response.read()

    run(both)

    (first, second) = tape.all
    assert len(tape.roots()) == 2
    assert first.data["status"] == 200
    assert second.data["status"] == 404


def test_a_base_url_session_records_the_absolute_url(
    server: Server, tape: Tape
) -> None:
    # A session opened with a base_url is handed a relative path; the
    # recording joins it back to the absolute URL the request targets.

    async def fetch(session: ClientSession) -> None:
        async with session.get("/ok") as response:
            await response.read()

    import asyncio

    from aiohttp import ClientSession as Session

    async def main() -> None:
        async with Session(base_url=server.url) as session:
            await fetch(session)

    asyncio.run(main())

    event = only(tape)
    assert event.data["url"] == f"{server.url}/ok"
    assert event.data["path"] == "/ok"
