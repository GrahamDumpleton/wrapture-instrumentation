"""The entry point: resolving the instrumentation by its bare name,
and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

import jinja2
from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from wrapture_instrumentation import __version__
from wrapture_instrumentation.template_jinja2 import Jinja2Instrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("jinja2") as record:
        (instance,) = record.instrumentations

        assert type(instance) is Jinja2Instrumentation
        assert instance.name == "jinja2"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == "Template rendering tracing for Jinja2."


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("jinja2")]).apply()
    try:
        report = applied.report()
        assert "jinja2" in report
        assert f"target jinja2 {metadata.version('jinja2')}" in report
        assert "applied jinja2.environment" in report

        env = jinja2.Environment(loader=jinja2.DictLoader({"p.html": "hi"}))
        with timeline() as tape:
            env.get_template("p.html").render()

        assert [event.label for event in tape.all] == [
            "jinja2.load",
            "jinja2.compile",
            "jinja2.render",
        ]
    finally:
        applied.revert()

    env = jinja2.Environment(loader=jinja2.DictLoader({"p.html": "hi"}))
    with timeline() as tape:
        env.get_template("p.html").render()

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"jinja2  ({DISTRIBUTION} {__version__})" in output
    assert "  Template rendering tracing for Jinja2." in output
    assert (
        f"  target: jinja2 {metadata.version('jinja2')}, supported (>=3.0,<4)" in output
    )
    assert "  modules: jinja2.environment" in output
    assert (
        "    loading = true   observe template loading and compilation"
        " (the jinja2.load and jinja2.compile events)" in output
    )


def test_the_toml_template_carries_the_setting() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "jinja2"\nenabled = false' in output
    assert "# loading = true" in output
