"""The entry point: resolving the instrumentation by its bare name,
and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.framework.django.shop import make_wsgi_app
from tests.wsgi import request
from wrapture_instrumentation import __version__
from wrapture_instrumentation.framework.django import DjangoInstrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("django") as record:
        (instance,) = record.instrumentations

        assert type(instance) is DjangoInstrumentation
        assert instance.name == "django"
        assert instance.distribution == DISTRIBUTION
        assert instance.description == (
            "Request, database and template tracing for Django applications."
        )


def test_a_config_entry_applies_and_reverts() -> None:
    applied = Config(instrument=[InstrumentEntry("django")]).apply()
    try:
        report = applied.report()
        assert "django" in report
        assert f"target django {metadata.version('django')}" in report
        assert "applied django.core.handlers.wsgi, django.core.handlers.asgi" in report

        with timeline() as tape:
            request(make_wsgi_app(), "GET", "/")

        assert [event.kind for event in tape.all] == ["request", "call"]
    finally:
        applied.revert()

    with timeline() as tape:
        request(make_wsgi_app(), "GET", "/")

    assert tape.all == []


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"django  ({DISTRIBUTION} {__version__})" in output
    assert "  Request, database and template tracing for Django applications." in output
    assert (
        f"  target: django {metadata.version('django')}, supported (>=4.2,<7)" in output
    )
    assert "  modules: django.core.handlers.wsgi, django.core.handlers.asgi" in output

    # The listing pads the setting names into a column, so the name
    # and its description are checked apart.

    assert "    ignore_paths = [] " in output
    assert "request paths not to record, as path" in output
    assert "    queries = true " in output
    assert "    statement = false " in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "django"\nenabled = false' in output
    assert "# ignore_paths = []" in output
    assert "# queries = true" in output
    assert "# leaf = true" in output
    assert "# templates = true" in output
