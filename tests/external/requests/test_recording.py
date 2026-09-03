"""What the instrumentation records: one external leaf per request
made through the session, the contract keys it carries, an error
status being a status rather than an exception, and what stays out
of capture."""

from __future__ import annotations

from typing import Any

import pytest
import requests
from wrapture import Event, Tape, instrumentation, timeline

from tests.httpserver import Server
from wrapture_instrumentation.external.requests import RequestsInstrumentation

SEND = "requests.sessions:Session.send"


def only(tape: Tape) -> Event:
    """The one event on the tape."""

    (event,) = tape.all

    return event


def arguments_of(event: Event) -> dict[str, Any]:
    """The event's captured arguments, which a call event always has."""

    assert event.arguments is not None

    return event.arguments


def test_a_request_records_one_external_leaf(server: Server, tape: Tape) -> None:
    response = requests.get(f"{server.url}/ok")
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
    requests.get(f"{server.url}/ok")

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
    requests.get(f"{server.url}/ok", timeout=5)

    event = only(tape)
    arguments = arguments_of(event)

    assert arguments["request"] == f"{server.url}/ok"

    # send's options arrive as one kwargs mapping, captured one level
    # down through the same rules: scalars pass, the rest by type.

    options = arguments["kwargs"]
    assert options["timeout"] == 5
    assert options["allow_redirects"] is True
    assert event.result == "<Response>"


def test_the_query_is_recorded_apart_from_the_url_with_secrets_masked(
    server: Server, tape: Tape
) -> None:
    requests.get(f"{server.url}/ok?token=hunter2&page=3")

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
        instrumentation(RequestsInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        requests.get(f"{server.url}/ok?voucher=SAVE10&page=3")

    assert only(tape).data["query"] == "voucher=<redacted>&page=3"


def test_a_post_records_its_method_and_never_its_body(
    server: Server, tape: Tape
) -> None:
    payload = {"name": "pat", "card": "4111111111111111"}

    response = requests.post(f"{server.url}/echo", data=payload)
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

    response = requests.get(f"http://user:hunter2@{host}/ok")
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
    response = requests.get(f"{server.url}/missing")
    assert response.status_code == 404

    event = only(tape)
    assert event.data["status"] == 404
    assert event.exception is None


def test_a_server_failure_is_recorded_the_same_way(server: Server, tape: Tape) -> None:
    assert requests.get(f"{server.url}/broken").status_code == 500

    assert only(tape).data["status"] == 500
    assert only(tape).exception is None


def test_a_connection_failure_records_the_error_with_no_status(tape: Tape) -> None:
    # Nothing listens on port 9 on the loopback; the failure is the
    # ConnectionError requests raises, before any status exists.

    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get("http://127.0.0.1:9/ok", timeout=1)

    event = only(tape)
    assert event.data["method"] == "GET"
    assert "status" not in event.data
    assert isinstance(event.exception, requests.exceptions.ConnectionError)


def test_a_redirect_is_one_leaf_named_by_the_original_url(
    server: Server, tape: Tape
) -> None:
    response = requests.get(f"{server.url}/redirect")

    assert response.url == f"{server.url}/ok"
    assert response.status_code == 200
    assert [hop.status_code for hop in response.history] == [302]

    # The server saw two requests; the caller made one, and the leaf
    # hides the nested send the redirect hop made.

    assert [seen.path for seen in server.received] == ["/redirect", "/ok"]

    event = only(tape)
    assert event.data["url"] == f"{server.url}/redirect"
    assert event.data["status"] == 200


def test_with_redirects_disabled_the_status_is_the_redirects_own(
    server: Server, tape: Tape
) -> None:
    response = requests.get(f"{server.url}/redirect", allow_redirects=False)

    assert response.status_code == 302
    assert [seen.path for seen in server.received] == ["/redirect"]
    assert only(tape).data["status"] == 302


def test_with_leaf_off_the_redirects_nested_send_shows(server: Server) -> None:
    with instrumentation(RequestsInstrumentation, leaf=False), timeline() as tape:
        requests.get(f"{server.url}/redirect")

    (outer, inner) = tape.all
    assert tape.parent_of(inner) is outer
    assert outer.data["url"] == f"{server.url}/redirect"
    assert outer.data["status"] == 200
    assert inner.data["url"] == f"{server.url}/ok"
    assert inner.data["status"] == 200


def test_a_session_records_one_event_per_request(server: Server, tape: Tape) -> None:
    with requests.Session() as session:
        session.get(f"{server.url}/ok")
        session.get(f"{server.url}/missing")

    (first, second) = tape.all
    assert len(tape.roots()) == 2
    assert first.data["status"] == 200
    assert second.data["status"] == 404


def test_a_prepared_send_through_a_session_records_the_same_way(
    server: Server, tape: Tape
) -> None:
    with requests.Session() as session:
        prepared = session.prepare_request(requests.Request("GET", f"{server.url}/ok"))
        response = session.send(prepared)

    assert response.status_code == 200

    event = only(tape)
    assert event.data["method"] == "GET"
    assert event.data["status"] == 200


def test_a_streamed_send_still_records_its_status(server: Server, tape: Tape) -> None:
    # With stream=True the event ends when the headers are in; the
    # body read afterwards is not part of it, but the status is.

    with requests.get(f"{server.url}/ok", stream=True) as response:
        assert response.raw.read() == b"ok"

    assert only(tape).data["status"] == 200
