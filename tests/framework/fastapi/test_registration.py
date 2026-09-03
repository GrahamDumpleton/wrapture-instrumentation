"""The entry point: resolving the instrumentation by its bare name,
and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.asgi import request
from tests.conftest import DISTRIBUTION, run_tool
from tests.framework.fastapi.shop import make_app
from wrapture_instrumentation import __version__
from wrapture_instrumentation.framework.fastapi import FastAPIInstrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("fastapi") as record:
        (instance,) = record.instrumentations

        assert type(instance) is FastAPIInstrumentation
        assert instance.name == "fastapi"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Request and route tracing for FastAPI applications."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("fastapi")]).apply()
    try:
        report = applied.report()
        assert "fastapi" in report
        assert f"target fastapi {metadata.version('fastapi')}" in report
        assert "applied fastapi.applications, fastapi.routing" in report

        with timeline() as tape:
            request(make_app(), "GET", "/quote/widget")

        assert [event.kind for event in tape.all] == ["request", "call"]
    finally:
        applied.revert()

    with timeline() as tape:
        request(make_app(), "GET", "/quote/widget")

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"fastapi  ({DISTRIBUTION} {__version__})" in output
    assert "  Request and route tracing for FastAPI applications." in output
    assert (
        f"  target: fastapi {metadata.version('fastapi')},"
        " supported (>=0.110,<1)" in output
    )
    assert "  modules: fastapi.applications, fastapi.routing" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    ignore_paths = [] " in output
    assert "request paths not to record, as path" in output
    assert "    redact = [] " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "fastapi"\nenabled = false' in output
    assert "# ignore_paths = []" in output
    assert "# redact = []" in output
