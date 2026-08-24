"""Applying and removing: what the patches do to Flask while applied,
and that removal leaves Flask as it was.

The live instance is reached through wrapture.instrumentation(), which
applies the class the way a config does and removes it on exit. The
instrumentation-packages page also documents a direct recipe,
construct, apply(name, module), remove(name, module), with no wrapture
machinery; that recipe is pinned at the bottom.
"""

from __future__ import annotations

from collections.abc import Iterator

import flask
import flask.app
import flask.sansio.blueprints
import flask.sansio.scaffold
import pytest
import wrapture
from wrapture import Instrumentation, ObservedCallable, WSGIMiddleware, instrumentation

from tests.framework_flask.shop import index, make_app, quoted
from wrapture_instrumentation.framework_flask import FlaskInstrumentation

CHOKE_POINTS: tuple[tuple[type, str], ...] = (
    (flask.app.Flask, "__init__"),
    (flask.app.Flask, "add_url_rule"),
    (flask.app.Flask, "preprocess_request"),
    (flask.app.Flask, "teardown_appcontext"),
    (flask.app.Flask, "handle_user_exception"),
    (flask.app.Flask, "handle_exception"),
    (flask.sansio.scaffold.Scaffold, "before_request"),
    (flask.sansio.scaffold.Scaffold, "after_request"),
    (flask.sansio.scaffold.Scaffold, "teardown_request"),
    (flask.sansio.scaffold.Scaffold, "register_error_handler"),
    (flask.sansio.blueprints.Blueprint, "before_app_request"),
    (flask.sansio.blueprints.Blueprint, "after_app_request"),
    (flask.sansio.blueprints.Blueprint, "teardown_app_request"),
)


def choke_points() -> dict[tuple[type, str], object]:
    """The callables currently at every patched name, across the three
    patched classes.

    Some are inherited (add_url_rule and teardown_appcontext come
    from flask.sansio.app.App), so the lookup is getattr rather than
    the class's own dict; the bindings patch the class named here and
    removal restores what it inherited.
    """

    return {(cls, name): getattr(cls, name) for cls, name in CHOKE_POINTS}


@pytest.fixture
def applied() -> Iterator[Instrumentation]:
    with instrumentation(FlaskInstrumentation) as record:
        (instance,) = record.instrumentations
        yield instance


def test_apply_installs_the_middleware_on_each_new_application(
    applied: Instrumentation,
) -> None:
    app = make_app("first")
    other = make_app("second")

    assert isinstance(app.wsgi_app, WSGIMiddleware)
    assert isinstance(other.wsgi_app, WSGIMiddleware)
    assert app.wsgi_app is not other.wsgi_app


def test_apply_observes_every_registered_view(applied: Instrumentation) -> None:
    app = make_app()

    # Positional view_func, keyword view_func, a blueprint's view
    # registered through register_blueprint, and a MethodView's
    # generated view all pass through add_url_rule.

    for endpoint in ("index", "quoted", "export", "catalog", "reports.summary"):
        assert isinstance(app.view_functions[endpoint], ObservedCallable), endpoint

    # The proxy is transparent: the original is what it wraps.

    for endpoint, original in (("index", index), ("quoted", quoted)):
        view = app.view_functions[endpoint]
        assert isinstance(view, ObservedCallable)
        assert view.__wrapped__ is original


def test_a_rule_without_a_view_function_passes_through(
    applied: Instrumentation,
) -> None:
    # add_url_rule(rule, endpoint) alone, the endpoint being bound to
    # a view later or never, is legal Flask and must not be touched.

    app = flask.Flask("bare")
    app.add_url_rule("/later", "later")

    assert "later" not in app.view_functions


def test_the_proxied_view_is_not_wrapped_twice(applied: Instrumentation) -> None:
    # Flask lets the same function register under the same endpoint
    # again for another rule. The second registration hands the
    # wrapper the caller's original function, not the proxy from the
    # first, so the fresh proxy wraps the raw view and observations
    # never stack.

    app = flask.Flask("twice")
    app.add_url_rule("/a", "index", index)
    app.add_url_rule("/b", "index", index)

    view = app.view_functions["index"]
    assert isinstance(view, ObservedCallable)
    assert not isinstance(view.__wrapped__, ObservedCallable)


def test_the_construction_itself_is_not_recorded(applied: Instrumentation) -> None:
    # The three bindings are behaviour-only (when=False): constructing
    # an application and registering its routes records nothing, so
    # the instrumentation's own plumbing stays out of the trace.

    with wrapture.timeline() as tape:
        make_app()

    assert tape.all == []


def same(
    first: dict[tuple[type, str], object], second: dict[tuple[type, str], object]
) -> bool:
    # wrapt's wrappers compare equal to what they wrap, so restoration
    # is a question of identity, name by name.

    return all(first[key] is second[key] for key in first)


def test_apply_then_remove_leaves_flask_as_it_was() -> None:
    before = choke_points()

    with instrumentation(FlaskInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == (
            "flask.app",
            "flask.sansio.scaffold",
            "flask.sansio.blueprints",
        )
        assert not same(choke_points(), before)

    assert same(choke_points(), before)
    assert not instance.applied


def test_after_remove_new_applications_are_plain() -> None:
    with instrumentation(FlaskInstrumentation):
        pass

    app = make_app("afterwards")

    assert not isinstance(app.wsgi_app, WSGIMiddleware)
    assert not isinstance(app.view_functions["index"], ObservedCallable)


def test_an_application_built_while_applied_keeps_its_middleware() -> None:
    # Removal unpatches the class; it does not reach into instances
    # already built, whose wsgi_app and view functions were set at
    # construction and registration. The middleware they keep records
    # only while something is listening, exactly as before.

    with instrumentation(FlaskInstrumentation):
        app = make_app("during")

    assert isinstance(app.wsgi_app, WSGIMiddleware)
    assert isinstance(app.view_functions["index"], ObservedCallable)


def test_the_documented_direct_recipe_applies_and_removes() -> None:
    # The recipe from the instrumentation-packages page, verbatim in
    # shape: no wrapture machinery, construct, apply, remove.

    before = choke_points()
    instance = FlaskInstrumentation()

    instance.apply("flask.app", flask.app)
    try:
        app = make_app("direct")
        assert isinstance(app.wsgi_app, WSGIMiddleware)
    finally:
        instance.remove("flask.app", flask.app)

    assert same(choke_points(), before)
