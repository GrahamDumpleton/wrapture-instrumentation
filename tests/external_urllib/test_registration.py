"""The entry point: resolving the instrumentation by its bare name,
and what the listing tool says about it."""

from __future__ import annotations

import platform
import urllib.request

from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.external_urllib.server import Server
from wrapture_instrumentation import __version__
from wrapture_instrumentation.external_urllib import UrllibInstrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("urllib") as record:
        (instance,) = record.instrumentations

        assert type(instance) is UrllibInstrumentation
        assert instance.name == "urllib"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Outbound request tracing and trace propagation for urllib."
        )


def test_a_config_entry_applies_and_reverts(server: Server) -> None:
    applied = Config(instrument=[InstrumentEntry("urllib")]).apply()
    try:
        report = applied.report()
        assert "urllib" in report
        assert (
            f"target urllib (standard library, python {platform.python_version()})"
            in report
        )
        assert "applied urllib.request" in report

        with timeline() as tape:
            urllib.request.urlopen(f"{server.url}/ok").close()

        assert [event.path for event in tape.all] == [
            "urllib.request:OpenerDirector.open"
        ]
    finally:
        applied.revert()

    with timeline() as tape:
        urllib.request.urlopen(f"{server.url}/ok").close()

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"urllib  ({DISTRIBUTION} {__version__})" in output
    assert "  Outbound request tracing and trace propagation for urllib." in output
    assert (
        f"  target: urllib (standard library, python {platform.python_version()}),"
        " supported (>=3.12)" in output
    )
    assert "  modules: urllib.request" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    leaf = true " in output
    assert (
        "record each open as a terminal node, so the nested opens behind a"
        " redirect and anything recorded beneath it stay out of the tree" in output
    )
    assert "    propagate = true " in output
    assert (
        "add the current trace identity to each request's headers so the"
        " service called can join the trace" in output
    )


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "urllib"\nenabled = false' in output
    assert "# leaf = true" in output
    assert "# propagate = true" in output
    assert "# redact = []" in output
