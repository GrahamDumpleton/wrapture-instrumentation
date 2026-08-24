"""Template rendering observed: the four flask.templating functions,
what their events capture and deliberately do not, and the namespace
re-export patching in both apply orders.
"""

from __future__ import annotations

from collections.abc import Iterator

import flask
import flask.templating
import pytest
from jinja2 import DictLoader
from wrapture import Tape, instrumentation, timeline

from tests.conftest import run_snippet
from tests.framework_flask.shop import make_app
from tests.wsgi import request
from wrapture_instrumentation.framework_flask import FlaskInstrumentation

TEMPLATES = {
    "page.html": "<p>Hello {{ person }}</p>",
    "rows.html": "{% for row in rows %}{{ row }}\n{% endfor %}",
}


def make_pages(name: str = "pages") -> flask.Flask:
    """A small application whose view renders a template."""

    app = flask.Flask(name)
    app.jinja_env.loader = DictLoader(TEMPLATES)

    def hello(person: str) -> str:
        return flask.render_template("page.html", person=person)

    app.add_url_rule("/hello/<person>", "hello", hello)

    return app


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(FlaskInstrumentation), timeline() as recorded:
        yield recorded


def test_a_rendering_view_shows_the_render_beneath_it(tape: Tape) -> None:
    response = request(make_pages(), "GET", "/hello/pat")

    assert response.status == "200 OK"
    assert response.body == b"<p>Hello pat</p>"

    (seen, view, render) = tape.all
    assert render.arguments is not None
    assert seen.kind == "request"
    assert view.label == "hello"
    assert render.label == "flask.render_template"
    assert tape.parent_of(render) is view


def test_the_template_name_is_captured_and_the_context_is_not(tape: Tape) -> None:
    request(make_pages(), "GET", "/hello/secret-person")

    (*_, render) = tape.all
    assert render.arguments is not None
    assert render.arguments["template_name_or_list"] == "page.html"

    # The context is arbitrary application data and never leaves the
    # process; the rendered output reports only its size.

    assert render.arguments["context"] == "<context>"
    assert "secret-person" not in repr(render.arguments)
    assert render.result == "<26 chars>"


def test_render_template_string_truncates_the_source(tape: Tape) -> None:
    app = make_pages()
    source = "{{ person }} " + "x" * 100

    with app.app_context():
        flask.render_template_string(source, person="pat")

    (render,) = tape.all
    assert render.label == "flask.render_template_string"

    assert render.arguments is not None
    captured = render.arguments["source"]
    assert len(captured) == 60
    assert captured.endswith("...")


def test_a_streamed_render_records_around_the_iteration(tape: Tape) -> None:
    app = make_pages()

    with app.app_context():
        stream = flask.stream_template("rows.html", rows=[1, 2, 3])
        chunks = list(stream)

    assert "".join(chunks) == "1\n2\n3\n"

    (render,) = tape.all
    assert render.label == "flask.stream_template"
    assert render.duration is not None


def test_both_module_and_namespace_attributes_are_patched(tape: Tape) -> None:
    # The documented spelling is the flask namespace re-export; the
    # defining module works too, each records exactly one event, and
    # both carry the same explicit label whichever path the call took.

    app = make_pages()

    with app.app_context():
        flask.render_template("page.html", person="a")
        flask.templating.render_template("page.html", person="b")

    assert [event.label for event in tape.all] == [
        "flask.render_template",
        "flask.render_template",
    ]


def test_a_from_import_taken_before_apply_stays_plain(tape: Tape) -> None:
    # The shop module did "from flask import render_template" when
    # this module imported it above, before the instrumentation
    # applied, so its reference is the original function and its
    # renders go unobserved: the /pricing request records the request
    # and the view, no render. Under the runner (apply before any
    # import) the same code is observed; the fresh-interpreter test
    # below proves that order.

    response = request(make_app(), "GET", "/pricing")

    assert response.status == "200 OK"
    assert [event.kind for event in tape.all] == ["request", "call"]


def test_a_triggers_subset_applies_templating_alone() -> None:
    # The package trigger carries templating alone: with only it in
    # play the renders record while requests and views do not.

    with (
        instrumentation(FlaskInstrumentation, triggers="flask"),
        timeline() as tape,
    ):
        response = request(make_pages(), "GET", "/hello/pat")

    assert response.status == "200 OK"
    assert [event.label for event in tape.all] == ["flask.render_template"]


def test_removal_restores_both_attributes() -> None:
    before = (flask.render_template, flask.templating.render_template)

    with instrumentation(FlaskInstrumentation):
        assert flask.render_template is not before[0]
        assert flask.templating.render_template is not before[1]

    assert flask.render_template is before[0]
    assert flask.templating.render_template is before[1]


def test_the_fresh_import_order_wraps_and_restores_the_namespace() -> None:
    # The runner case: the instrumentation applies before flask ever
    # imports. The package trigger fires only after flask/__init__
    # finishes executing, by which point its from-import has copied
    # the original functions into the namespace, so all eight
    # attributes bind as plain functions and removal restores every
    # one through the binding machinery; a fresh interpreter is the
    # only honest way to exercise the order.

    output = run_snippet(
        "import types\n"
        "import wrapture\n"
        "from wrapture_instrumentation.framework_flask import FlaskInstrumentation\n"
        "scope = wrapture.instrumentation(FlaskInstrumentation)\n"
        "scope.__enter__()\n"
        "import flask\n"
        "from jinja2 import DictLoader\n"
        "app = flask.Flask('t')\n"
        "app.jinja_env.loader = DictLoader({'p.html': 'hi'})\n"
        "with wrapture.timeline() as tape:\n"
        "    with app.app_context():\n"
        "        flask.render_template('p.html')\n"
        "print('recorded', len(tape.all))\n"
        "scope.__exit__(None, None, None)\n"
        "print('plain', isinstance(flask.render_template, types.FunctionType))\n"
        "with wrapture.timeline() as tape:\n"
        "    with app.app_context():\n"
        "        flask.render_template('p.html')\n"
        "print('after', len(tape.all))\n"
    )

    assert output.splitlines() == ["recorded 1", "plain True", "after 0"]


def test_templates_off_quietens_the_renders() -> None:
    # With the templates switch off the trigger binds nothing: a
    # rendering view records the request and the view alone, and the
    # render still happens.

    with (
        instrumentation(FlaskInstrumentation, templates=False),
        timeline() as tape,
    ):
        response = request(make_pages(), "GET", "/hello/pat")

    assert response.status == "200 OK"
    assert response.body == b"<p>Hello pat</p>"
    assert [event.kind for event in tape.all] == ["request", "call"]
