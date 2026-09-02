"""The entry point: resolving the instrumentation by its dotted name,
and what the listing tool says about it."""

from __future__ import annotations

import platform
import xmlrpc.client

from wrapture import (
    Config,
    InstrumentEntry,
    Tape,
    add_sink,
    instrumentation,
    remove_sink,
)

from tests.conftest import DISTRIBUTION, run_tool
from tests.server.xmlrpc_server.conftest import settled
from tests.xmlrpcserver import Server
from wrapture_instrumentation import __version__
from wrapture_instrumentation.server.xmlrpc_server import XMLRPCServerInstrumentation


def test_the_dotted_name_resolves_to_the_class() -> None:
    with instrumentation("xmlrpc.server") as record:
        (instance,) = record.instrumentations

        assert type(instance) is XMLRPCServerInstrumentation
        assert instance.name == "xmlrpc.server"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Request and dispatch tracing for xmlrpc.server."
        )


def test_a_config_entry_applies_and_reverts(server: Server) -> None:
    applied = Config(instrument=[InstrumentEntry("xmlrpc.server")]).apply()
    try:
        report = applied.report()
        assert "xmlrpc.server" in report
        assert (
            "target xmlrpc.server (standard library,"
            f" python {platform.python_version()})" in report
        )
        assert "applied xmlrpc.server" in report

        tape = Tape()
        add_sink(tape)
        try:
            assert xmlrpc.client.ServerProxy(server.url).echo("hi") == "hi"
            events = settled(tape)
        finally:
            remove_sink(tape)

        assert [event.kind for event in events] == ["block", "call"]
    finally:
        applied.revert()

    tape = Tape()
    add_sink(tape)
    try:
        assert xmlrpc.client.ServerProxy(server.url).echo("hi") == "hi"
    finally:
        remove_sink(tape)

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"xmlrpc.server  ({DISTRIBUTION} {__version__})" in output
    assert "  Request and dispatch tracing for xmlrpc.server." in output
    assert (
        "  target: xmlrpc.server (standard library,"
        f" python {platform.python_version()}), supported (>=3.12)" in output
    )
    assert "  modules: xmlrpc.server" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    join = true " in output
    assert (
        "join the distributed trace an arriving request's traceparent"
        " header carries, rather than minting a fresh identity per"
        " request" in output
    )


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "xmlrpc.server"\nenabled = false' in output
    assert "# join = true" in output
