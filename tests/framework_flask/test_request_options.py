"""The request-shaping settings: ignore_paths keeping nominated
requests off the tape entirely, and redact masking query string
parameters by name."""

from __future__ import annotations

import flask
from wrapture import Config, InstrumentEntry, instrumentation, timeline

from tests.wsgi import request
from wrapture_instrumentation.framework_flask import FlaskInstrumentation


def make_probe() -> flask.Flask:
    """An application with a health endpoint beside a working route,
    and a lifecycle callback that runs on every request."""

    app = flask.Flask("probe")

    def health() -> str:
        return "ok"

    def work() -> str:
        return "done"

    def stamp() -> None:
        return None

    app.before_request(stamp)
    app.add_url_rule("/health", "health", health)
    app.add_url_rule("/static/<name>", "asset", lambda name: name)
    app.add_url_rule("/work", "work", work)

    return app


def test_ignored_paths_record_nothing_and_still_answer() -> None:
    # An ignored request leaves no events at all: the middleware's
    # filter declines the request with tree=True, so the view and the
    # lifecycle callback beneath it are silenced rather than left as
    # stray roots. The application still runs and answers.

    with (
        instrumentation(FlaskInstrumentation, ignore_paths=["/health", "/static/*"]),
        timeline() as tape,
    ):
        app = make_probe()

        response = request(app, "GET", "/health")
        assert response.status == "200 OK"
        assert response.body == b"ok"

        response = request(app, "GET", "/static/logo.png")
        assert response.body == b"logo.png"

        response = request(app, "GET", "/work")
        assert response.body == b"done"

    assert [(event.kind, event.label or event.path) for event in tape.all] == [
        ("request", "probe.wsgi_app"),
        ("call", f"{__name__}:make_probe.<locals>.stamp"),
        ("call", "work"),
    ]


def test_redact_masks_named_query_parameters() -> None:
    # The named parameter is masked in the recorded query while the
    # rest pass; the built-in sensitive set stays enforced on top.

    with (
        instrumentation(FlaskInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        request(make_probe(), "GET", "/work", query="voucher=SECRET50&limit=5&token=t")

    seen = tape.all[0]
    assert seen.data["query"] == "voucher=<redacted>&limit=5&token=<redacted>"
    assert "SECRET50" not in repr(seen.data)


def test_the_settings_arrive_through_a_config_entry() -> None:
    # The [[instrument]] form of the same settings, as a config file
    # would build them.

    applied = Config(
        instrument=[
            InstrumentEntry(
                "flask",
                settings={"ignore_paths": ["/health"], "redact": ["voucher"]},
            )
        ]
    ).apply()
    try:
        with timeline() as tape:
            app = make_probe()
            request(app, "GET", "/health")
            request(app, "GET", "/work", query="voucher=x")

        events = [event for event in tape.all if event.kind == "request"]
        assert [event.data["path"] for event in events] == ["/work"]
        assert events[0].data["query"] == "voucher=<redacted>"
    finally:
        applied.revert()


def test_defaults_ignore_nothing_and_redact_only_the_built_ins() -> None:
    with instrumentation(FlaskInstrumentation), timeline() as tape:
        request(make_probe(), "GET", "/health", query="voucher=v&api_key=k")

    seen = tape.all[0]
    assert seen.data["path"] == "/health"
    assert seen.data["query"] == "voucher=v&api_key=<redacted>"
