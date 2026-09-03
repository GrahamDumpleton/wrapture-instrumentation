"""What the sync client's instrumentation records: one external leaf
per request, the contract keys it carries, an error status being a
status rather than an exception, a followed redirect resolving
inside the one event, and what stays out of capture."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from wrapture import Event, Tape, instrumentation, timeline

from tests.httpserver import Server
from wrapture_instrumentation.external.httpx import HTTPXInstrumentation

# The classes live in httpx._client, but httpx stamps the public
# package as their __module__ as it finishes importing, and the
# binding waits for that, so the derived path is the public spelling
# in every import order.

SEND = "httpx:Client.send"


def only(tape: Tape) -> Event:
    """The one event on the tape."""

    (event,) = tape.all

    return event


def arguments_of(event: Event) -> dict[str, Any]:
    """The event's captured arguments, which a call event always has."""

    assert event.arguments is not None

    return event.arguments


def test_a_request_records_one_external_leaf(server: Server, tape: Tape) -> None:
    response = httpx.get(f"{server.url}/ok")
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
    httpx.get(f"{server.url}/ok")

    port = int(server.url.rpartition(":")[2])

    assert only(tape).data == {
        "method": "GET",
        "url": f"{server.url}/ok",
        "host": "127.0.0.1",
        "port": port,
        "path": "/ok",
        "status": 200,
    }


def test_the_captured_arguments_show_the_url_and_the_result_its_type(
    server: Server, tape: Tape
) -> None:
    httpx.get(f"{server.url}/ok")

    event = only(tape)
    arguments = arguments_of(event)

    assert arguments["request"] == f"{server.url}/ok"
    assert arguments["stream"] is False
    assert event.result == "<Response>"


def test_the_query_is_recorded_apart_from_the_url_with_secrets_masked(
    server: Server, tape: Tape
) -> None:
    httpx.get(f"{server.url}/ok?token=hunter2&page=3")

    event = only(tape)
    assert event.data["url"] == f"{server.url}/ok"
    assert event.data["query"] == "token=<redacted>&page=3"
    assert arguments_of(event)["request"] == f"{server.url}/ok"
    assert "hunter2" not in repr(event.arguments)
    assert "hunter2" not in repr(event.data)

    # The server still received the query untouched; only the record
    # is masked.

    assert server.received[0].path == "/ok?token=hunter2&page=3"


def test_redact_masks_further_query_parameters_by_name(server: Server) -> None:
    with (
        instrumentation(HTTPXInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        httpx.get(f"{server.url}/ok?voucher=SAVE10&page=3")

    assert only(tape).data["query"] == "voucher=<redacted>&page=3"


def test_a_post_records_its_method_and_never_its_body(
    server: Server, tape: Tape
) -> None:
    payload = {"name": "pat", "card": "4111111111111111"}

    response = httpx.post(f"{server.url}/echo", data=payload)
    assert "4111111111111111" in response.text

    event = only(tape)
    assert event.data["method"] == "POST"
    assert event.data["status"] == 200

    # The full card number, nowhere: the request reduces to its URL,
    # and the body is never captured at all.

    assert "4111111111111111" not in repr(event.arguments)
    assert "4111111111111111" not in repr(event.data)


def test_url_credentials_are_never_recorded(server: Server, tape: Tape) -> None:
    host = server.url.removeprefix("http://")

    response = httpx.get(f"http://user:hunter2@{host}/ok")
    assert response.status_code == 200

    event = only(tape)
    assert event.data["url"] == f"{server.url}/ok"
    assert event.data["host"] == "127.0.0.1"
    assert arguments_of(event)["request"] == f"{server.url}/ok"
    assert "hunter2" not in repr(event.arguments)
    assert "hunter2" not in repr(event.data)


def test_an_error_status_is_a_status_not_an_exception(
    server: Server, tape: Tape
) -> None:
    response = httpx.get(f"{server.url}/missing")
    assert response.status_code == 404

    event = only(tape)
    assert event.data["status"] == 404
    assert event.exception is None


def test_a_server_failure_is_recorded_the_same_way(server: Server, tape: Tape) -> None:
    assert httpx.get(f"{server.url}/broken").status_code == 500

    assert only(tape).data["status"] == 500
    assert only(tape).exception is None


def test_a_connection_failure_records_the_error_with_no_status(tape: Tape) -> None:
    # Nothing listens on port 9 on the loopback. A refused connection
    # is a ConnectError and a filtered port (Windows) times out as a
    # ConnectTimeout; both are the TransportError family, recorded
    # the same way, before any status exists.

    with pytest.raises(httpx.TransportError):
        httpx.get("http://127.0.0.1:9/ok", timeout=1)

    event = only(tape)
    assert event.data["method"] == "GET"
    assert "status" not in event.data
    assert isinstance(event.exception, httpx.TransportError)


def test_an_unfollowed_redirect_carries_its_own_status(
    server: Server, tape: Tape
) -> None:
    # httpx does not follow redirects unless asked, so the caller sees
    # the 302 itself and the event carries it.

    response = httpx.get(f"{server.url}/redirect")

    assert response.status_code == 302
    assert [seen.path for seen in server.received] == ["/redirect"]
    assert only(tape).data["status"] == 302


def test_a_followed_redirect_is_one_event_named_by_the_original_url(
    server: Server, tape: Tape
) -> None:
    response = httpx.get(f"{server.url}/redirect", follow_redirects=True)

    assert response.status_code == 200
    assert [hop.status_code for hop in response.history] == [302]

    # The server saw two requests; the caller made one, and httpx
    # resolved the hop inside the one send, so there is one event
    # whatever the leaf setting says.

    assert [seen.path for seen in server.received] == ["/redirect", "/ok"]

    event = only(tape)
    assert event.data["url"] == f"{server.url}/redirect"
    assert event.data["status"] == 200


def test_with_leaf_off_a_followed_redirect_is_still_one_event(server: Server) -> None:
    # Unlike requests, the hops are a loop inside send rather than
    # nested sends, so leaf off exposes nothing further from httpx
    # itself.

    with instrumentation(HTTPXInstrumentation, leaf=False), timeline() as tape:
        httpx.get(f"{server.url}/redirect", follow_redirects=True)

    event = only(tape)
    assert event.data["url"] == f"{server.url}/redirect"
    assert event.data["status"] == 200


def test_a_client_records_one_event_per_request(server: Server, tape: Tape) -> None:
    with httpx.Client() as client:
        client.get(f"{server.url}/ok")
        client.get(f"{server.url}/missing")

    (first, second) = tape.all
    assert len(tape.roots()) == 2
    assert first.data["status"] == 200
    assert second.data["status"] == 404


def test_a_built_request_sent_directly_records_the_same_way(
    server: Server, tape: Tape
) -> None:
    with httpx.Client() as client:
        request = client.build_request("GET", f"{server.url}/ok")
        response = client.send(request)

    assert response.status_code == 200

    event = only(tape)
    assert event.data["method"] == "GET"
    assert event.data["status"] == 200


def test_a_streamed_send_still_records_its_status(server: Server, tape: Tape) -> None:
    # With stream=True the event ends when the headers are in; the
    # body read afterwards is not part of it, but the status is.

    with httpx.Client() as client, client.stream("GET", f"{server.url}/ok") as response:
        assert response.read() == b"ok"

    assert only(tape).data["status"] == 200
