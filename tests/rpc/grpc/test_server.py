"""What the server side records: one request boundary per handled
RPC spanning the handler's run, the code it ended with, the join
into the caller's trace, and aborts as control flow."""

from __future__ import annotations

import pytest

grpc = pytest.importorskip("grpc")

from wrapture import Event, Tape, instrumentation

from tests.rpc.grpc.conftest import settled
from tests.rpc.grpc.service import Service, serve
from wrapture_instrumentation.rpc.grpc import GRPCInstrumentation


def boundary(events: list[Event]) -> Event:
    (event,) = [event for event in events if event.kind == "block"]

    return event


def trace_id(event: Event) -> str | None:
    slot = event.trace.slots.get("w3c") if event.trace else None

    return slot.trace_id if slot else None


def test_a_handled_rpc_records_one_boundary(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        channel.unary_unary("/demo.Echo/Shout")(b"hi")

    block = boundary(settled(tape))
    assert block.label == "grpc"
    assert block.category == "server"
    assert block.exception is None
    assert block.data == {
        "system": "grpc",
        "service": "demo.Echo",
        "operation": "Shout",
        "client": "127.0.0.1",
        "code": "OK",
    }


def test_the_boundary_joins_the_callers_trace(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        channel.unary_unary("/demo.Echo/Shout")(b"hi")

    events = settled(tape)
    (call,) = [e for e in events if e.label == "grpc:Channel.unary_unary"]
    block = boundary(events)

    assert trace_id(call) is not None
    assert trace_id(block) == trace_id(call)


def test_an_abort_is_its_code_and_the_boundary_stays_clean(
    service: Service, tape: Tape
) -> None:
    with grpc.insecure_channel(service.address) as channel:
        with pytest.raises(grpc.RpcError):
            channel.unary_unary("/demo.Echo/Fail")(b"hi")

    block = boundary(settled(tape))
    assert block.data["code"] == "NOT_FOUND"
    assert block.exception is None


def test_an_escaped_exception_is_the_failure_it_is(
    service: Service, tape: Tape
) -> None:
    with grpc.insecure_channel(service.address) as channel:
        with pytest.raises(grpc.RpcError):
            channel.unary_unary("/demo.Echo/Boom")(b"hi")

    block = boundary(settled(tape))
    assert block.data["code"] == "UNKNOWN"
    assert isinstance(block.exception, RuntimeError)


def test_a_streaming_handler_spans_its_whole_body(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        chunks = list(channel.unary_stream("/demo.Echo/Count")(b"x"))

    assert len(chunks) == 3

    block = boundary(settled(tape))
    assert block.data["operation"] == "Count"
    assert block.data["code"] == "OK"


def test_a_streamed_request_records_its_boundary(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        assert channel.stream_unary("/demo.Echo/Sum")(iter([b"2", b"3"])) == b"5"

    block = boundary(settled(tape))
    assert block.data["operation"] == "Sum"
    assert block.data["code"] == "OK"


def test_join_off_roots_a_trace_of_its_own(tape: Tape) -> None:
    with instrumentation(GRPCInstrumentation, join=False):
        serving = serve()
        service = next(serving)
        try:
            with grpc.insecure_channel(service.address) as channel:
                channel.unary_unary("/demo.Echo/Shout")(b"hi")

            events = settled(tape)
            (call,) = [e for e in events if e.label == "grpc:Channel.unary_unary"]
            block = boundary(events)

            assert trace_id(block) is not None
            assert trace_id(block) != trace_id(call)
        finally:
            next(serving, None)
