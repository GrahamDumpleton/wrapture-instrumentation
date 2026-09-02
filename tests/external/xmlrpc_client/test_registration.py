"""The entry point: resolving the instrumentation by its dotted name,
and what the listing tool says about it."""

from __future__ import annotations

import platform
import xmlrpc.client

from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.xmlrpcserver import Server
from wrapture_instrumentation import __version__
from wrapture_instrumentation.external.xmlrpc_client import XMLRPCClientInstrumentation

CALL = "xmlrpc.client:ServerProxy._ServerProxy__request"


def test_the_dotted_name_resolves_to_the_class() -> None:
    with instrumentation("xmlrpc.client") as record:
        (instance,) = record.instrumentations

        assert type(instance) is XMLRPCClientInstrumentation
        assert instance.name == "xmlrpc.client"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Remote call tracing and trace propagation for xmlrpc.client."
        )


def test_a_config_entry_applies_and_reverts(server: Server) -> None:
    applied = Config(instrument=[InstrumentEntry("xmlrpc.client")]).apply()
    try:
        report = applied.report()
        assert "xmlrpc.client" in report
        assert (
            "target xmlrpc.client (standard library,"
            f" python {platform.python_version()})" in report
        )
        assert "applied xmlrpc.client" in report

        with timeline() as tape:
            assert xmlrpc.client.ServerProxy(server.url).echo("hi") == "hi"

        assert [event.path for event in tape.all] == [CALL]
    finally:
        applied.revert()

    with timeline() as tape:
        assert xmlrpc.client.ServerProxy(server.url).echo("hi") == "hi"

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"xmlrpc.client  ({DISTRIBUTION} {__version__})" in output
    assert "  Remote call tracing and trace propagation for xmlrpc.client." in output
    assert (
        "  target: xmlrpc.client (standard library,"
        f" python {platform.python_version()}), supported (>=3.12)" in output
    )
    assert "  modules: xmlrpc.client" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    leaf = true " in output
    assert (
        "record each remote call as a terminal node, so the transport work"
        " beneath it (including its silent reconnect retry) stays out of"
        " the tree" in output
    )
    assert "    propagate = true " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "xmlrpc.client"\nenabled = false' in output
    assert "# leaf = true" in output
    assert "# propagate = true" in output
