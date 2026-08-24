"""The entry point: resolving the instrumentation by its bare name, the
way a config file does, and what the listing tool says about it."""

from __future__ import annotations

from importlib import metadata

from wrapture import Config, InstrumentEntry, WSGIMiddleware, instrumentation, timeline

from tests.conftest import DISTRIBUTION, run_tool
from tests.framework_flask.shop import make_app
from tests.wsgi import request
from wrapture_instrumentation import __version__
from wrapture_instrumentation.framework_flask import FlaskInstrumentation


def test_the_bare_name_resolves_to_the_class() -> None:
    with instrumentation("flask") as record:
        (instance,) = record.instrumentations

        assert type(instance) is FlaskInstrumentation
        assert instance.name == "flask"
        assert instance.distribution == DISTRIBUTION
        assert instance.version == __version__
        assert (
            instance.description == "Request and view tracing for Flask applications."
        )


def test_the_qualified_name_resolves_too() -> None:
    with instrumentation(f"flask@{DISTRIBUTION}") as record:
        (instance,) = record.instrumentations

        assert type(instance) is FlaskInstrumentation


def test_a_config_entry_applies_and_reverts() -> None:
    # The programmatic form of `[[instrument]]` with `name = "flask"`:
    # what a config file builds, applied and reverted by hand.

    applied = Config(instrument=[InstrumentEntry("flask")]).apply()
    try:
        report = applied.report()
        assert "flask" in report
        assert f"target flask {metadata.version('flask')}" in report
        assert (
            "applied flask.app, flask.sansio.scaffold, flask.sansio.blueprints"
            in report
        )
        assert "removable" in report

        with timeline() as tape:
            app = make_app()
            request(app, "GET", "/")

        assert isinstance(app.wsgi_app, WSGIMiddleware)
        assert [event.kind for event in tape.all] == ["request", "call"]
    finally:
        applied.revert()

    assert not isinstance(make_app().wsgi_app, WSGIMiddleware)


def test_the_listing_tool_describes_the_entry() -> None:
    output = run_tool("instrumentation", "--verbose")

    assert f"flask  ({DISTRIBUTION} {__version__})" in output
    assert "  Request and view tracing for Flask applications." in output
    assert (
        f"  target: flask {metadata.version('flask')}, supported (>=3.0,<4)" in output
    )
    assert (
        "  modules: flask.app, flask.sansio.scaffold, flask.sansio.blueprints" in output
    )
    assert "  removable: yes" in output
    assert "  settings:" in output
    assert (
        "    lifecycle = true        observe before/after/teardown callbacks"
        " as they register" in output
    )
    assert (
        "    handled_errors = true   note an exception a registered handler"
        " absorbed against its request" in output
    )
    assert "  would register: flask.app\n" in output
    assert "  would register: flask.sansio.scaffold\n" in output
    assert "  would register: flask.sansio.blueprints\n" in output


def test_the_toml_template_carries_the_settings() -> None:
    output = run_tool("instrumentation", "--toml")

    assert '[[instrument]]\nname = "flask"\nenabled = false' in output
    assert "# lifecycle = true" in output
    assert "# handled_errors = true" in output
