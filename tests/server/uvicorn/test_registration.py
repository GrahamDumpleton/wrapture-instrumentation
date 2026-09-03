"""The entry point: resolving the instrumentation by its bare name,
and what the listing tool says about it."""

from __future__ import annotations

import urllib.request
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
from tests.server.uvicorn.conftest import hello_app, serve, settled
from wrapture_instrumentation import __version__
from wrapture_instrumentation.server.uvicorn import UvicornInstrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("uvicorn") as record:
        (instance,) = record.instrumentations

        assert type(instance) is UvicornInstrumentation
        assert instance.name == "uvicorn"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Request tracing for applications served by uvicorn."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("uvicorn")]).apply()
    try:
        report = applied.report()
        assert "uvicorn" in report
        assert f"target uvicorn {metadata.version('uvicorn')}" in report
        assert "applied uvicorn.config" in report

        tape = Tape()
        add_sink(tape)
        try:
            serving = serve(hello_app)
            url = next(serving)
            try:
                urllib.request.urlopen(url).close()
                settled(tape)
            finally:
                next(serving, None)
        finally:
            remove_sink(tape)
    finally:
        applied.revert()

    tape = Tape()
    add_sink(tape)
    try:
        serving = serve(hello_app)
        url = next(serving)
        try:
            urllib.request.urlopen(url).close()
        finally:
            next(serving, None)
    finally:
        remove_sink(tape)

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"uvicorn  ({DISTRIBUTION} {__version__})" in output
    assert "  Request tracing for applications served by uvicorn." in output
    assert (
        f"  target: uvicorn {metadata.version('uvicorn')},"
        " supported (>=0.30,<1)" in output
    )
    assert "  modules: uvicorn.config" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    ignore_paths = [] " in output
    assert "request paths not to record, as path" in output
    assert "    redact = [] " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "uvicorn"\nenabled = false' in output
    assert "# ignore_paths = []" in output
    assert "# redact = []" in output
