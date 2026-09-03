"""What the client side records: one external leaf per RPC in every
call shape, error codes as statuses rather than exceptions, and what
stays out of capture."""

from __future__ import annotations

import pytest

grpc = pytest.importorskip("grpc")

from wrapture import Event, Tape

from tests.rpc.grpc.conftest import settled
from tests.rpc.grpc.service import Service


def labelled(tape: Tape, label: str) -> list[Event]:
    return [event for event in tape.all if event.label == label]


def test_a_unary_call_records_an_external_leaf(service: Service, tape: Tape) -> None:
    port = int(service.address.rpartition(":")[2])

    with grpc.insecure_channel(service.address) as channel:
        assert channel.unary_unary("/demo.Echo/Shout")(b"hi") == b"HI"

    (event,) = labelled(tape, "grpc:Channel.unary_unary")
    assert event.category == "external"
    assert event.data == {
        "system": "grpc",
        "service": "demo.Echo",
        "operation": "Shout",
        "host": "127.0.0.1",
        "port": port,
        "code": "OK",
    }
    assert tape.children_of(event) == []

    # Payloads and metadata never reach the record.

    assert event.arguments is None


def test_an_error_code_is_a_status_not_an_exception(
    service: Service, tape: Tape
) -> None:
    with grpc.insecure_channel(service.address) as channel:
        with pytest.raises(grpc.RpcError):
            channel.unary_unary("/demo.Echo/Fail")(b"hi")

    (event,) = labelled(tape, "grpc:Channel.unary_unary")
    assert event.data["code"] == "NOT_FOUND"
    assert event.exception is None


def test_a_server_side_failure_is_its_unknown_code(
    service: Service, tape: Tape
) -> None:
    with grpc.insecure_channel(service.address) as channel:
        with pytest.raises(grpc.RpcError):
            channel.unary_unary("/demo.Echo/Boom")(b"hi")

    (event,) = labelled(tape, "grpc:Channel.unary_unary")
    assert event.data["code"] == "UNKNOWN"
    assert event.exception is None


def test_a_call_nobody_serves_is_unimplemented(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        with pytest.raises(grpc.RpcError):
            channel.unary_unary("/demo.Echo/Missing")(b"hi")

    (event,) = labelled(tape, "grpc:Channel.unary_unary")
    assert event.data["code"] == "UNIMPLEMENTED"

    # No handler existed to wrap, so no server boundary records.

    assert [event for event in tape.all if event.kind == "block"] == []


def test_with_call_records_like_the_plain_call(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        response, call = channel.unary_unary("/demo.Echo/Shout").with_call(b"hi")

    assert response == b"HI"
    assert call.code() == grpc.StatusCode.OK

    (event,) = labelled(tape, "grpc:Channel.unary_unary")
    assert event.data["code"] == "OK"


def test_a_future_call_records_the_call_being_made(
    service: Service, tape: Tape
) -> None:
    with grpc.insecure_channel(service.address) as channel:
        future = channel.unary_unary("/demo.Echo/Shout").future(b"hi")
        assert future.result() == b"HI"

    # The RPC was still in flight when the call returned, so its
    # event covers the call being made and carries no code.

    (event,) = labelled(tape, "grpc:Channel.unary_unary")
    assert "code" not in event.data
    assert event.data["operation"] == "Shout"


def test_a_streamed_response_records_the_call_not_the_consumption(
    service: Service, tape: Tape
) -> None:
    with grpc.insecure_channel(service.address) as channel:
        chunks = list(channel.unary_stream("/demo.Echo/Count")(b"x"))

    assert chunks == [b"x-0", b"x-1", b"x-2"]

    # The database model: the event is the call, iteration is the
    # application's business and is not tracked, so no code rides.

    (event,) = labelled(tape, "grpc:Channel.unary_stream")
    assert event.data["operation"] == "Count"
    assert "code" not in event.data


def test_a_streamed_request_records_with_its_code(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        total = channel.stream_unary("/demo.Echo/Sum")(iter([b"1", b"2", b"3"]))

    assert total == b"6"

    (event,) = labelled(tape, "grpc:Channel.stream_unary")
    assert event.data["operation"] == "Sum"
    assert event.data["code"] == "OK"


def test_a_bidirectional_stream_records_the_call(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        replies = list(channel.stream_stream("/demo.Echo/Chat")(iter([b"a", b"b"])))

    assert replies == [b"A", b"B"]

    (event,) = labelled(tape, "grpc:Channel.stream_stream")
    assert event.data["operation"] == "Chat"
    assert "code" not in event.data


def test_the_client_leaf_hides_the_server_boundary_beneath_it(
    service: Service, tape: Tape
) -> None:
    # In one process the server's boundary is real work beneath the
    # client's leaf on another thread, in its own trace unless joined;
    # the client event itself stays childless.

    with grpc.insecure_channel(service.address) as channel:
        channel.unary_unary("/demo.Echo/Shout")(b"hi")

    events = settled(tape)
    (event,) = [e for e in events if e.label == "grpc:Channel.unary_unary"]
    assert tape.children_of(event) == []
