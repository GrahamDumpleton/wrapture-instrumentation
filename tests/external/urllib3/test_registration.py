"""The entry point: resolving the instrumentation by its name, and
what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

import urllib3
from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.httpserver import Server
from wrapture_instrumentation import __version__
from wrapture_instrumentation.external.urllib3 import Urllib3Instrumentation


def test_the_name_resolves_to_the_class() -> None:
    with instrumentation("urllib3") as record:
        (instance,) = record.instrumentations

        assert type(instance) is Urllib3Instrumentation
        assert instance.name == "urllib3"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Outbound request tracing and trace propagation for urllib3."
        )


def test_a_config_entry_applies_and_reverts(server: Server) -> None:
    applied = Config(instrument=[InstrumentEntry("urllib3")]).apply()
    try:
        report = applied.report()
        assert "urllib3" in report
        assert f"target urllib3 {metadata.version('urllib3')}" in report
        assert "applied urllib3.poolmanager, urllib3.connectionpool" in report

        with timeline() as tape:
            with urllib3.PoolManager() as manager:
                manager.request("GET", f"{server.url}/ok")

        assert [event.path for event in tape.all] == [
            "urllib3.poolmanager:PoolManager.urlopen"
        ]
    finally:
        applied.revert()

    with timeline() as tape:
        with urllib3.PoolManager() as manager:
            manager.request("GET", f"{server.url}/ok")

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"urllib3  ({DISTRIBUTION} {__version__})" in output
    assert "  Outbound request tracing and trace propagation for urllib3." in output
    assert (
        f"  target: urllib3 {metadata.version('urllib3')}, supported (>=1.26,<3)"
        in output
    )
    assert "  modules: urllib3.poolmanager, urllib3.connectionpool" in output

    assert "    leaf = true " in output
    assert "    propagate = true " in output
    assert "    redact = []" in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "urllib3"\nenabled = false' in output
    assert "# leaf = true" in output
    assert "# propagate = true" in output
    assert "# redact = []" in output
