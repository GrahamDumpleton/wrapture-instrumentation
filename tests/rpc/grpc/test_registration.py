"""The entry point: resolving the instrumentation by its name, and
what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

import pytest

grpc = pytest.importorskip("grpc")

from wrapture import (
    Config,
    InstrumentEntry,
    Tape,
    add_sink,
    instrumentation,
    remove_sink,
)

from tests.conftest import DISTRIBUTION, run_tool
from wrapture_instrumentation import __version__
from wrapture_instrumentation.rpc.grpc import GRPCInstrumentation


def test_the_name_resolves_to_the_class() -> None:
    with instrumentation("grpc") as record:
        (instance,) = record.instrumentations

        assert type(instance) is GRPCInstrumentation
        assert instance.name == "grpc"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Call and handler tracing for gRPC clients and servers."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("grpc")]).apply()
    try:
        report = applied.report()
        assert "grpc" in report
        assert f"target grpc {metadata.version('grpcio')}" in report
        assert "applied grpc" in report

        # A call to a dead port still records the leaf, its failure
        # a status: no server is needed to prove the patch is live.

        tape = Tape()
        add_sink(tape)
        try:
            with grpc.insecure_channel("127.0.0.1:1") as channel:
                with pytest.raises(grpc.RpcError):
                    channel.unary_unary("/demo.Echo/Shout")(b"hi", timeout=0.5)
        finally:
            remove_sink(tape)

        (event,) = [e for e in tape.all if e.label == "grpc:Channel.unary_unary"]
        assert event.data["code"] == "UNAVAILABLE"
    finally:
        applied.revert()

    tape = Tape()
    add_sink(tape)
    try:
        with grpc.insecure_channel("127.0.0.1:1") as channel:
            with pytest.raises(grpc.RpcError):
                channel.unary_unary("/demo.Echo/Shout")(b"hi", timeout=0.5)
    finally:
        remove_sink(tape)

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"grpc  ({DISTRIBUTION} {__version__})" in output
    assert "  Call and handler tracing for gRPC clients and servers." in output
    assert (
        f"  target: grpc {metadata.version('grpcio')}, supported (>=1.76,<2)" in output
    )
    assert "  modules: grpc\n" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    client = true " in output
    assert "record every RPC made through a channel as an external leaf" in output
    assert "    server = true " in output
    assert "record every RPC the server handles as a request boundary" in output
    assert "    propagate = true " in output
    assert "    join = true " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "grpc"\nenabled = false' in output
    assert "# client = true" in output
    assert "# server = true" in output
    assert "# propagate = true" in output
    assert "# join = true" in output
