"""What the instrumentation records: one external leaf per request
made through the opener, the contract keys it carries, the status
however it arrives, and what stays out of capture."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from wrapture import Event, Tape, instrumentation, timeline

from tests.external_urllib_request.server import Server
from wrapture_instrumentation.external_urllib_request import UrllibInstrumentation

OPEN = "urllib.request:OpenerDirector.open"


def only(tape: Tape) -> Event:
    """The one event on the tape."""

    (event,) = tape.all

    return event


def arguments_of(event: Event) -> dict[str, Any]:
    """The event's captured arguments, which a call event always has."""

    assert event.arguments is not None

    return event.arguments


def test_a_request_records_one_external_leaf(server: Server, tape: Tape) -> None:
    with urllib.request.urlopen(f"{server.url}/ok") as response:
        assert response.read() == b"ok"

    event = only(tape)
    assert event.path == OPEN
    assert event.label is None
    assert event.category == "external"
    assert event.exception is None
    assert tape.children_of(event) == []


def test_the_event_carries_the_external_contract_keys(
    server: Server, tape: Tape
) -> None:
    urllib.request.urlopen(f"{server.url}/ok").close()

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
    urllib.request.urlopen(f"{server.url}/ok", timeout=5).close()

    event = only(tape)
    assert event.arguments == {
        "fullurl": f"{server.url}/ok",
        "data": None,
        "timeout": 5,
    }
    assert event.result == "<HTTPResponse>"


def test_the_default_timeout_is_not_captured_as_an_object(
    server: Server, tape: Tape
) -> None:
    urllib.request.urlopen(f"{server.url}/ok").close()

    assert arguments_of(only(tape))["timeout"] == "<default>"


def test_the_query_is_recorded_apart_from_the_url_with_secrets_masked(
    server: Server, tape: Tape
) -> None:
    urllib.request.urlopen(f"{server.url}/ok?token=hunter2&page=3").close()

    event = only(tape)
    assert event.data["url"] == f"{server.url}/ok"
    assert event.data["query"] == "token=<redacted>&page=3"
    assert arguments_of(event)["fullurl"] == f"{server.url}/ok"
    assert "hunter2" not in repr(event.arguments)
    assert "hunter2" not in repr(event.data)

    # The server still received the query untouched; only the record
    # is masked.

    assert server.received[0].path == "/ok?token=hunter2&page=3"


def test_redact_masks_further_query_parameters_by_name(server: Server) -> None:
    with (
        instrumentation(UrllibInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        urllib.request.urlopen(f"{server.url}/ok?voucher=SAVE10&page=3").close()

    assert only(tape).data["query"] == "voucher=<redacted>&page=3"


def test_a_post_records_its_method_and_the_body_by_size(
    server: Server, tape: Tape
) -> None:
    body = b"name=pat&card=4111111111111111"

    with urllib.request.urlopen(f"{server.url}/echo", data=body) as response:
        assert response.read() == body

    event = only(tape)
    assert event.data["method"] == "POST"
    assert event.data["status"] == 200
    assert arguments_of(event)["data"] == f"<{len(body)} bytes>"
    assert "4111" not in repr(event.arguments)


def test_a_request_object_supplies_its_own_method(server: Server, tape: Tape) -> None:
    request = urllib.request.Request(
        f"{server.url}/echo", data=b"x", method="PUT", headers={"X-Own": "yes"}
    )
    urllib.request.urlopen(request).close()

    event = only(tape)
    assert event.data["method"] == "PUT"
    assert arguments_of(event)["fullurl"] == f"{server.url}/echo"

    # The application's own headers travel as they were.

    assert server.header(0, "X-Own") == "yes"


def test_an_error_status_is_the_raised_error_and_the_status(
    server: Server, tape: Tape
) -> None:
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(f"{server.url}/missing")

    assert caught.value.code == 404

    event = only(tape)
    assert event.data["status"] == 404
    assert event.exception is caught.value


def test_a_server_failure_is_recorded_the_same_way(server: Server, tape: Tape) -> None:
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"{server.url}/broken")

    assert only(tape).data["status"] == 500
    assert only(tape).exception is not None


def test_a_connection_failure_records_the_error_with_no_status(
    tape: Tape,
) -> None:
    # Nothing listens on port 9 on the loopback; the failure is the
    # opener's own URLError, before any status exists.

    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen("http://127.0.0.1:9/ok", timeout=1)

    event = only(tape)
    assert event.data["method"] == "GET"
    assert "status" not in event.data
    assert isinstance(event.exception, urllib.error.URLError)


def test_a_redirect_is_one_leaf_named_by_the_original_url(
    server: Server, tape: Tape
) -> None:
    with urllib.request.urlopen(f"{server.url}/redirect") as response:
        assert response.url == f"{server.url}/ok"
        assert response.status == 200

    # The server saw two requests; the caller made one open, and the
    # leaf hides the nested open the redirect handler made.

    assert [seen.path for seen in server.received] == ["/redirect", "/ok"]

    event = only(tape)
    assert event.data["url"] == f"{server.url}/redirect"
    assert event.data["status"] == 200


def test_with_leaf_off_the_redirects_nested_open_shows(server: Server) -> None:
    with instrumentation(UrllibInstrumentation, leaf=False), timeline() as tape:
        urllib.request.urlopen(f"{server.url}/redirect").close()

    (outer, inner) = tape.all
    assert tape.parent_of(inner) is outer
    assert outer.data["url"] == f"{server.url}/redirect"
    assert inner.data["url"] == f"{server.url}/ok"
    assert inner.data["status"] == 200


def test_a_custom_opener_goes_through_the_same_binding(
    server: Server, tape: Tape
) -> None:
    opener = urllib.request.build_opener()
    opener.open(f"{server.url}/ok").close()

    assert only(tape).data["url"] == f"{server.url}/ok"


def test_a_file_url_records_without_host_or_status(tmp_path: Path, tape: Tape) -> None:
    target = tmp_path / "note.txt"
    target.write_text("hello")

    with urllib.request.urlopen(target.as_uri()) as response:
        assert response.read() == b"hello"

    event = only(tape)
    assert event.category == "external"
    assert event.data["method"] == "GET"
    assert event.data["url"] == target.as_uri()
    assert "host" not in event.data
    assert "status" not in event.data
