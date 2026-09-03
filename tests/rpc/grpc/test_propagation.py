"""Trace propagation in the call metadata: the identity added to
each RPC, a key the application set left alone, the setting to turn
it off, and metadata values never reaching the record."""

from __future__ import annotations

import pytest

grpc = pytest.importorskip("grpc")

import wrapture
from wrapture import Tape, instrumentation

from tests.rpc.grpc.service import Service, serve
from wrapture_instrumentation.rpc.grpc import GRPCInstrumentation

CLAIMED = "00-11111111111111111111111111111111-2222222222222222-01"


def test_the_trace_identity_rides_in_the_metadata(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        channel.unary_unary("/demo.Echo/Shout")(b"hi")

    carried = service.header(0, "traceparent")
    assert carried is not None
    assert carried.startswith("00-")


def test_a_traceparent_the_application_set_is_left_alone(
    service: Service, tape: Tape
) -> None:
    with grpc.insecure_channel(service.address) as channel:
        channel.unary_unary("/demo.Echo/Shout")(
            b"hi", metadata=(("traceparent", CLAIMED),)
        )

    assert service.header(0, "traceparent") == CLAIMED


def test_propagate_off_sends_nothing(tape: Tape) -> None:
    with instrumentation(GRPCInstrumentation, propagate=False):
        serving = serve()
        service = next(serving)
        try:
            with grpc.insecure_channel(service.address) as channel:
                channel.unary_unary("/demo.Echo/Shout")(b"hi")

            assert service.header(0, "traceparent") is None
        finally:
            next(serving, None)


def test_metadata_values_never_reach_the_record(service: Service, tape: Tape) -> None:
    with grpc.insecure_channel(service.address) as channel:
        channel.unary_unary("/demo.Echo/Shout")(
            b"hi", metadata=(("x-api-key", "a-secret-value"),)
        )

    assert service.header(0, "x-api-key") == "a-secret-value"

    for event in tape.all:
        assert "a-secret-value" not in repr(event.data)
        assert "a-secret-value" not in repr(event.arguments)


def test_no_identity_is_sent_beneath_a_foreign_leaf(
    service: Service, tape: Tape
) -> None:
    # Propagation follows recording: silenced beneath another
    # target's leaf, the client injects nothing and leaves the leaf's
    # event alone, so a leaf that does not propagate at its own level
    # sends no identity downstream.

    @wrapture.observed(leaf=True)
    def vendor_call() -> None:
        with grpc.insecure_channel(service.address) as channel:
            channel.unary_unary("/demo.Echo/Shout")(b"hi")

    vendor_call()

    # The instrumented server side still records its own boundary (it
    # is not beneath the client's leaf); the client side is the leaf
    # alone, with nothing recorded or smeared.

    (leaf,) = [event for event in tape.all if event.kind == "call"]
    assert tape.children_of(leaf) == []
    assert "system" not in leaf.data
    assert service.header(0, "traceparent") is None
