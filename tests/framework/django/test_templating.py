"""DTL template rendering observed beneath the view: the template
category, the name annotation, what the events deliberately do not
capture, and the templates switch."""

from __future__ import annotations

from wrapture import Tape, instrumentation, timeline

from tests.framework.django.shop import make_wsgi_app
from tests.wsgi import request
from wrapture_instrumentation.framework.django import DjangoInstrumentation

RENDER = "django.template.base:Template.render"


def test_a_rendering_view_shows_the_render_beneath_it(tape: Tape) -> None:
    response = request(make_wsgi_app(), "GET", "/pricelist/")

    assert response.status == "200 OK"
    assert response.body == b"<p>Hello pat</p>\n"

    (seen, view, render) = tape.all
    assert seen.kind == "request"
    assert view.label == "pricelist"

    assert render.kind == "call"
    assert render.category == "template"
    assert render.label is None
    assert render.path == RENDER
    assert render.data["template"] == "page.html"
    assert tape.parent_of(render) is view


def test_the_context_is_not_captured_and_the_output_is_a_size(tape: Tape) -> None:
    request(make_wsgi_app(), "GET", "/pricelist/", query="person=secret-person")

    (*_, render) = tape.all
    assert render.path == RENDER

    assert render.arguments is not None
    assert set(render.arguments.values()) == {"<context>"}
    assert "secret-person" not in repr(render.arguments)
    assert render.result == f"<{len('<p>Hello secret-person</p>') + 1} chars>"


def test_templates_off_quietens_the_renders() -> None:
    with (
        instrumentation(DjangoInstrumentation, templates=False),
        timeline() as tape,
    ):
        response = request(make_wsgi_app(), "GET", "/pricelist/")

    assert response.status == "200 OK"
    assert [event.kind for event in tape.all] == ["request", "call"]
