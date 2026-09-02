"""The entry point: resolving the instrumentation by its dotted name,
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
from tests.server.werkzeug_serving.conftest import hello_app, serve, settled
from wrapture_instrumentation import __version__
from wrapture_instrumentation.server.werkzeug_serving import (
    WerkzeugServingInstrumentation,
)


def test_the_dotted_name_resolves_to_the_class() -> None:
    with instrumentation("werkzeug.serving") as record:
        (instance,) = record.instrumentations

        assert type(instance) is WerkzeugServingInstrumentation
        assert instance.name == "werkzeug.serving"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Request tracing for applications served by werkzeug's development server."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("werkzeug.serving")]).apply()
    try:
        report = applied.report()
        assert "werkzeug.serving" in report
        assert f"target werkzeug.serving {metadata.version('werkzeug')}" in report
        assert "applied werkzeug.serving" in report

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

    assert f"werkzeug.serving  ({DISTRIBUTION} {__version__})" in output
    assert (
        "  Request tracing for applications served by werkzeug's"
        " development server." in output
    )
    assert (
        f"  target: werkzeug.serving {metadata.version('werkzeug')},"
        " supported (>=3.0,<4)" in output
    )
    assert "  modules: werkzeug.serving" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    ignore_paths = [] " in output
    assert "request paths not to record, as path" in output
    assert "    redact = [] " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "werkzeug.serving"\nenabled = false' in output
    assert "# ignore_paths = []" in output
    assert "# redact = []" in output
