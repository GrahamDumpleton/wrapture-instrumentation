"""What the instrumentation records: the phases of an exchange, cold
against warm connections, the status, and what stays out of capture."""

from __future__ import annotations

import http.client

from wrapture import Event, Tape, instrumentation, timeline

from tests.external.http_client.conftest import host_of
from tests.httpserver import Server
from wrapture_instrumentation.external.http_client import HTTPClientInstrumentation

CONNECT = "http.client:HTTPConnection.connect"
PUTREQUEST = "http.client:HTTPConnection.putrequest"
ENDHEADERS = "http.client:HTTPConnection.endheaders"
GETRESPONSE = "http.client:HTTPConnection.getresponse"


def exchange(
    server: Server, method: str, path: str, body: bytes | None = None
) -> bytes:
    """One request on a fresh connection, the response body back."""

    connection = http.client.HTTPConnection(host_of(server))
    try:
        connection.request(method, path, body=body)
        response = connection.getresponse()
        return response.read()
    finally:
        connection.close()


def of_path(tape: Tape, path: str) -> Event:
    """The one event on the tape with the given path."""

    (event,) = [event for event in tape.all if event.path == path]

    return event


def test_a_cold_exchange_records_its_phases_with_connect_nested(
    server: Server, tape: Tape
) -> None:
    assert exchange(server, "GET", "/ok") == b"ok"

    assert [event.path for event in tape.all] == [
        PUTREQUEST,
        ENDHEADERS,
        CONNECT,
        GETRESPONSE,
    ]

    # The socket is established by the first phase that writes to it,
    # so connect records inside endheaders; the phases themselves are
    # roots here, with nothing above to hold them.

    connect = of_path(tape, CONNECT)
    assert tape.parent_of(connect) is of_path(tape, ENDHEADERS)
    assert tape.parent_of(of_path(tape, PUTREQUEST)) is None

    port = int(server.url.rpartition(":")[2])
    assert connect.data == {"host": "127.0.0.1", "port": port}


def test_a_kept_alive_connection_connects_once(server: Server, tape: Tape) -> None:
    connection = http.client.HTTPConnection(host_of(server))
    try:
        for _ in range(2):
            connection.request("GET", "/ok")
            assert connection.getresponse().read() == b"ok"
    finally:
        connection.close()

    paths = [event.path for event in tape.all]
    assert paths.count(GETRESPONSE) == 2
    assert paths.count(CONNECT) == 1


def test_getresponse_carries_the_status(server: Server, tape: Tape) -> None:
    # http.client raises nothing for an error status; the status is
    # data on the wait that brought it back.

    exchange(server, "GET", "/missing")

    event = of_path(tape, GETRESPONSE)
    assert event.data == {"status": 404}
    assert event.result == "<HTTPResponse>"
    assert event.exception is None


def test_the_query_string_is_recorded_masked(server: Server, tape: Tape) -> None:
    exchange(server, "GET", "/ok?token=hunter2&page=3")

    event = of_path(tape, PUTREQUEST)
    assert event.arguments is not None
    assert event.arguments["url"] == "/ok?token=<redacted>&page=3"
    assert "hunter2" not in repr(event.arguments)

    # The server received the query untouched; only the record is
    # masked.

    assert server.received[0].path == "/ok?token=hunter2&page=3"


def test_redact_masks_further_query_parameters_by_name(server: Server) -> None:
    with (
        instrumentation(HTTPClientInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        exchange(server, "GET", "/ok?voucher=SAVE10&page=3")

    event = of_path(tape, PUTREQUEST)
    assert event.arguments is not None
    assert event.arguments["url"] == "/ok?voucher=<redacted>&page=3"


def test_a_body_is_recorded_by_size(server: Server, tape: Tape) -> None:
    body = b"name=pat&card=4111111111111111"

    assert exchange(server, "POST", "/echo", body) == body

    event = of_path(tape, ENDHEADERS)
    assert event.arguments is not None
    assert event.arguments["message_body"] == f"<{len(body)} bytes>"
    assert "4111" not in repr(event.arguments)


def test_a_urllib3_style_subclass_is_seen_through(server: Server, tape: Tape) -> None:
    # urllib3 overrides request() and drives the phase methods itself;
    # the base class bindings still see every phase.

    class Overriding(http.client.HTTPConnection):
        def request(  # type: ignore[override]
            self,
            method: str,
            url: str,
            body: bytes | None = None,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.putrequest(method, url)
            for name, value in (headers or {}).items():
                self.putheader(name, value)
            self.endheaders(body)

    connection = Overriding(host_of(server))
    try:
        connection.request("GET", "/ok")
        assert connection.getresponse().read() == b"ok"
    finally:
        connection.close()

    assert [event.path for event in tape.all] == [
        PUTREQUEST,
        ENDHEADERS,
        CONNECT,
        GETRESPONSE,
    ]
