"""The entry point: resolving the instrumentation by its dotted name,
and what the listing tool says about it."""

from __future__ import annotations

import http.client
import platform

from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.external_http_client.conftest import host_of
from tests.httpserver import Server
from wrapture_instrumentation import __version__
from wrapture_instrumentation.external_http_client import HTTPClientInstrumentation

PHASES = [
    "http.client:HTTPConnection.putrequest",
    "http.client:HTTPConnection.endheaders",
    "http.client:HTTPConnection.connect",
    "http.client:HTTPConnection.getresponse",
]


def test_the_dotted_name_resolves_to_the_class() -> None:
    with instrumentation("http.client") as record:
        (instance,) = record.instrumentations

        assert type(instance) is HTTPClientInstrumentation
        assert instance.name == "http.client"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == "Wire-level tracing for http.client."


def test_a_config_entry_applies_and_reverts(server: Server) -> None:
    applied = Config(instrument=[InstrumentEntry("http.client")]).apply()
    try:
        report = applied.report()
        assert "http.client" in report
        assert (
            "target http.client (standard library,"
            f" python {platform.python_version()})" in report
        )
        assert "applied http.client" in report

        connection = http.client.HTTPConnection(host_of(server))
        try:
            with timeline() as tape:
                connection.request("GET", "/ok")
                connection.getresponse().read()
        finally:
            connection.close()

        assert [event.path for event in tape.all] == PHASES
    finally:
        applied.revert()

    connection = http.client.HTTPConnection(host_of(server))
    try:
        with timeline() as tape:
            connection.request("GET", "/ok")
            connection.getresponse().read()
    finally:
        connection.close()

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"http.client  ({DISTRIBUTION} {__version__})" in output
    assert "  Wire-level tracing for http.client." in output
    assert (
        "  target: http.client (standard library,"
        f" python {platform.python_version()}), supported (>=3.12)" in output
    )
    assert "  modules: http.client" in output
    assert "    redact = []" in output
    assert (
        "query string parameters to mask by name, on top of the"
        " built-in sensitive set" in output
    )


def test_the_toml_template_carries_the_setting() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "http.client"\nenabled = false' in output
    assert "# redact = []" in output
