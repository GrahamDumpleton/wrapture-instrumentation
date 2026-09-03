"""The entry point: resolving the instrumentation by its dotted name,
and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

from wrapture import (
    Config,
    InstrumentEntry,
    Tape,
    add_sink,
    instrumentation,
    remove_sink,
)

from tests.conftest import DISTRIBUTION, run_tool
from tests.server.aiohttp_web.conftest import drive
from tests.server.aiohttp_web.shop import make_app
from wrapture_instrumentation import __version__
from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation


def test_the_dotted_name_resolves_to_the_class() -> None:
    with instrumentation("aiohttp.web") as record:
        (instance,) = record.instrumentations

        assert type(instance) is AiohttpWebInstrumentation
        assert instance.name == "aiohttp.web"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Request and route tracing for aiohttp.web server applications."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("aiohttp.web")]).apply()
    try:
        report = applied.report()
        assert "aiohttp.web" in report
        assert f"target aiohttp.web {metadata.version('aiohttp')}" in report
        assert "applied aiohttp.web" in report

        tape = Tape()
        add_sink(tape)
        try:
            drive(make_app(), "/")
        finally:
            remove_sink(tape)

        assert [event.kind for event in tape.all] == ["block", "call"]
    finally:
        applied.revert()

    tape = Tape()
    add_sink(tape)
    try:
        drive(make_app(), "/")
    finally:
        remove_sink(tape)

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"aiohttp.web  ({DISTRIBUTION} {__version__})" in output
    assert "  Request and route tracing for aiohttp.web server applications." in output
    assert (
        f"  target: aiohttp.web {metadata.version('aiohttp')},"
        " supported (>=3.10,<4)" in output
    )
    assert "  modules: aiohttp.web" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    ignore_paths = [] " in output
    assert "request paths not to record, as path" in output
    assert "    join = true " in output
    assert "join the distributed trace an arriving request's" in output
    assert "    redact = [] " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "aiohttp.web"\nenabled = false' in output
    assert "# ignore_paths = []" in output
    assert "# join = true" in output
    assert "# redact = []" in output
