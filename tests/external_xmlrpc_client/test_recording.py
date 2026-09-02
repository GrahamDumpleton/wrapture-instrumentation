"""What the instrumentation records: one external leaf per remote
call, the contract keys and operation it carries, faults and protocol
errors, and what stays out of capture."""

from __future__ import annotations

import xmlrpc.client

import pytest
from wrapture import Event, Tape, instrumentation, timeline

from tests.external_xmlrpc_client.server import Server
from wrapture_instrumentation.external_xmlrpc_client import XMLRPCClientInstrumentation

CALL = "xmlrpc.client:ServerProxy._ServerProxy__request"
TRANSPORT = "xmlrpc.client:Transport.request"


def only(tape: Tape) -> Event:
    """The one event on the tape."""

    (event,) = tape.all

    return event


def test_a_call_records_one_external_leaf(server: Server, tape: Tape) -> None:
    proxy = xmlrpc.client.ServerProxy(server.url)

    assert proxy.echo("hello") == "hello"

    event = only(tape)
    assert event.path == CALL
    assert event.label is None
    assert event.category == "external"
    assert event.exception is None
    assert tape.children_of(event) == []


def test_the_event_carries_the_contract_keys_and_the_operation(
    server: Server, tape: Tape
) -> None:
    port = int(server.url.rpartition(":")[2])

    xmlrpc.client.ServerProxy(server.url).inventory.count("widget", 3)

    assert only(tape).data == {
        "operation": "inventory.count",
        "method": "POST",
        "url": f"{server.url}/RPC2",
        "path": "/RPC2",
        "host": "127.0.0.1",
        "port": port,
        "status": 200,
    }


def test_arguments_and_results_stay_out_of_capture(server: Server, tape: Tape) -> None:
    xmlrpc.client.ServerProxy(server.url).echo("a-secret-value")

    event = only(tape)
    assert event.arguments is not None
    assert event.arguments["methodname"] == "echo"
    assert event.arguments["params"] == "<1 values>"
    assert event.result == "<str>"
    assert "a-secret-value" not in repr(event.arguments)
    assert "a-secret-value" not in repr(event.result)


def test_a_fault_is_the_raised_error_with_status_200(
    server: Server, tape: Tape
) -> None:
    # A Fault came back in a parsed 200 response: the HTTP exchange
    # succeeded and the failure is the application's.

    with pytest.raises(xmlrpc.client.Fault) as caught:
        xmlrpc.client.ServerProxy(server.url).boom()

    event = only(tape)
    assert event.data["operation"] == "boom"
    assert event.data["status"] == 200
    assert event.exception is caught.value


def test_a_protocol_error_carries_its_status(server: Server, tape: Tape) -> None:
    with pytest.raises(xmlrpc.client.ProtocolError) as caught:
        xmlrpc.client.ServerProxy(f"{server.url}/nope").echo("lost")

    assert caught.value.errcode == 404

    event = only(tape)
    assert event.data["path"] == "/nope"
    assert event.data["status"] == 404
    assert event.exception is caught.value


def test_a_refused_connection_records_no_status(tape: Tape) -> None:
    with pytest.raises(OSError):
        xmlrpc.client.ServerProxy("http://127.0.0.1:9/RPC2").echo("lost")

    event = only(tape)
    assert event.data["operation"] == "echo"
    assert "status" not in event.data


def test_a_multicall_is_one_call(server: Server, tape: Tape) -> None:
    batch = xmlrpc.client.MultiCall(xmlrpc.client.ServerProxy(server.url))
    batch.echo("first")
    batch.echo("second")

    # MultiCallIterator only supports indexing, in typeshed as at
    # runtime, so the results are read out by position.

    results = batch()
    assert [results[0], results[1]] == ["first", "second"]

    assert only(tape).data["operation"] == "system.multicall"


def test_userinfo_credentials_never_reach_the_record(
    server: Server, tape: Tape
) -> None:
    # Basic auth travels in the URI's netloc; the recorded host and
    # url are stripped of it.

    authority = server.url.removeprefix("http://")
    proxy = xmlrpc.client.ServerProxy(f"http://user:hunter2@{authority}")

    proxy.echo("hello")

    event = only(tape)
    assert event.data["host"] == "127.0.0.1"
    assert event.data["url"] == f"{server.url}/RPC2"
    assert "hunter2" not in repr(event.data)
    assert "hunter2" not in repr(event.arguments)


def test_leaf_off_shows_the_transport_beneath_the_call(server: Server) -> None:
    with (
        instrumentation(XMLRPCClientInstrumentation, leaf=False),
        timeline() as tape,
    ):
        xmlrpc.client.ServerProxy(server.url).echo("hello")

    (call, transport) = tape.all
    assert call.path == CALL
    assert transport.path == TRANSPORT
    assert tape.parent_of(transport) is call

    # The transport's own capture: the body by size, nothing readable.

    assert transport.arguments is not None
    assert transport.arguments["request_body"].startswith("<")
    assert "echo" not in repr(transport.arguments)


def test_https_would_be_reported_as_such() -> None:
    # No TLS server here; the scheme is derived from the transport
    # class, which is what a real https proxy carries.

    from wrapture_instrumentation.external_xmlrpc_client.client import describe

    proxy = xmlrpc.client.ServerProxy(
        "https://rpc.example.test/endpoint", transport=xmlrpc.client.SafeTransport()
    )

    data = describe(xmlrpc.client, proxy, "echo")
    assert data["url"] == "https://rpc.example.test/endpoint"
    assert data["port"] == 443
