"""What the instrumentation records: one request boundary per POST
with its status, the dispatched procedures beneath it, faults, the
404 for a wrong path, and what stays out of capture."""

from __future__ import annotations

import xmlrpc.client

import pytest
from wrapture import Event, Tape

from tests.server.xmlrpc_server.conftest import settled
from tests.xmlrpcserver import Server

DISPATCH = "xmlrpc.server:SimpleXMLRPCDispatcher._dispatch"


def boundary(events: list[Event]) -> Event:
    """The one request boundary among the events."""

    (event,) = [event for event in events if event.kind == "block"]

    return event


def test_a_post_records_one_boundary_with_its_dispatch(
    server: Server, instrumented: None, tape: Tape
) -> None:
    port = int(server.url.rpartition(":")[2])

    assert xmlrpc.client.ServerProxy(server.url).echo("hello") == "hello"

    events = settled(tape)
    block = boundary(events)
    assert block.label == "xmlrpc.server"
    assert block.category == "server"
    assert block.exception is None
    assert block.data == {
        "system": "xmlrpc",
        "method": "POST",
        "path": "/RPC2",
        "client": "127.0.0.1",
        "status": 200,
    }
    assert port  # the boundary says who called, not where it listens

    (dispatch,) = tape.children_of(block)
    assert dispatch.path == DISPATCH
    assert dispatch.data == {"operation": "echo"}
    assert tape.parent_of(dispatch) is block


def test_a_dotted_method_name_is_the_operation(
    server: Server, instrumented: None, tape: Tape
) -> None:
    assert xmlrpc.client.ServerProxy(server.url).inventory.count("widget", 3) == 18

    (dispatch,) = tape.children_of(boundary(settled(tape)))
    assert dispatch.data["operation"] == "inventory.count"


def test_arguments_and_results_stay_out_of_capture(
    server: Server, instrumented: None, tape: Tape
) -> None:
    xmlrpc.client.ServerProxy(server.url).echo("a-secret-value")

    (dispatch,) = tape.children_of(boundary(settled(tape)))
    assert dispatch.arguments is not None
    assert dispatch.arguments["method"] == "echo"
    assert dispatch.arguments["params"] == "<1 values>"
    assert dispatch.result == "<str>"
    assert "a-secret-value" not in repr(dispatch.arguments)
    assert "a-secret-value" not in repr(dispatch.result)


def test_a_fault_is_the_dispatch_exception_inside_a_200(
    server: Server, instrumented: None, tape: Tape
) -> None:
    # The procedure raised, the server marshalled the failure into a
    # Fault response, and the HTTP exchange itself succeeded: the
    # failure shows on the dispatch event, not the boundary.

    with pytest.raises(xmlrpc.client.Fault):
        xmlrpc.client.ServerProxy(server.url).boom()

    events = settled(tape)
    block = boundary(events)
    assert block.data["status"] == 200
    assert block.exception is None

    (dispatch,) = tape.children_of(block)
    assert dispatch.data["operation"] == "boom"
    assert isinstance(dispatch.exception, ValueError)


def test_a_wrong_path_is_a_404_boundary_with_nothing_dispatched(
    server: Server, instrumented: None, tape: Tape
) -> None:
    with pytest.raises(xmlrpc.client.ProtocolError):
        xmlrpc.client.ServerProxy(f"{server.url}/nope").echo("lost")

    events = settled(tape)
    block = boundary(events)
    assert block.data["path"] == "/nope"
    assert block.data["status"] == 404
    assert tape.children_of(block) == []


def test_a_multicall_nests_its_sub_calls(
    server: Server, instrumented: None, tape: Tape
) -> None:
    batch = xmlrpc.client.MultiCall(xmlrpc.client.ServerProxy(server.url))
    batch.echo("first")
    batch.echo("second")

    results = batch()
    assert [results[0], results[1]] == ["first", "second"]

    events = settled(tape)
    block = boundary(events)

    (batched,) = tape.children_of(block)
    assert batched.data["operation"] == "system.multicall"

    inner = tape.children_of(batched)
    assert [event.data["operation"] for event in inner] == ["echo", "echo"]

    # A sub-call's params arrive as a list from the unmarshalled XML
    # and reduce to a count like any other.

    for event in inner:
        assert event.arguments is not None
        assert event.arguments["params"] == "<1 values>"
    assert "first" not in repr(inner[0].arguments)
