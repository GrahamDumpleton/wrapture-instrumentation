"""The entry point: resolving the instrumentation by its dotted name,
and what the listing tool says about it."""

from __future__ import annotations

import platform
import urllib.request

from wrapture import (
    Config,
    InstrumentEntry,
    Tape,
    add_sink,
    instrumentation,
    remove_sink,
)

from tests.conftest import DISTRIBUTION, run_tool
from tests.server.wsgiref_simple_server.conftest import hello_app, serve, settled
from wrapture_instrumentation import __version__
from wrapture_instrumentation.server.wsgiref_simple_server import (
    WSGIRefSimpleServerInstrumentation,
)


def test_the_dotted_name_resolves_to_the_class() -> None:
    with instrumentation("wsgiref.simple_server") as record:
        (instance,) = record.instrumentations

        assert type(instance) is WSGIRefSimpleServerInstrumentation
        assert instance.name == "wsgiref.simple_server"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Request tracing for applications served by wsgiref.simple_server."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("wsgiref.simple_server")]).apply()
    try:
        report = applied.report()
        assert "wsgiref.simple_server" in report
        assert (
            "target wsgiref.simple_server (standard library,"
            f" python {platform.python_version()})" in report
        )
        assert "applied wsgiref.simple_server" in report

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

    assert f"wsgiref.simple_server  ({DISTRIBUTION} {__version__})" in output
    assert (
        "  Request tracing for applications served by wsgiref.simple_server." in output
    )
    assert (
        "  target: wsgiref.simple_server (standard library,"
        f" python {platform.python_version()}), supported (>=3.12)" in output
    )
    assert "  modules: wsgiref.simple_server" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    ignore_paths = [] " in output
    assert "request paths not to record, as path" in output
    assert "    redact = [] " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "wsgiref.simple_server"\nenabled = false' in output
    assert "# ignore_paths = []" in output
    assert "# redact = []" in output
