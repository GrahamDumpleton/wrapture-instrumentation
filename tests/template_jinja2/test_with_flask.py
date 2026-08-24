"""The cross-target shape: with framework_flask and template_jinja2
both applied, a request's render shows Flask's call with Jinja2's
work nested beneath it."""

from __future__ import annotations

from importlib import metadata

import pytest
from packaging.version import Version
from wrapture import instrumentation, timeline

# The jinja2 matrix overlays versions below what Flask requires;
# Flask itself is untestable there.

pytestmark = pytest.mark.skipif(
    Version(metadata.version("jinja2")) < Version("3.1.2"),
    reason="installed jinja2 is below Flask's own requirement",
)


def test_the_flask_render_nests_the_jinja2_work() -> None:
    from tests.framework_flask.test_templating import make_pages
    from tests.wsgi import request

    with instrumentation("flask", "jinja2"), timeline() as tape:
        response = request(make_pages(), "GET", "/hello/pat")

    assert response.status == "200 OK"

    labels = [event.label or event.path for event in tape.all]
    assert labels == [
        "pages.wsgi_app",
        "hello",
        "flask.render_template",
        "jinja2.load",
        "jinja2.compile",
        "jinja2.render",
    ]

    render_template = tape.all[2]
    jinja_render = tape.all[5]
    assert tape.parent_of(jinja_render) is render_template
