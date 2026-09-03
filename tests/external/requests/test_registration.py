"""The entry point: resolving the instrumentation by its bare name,
and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

import requests
from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.httpserver import Server
from wrapture_instrumentation import __version__
from wrapture_instrumentation.external.requests import RequestsInstrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("requests") as record:
        (instance,) = record.instrumentations

        assert type(instance) is RequestsInstrumentation
        assert instance.name == "requests"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Outbound request tracing and trace propagation for requests."
        )


def test_a_config_entry_applies_and_reverts(server: Server) -> None:
    applied = Config(instrument=[InstrumentEntry("requests")]).apply()
    try:
        report = applied.report()
        assert "requests" in report
        assert f"target requests {metadata.version('requests')}" in report
        assert "applied requests.sessions" in report

        with timeline() as tape:
            requests.get(f"{server.url}/ok")

        assert [event.path for event in tape.all] == ["requests.sessions:Session.send"]
    finally:
        applied.revert()

    with timeline() as tape:
        requests.get(f"{server.url}/ok")

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"requests  ({DISTRIBUTION} {__version__})" in output
    assert "  Outbound request tracing and trace propagation for requests." in output
    assert (
        f"  target: requests {metadata.version('requests')},"
        " supported (>=2.31,<3)" in output
    )
    assert "  modules: requests.sessions" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    leaf = true " in output
    assert (
        "record each send as a terminal node, so the nested sends behind a"
        " redirect and anything recorded beneath it stay out of the tree" in output
    )
    assert "    propagate = true " in output
    assert (
        "add the current trace identity to each request's headers so the"
        " service called can join the trace" in output
    )


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "requests"\nenabled = false' in output
    assert "# leaf = true" in output
    assert "# propagate = true" in output
    assert "# redact = []" in output
