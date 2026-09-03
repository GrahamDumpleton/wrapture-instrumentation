"""The entry point: resolving the instrumentation by its dotted name,
and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.external.aiohttp_client.conftest import run
from tests.httpserver import Server
from wrapture_instrumentation import __version__
from wrapture_instrumentation.external.aiohttp_client import (
    AiohttpClientInstrumentation,
)


async def get(session: object, url: str) -> None:
    async with session.get(url) as response:  # type: ignore[attr-defined]
        await response.read()


def test_the_dotted_name_resolves_to_the_class() -> None:
    with instrumentation("aiohttp.client") as record:
        (instance,) = record.instrumentations

        assert type(instance) is AiohttpClientInstrumentation
        assert instance.name == "aiohttp.client"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Outbound request tracing and trace propagation for aiohttp's client."
        )


def test_a_config_entry_applies_and_reverts(server: Server) -> None:
    applied = Config(instrument=[InstrumentEntry("aiohttp.client")]).apply()
    try:
        report = applied.report()
        assert "aiohttp.client" in report
        assert f"target aiohttp.client {metadata.version('aiohttp')}" in report
        assert "applied aiohttp.client" in report

        with timeline() as tape:
            run(lambda s: get(s, f"{server.url}/ok"))

        assert [event.path for event in tape.all] == [
            "aiohttp.client:ClientSession._request"
        ]
    finally:
        applied.revert()

    with timeline() as tape:
        run(lambda s: get(s, f"{server.url}/ok"))

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"aiohttp.client  ({DISTRIBUTION} {__version__})" in output
    assert (
        "  Outbound request tracing and trace propagation for aiohttp's client."
        in output
    )
    assert (
        f"  target: aiohttp.client {metadata.version('aiohttp')},"
        " supported (>=3.10,<4)" in output
    )
    assert "  modules: aiohttp.client\n" in output

    assert "    leaf = true " in output
    assert "    propagate = true " in output
    assert "    redact = [] " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "aiohttp.client"\nenabled = false' in output
    assert "# leaf = true" in output
    assert "# propagate = true" in output
    assert "# redact = []" in output
