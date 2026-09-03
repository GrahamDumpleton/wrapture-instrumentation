"""Applying and removing: the patched factories per settings, and
removal leaving them as they were, with channels and servers built
while instrumented going quiet rather than breaking."""

from __future__ import annotations

import pytest

grpc = pytest.importorskip("grpc")

from wrapture import Tape, instrumentation

from tests.rpc.grpc.service import serve
from wrapture_instrumentation.rpc.grpc import GRPCInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "insecure_channel": grpc.insecure_channel,
        "secure_channel": grpc.secure_channel,
        "server": grpc.server,
    }


@pytest.mark.parametrize(
    ("client", "server", "patched"),
    [
        (True, True, {"insecure_channel", "secure_channel", "server"}),
        (False, True, {"server"}),
        (True, False, {"insecure_channel", "secure_channel"}),
    ],
)
def test_the_settings_decide_what_is_patched(
    client: bool, server: bool, patched: set[str]
) -> None:
    before = choke_points()

    with instrumentation(GRPCInstrumentation, client=client, server=server):
        current = choke_points()

        for name in before:
            if name in patched:
                assert current[name] is not before[name], name
            else:
                assert current[name] is before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name


def test_after_removal_live_objects_go_quiet(tape: Tape) -> None:
    # A channel and a server built while instrumented keep their
    # interceptor objects; removal flips those to passing everything
    # through untouched, so they work and record nothing.

    with instrumentation(GRPCInstrumentation):
        serving = serve()
        service = next(serving)
        channel = grpc.insecure_channel(service.address)

    try:
        assert channel.unary_unary("/demo.Echo/Shout")(b"hi") == b"HI"

        assert tape.all == []
        assert service.header(0, "traceparent") is None
    finally:
        channel.close()
        next(serving, None)
