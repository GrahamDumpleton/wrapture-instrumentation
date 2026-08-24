"""A small Flask shop for the tests, unaware it is being observed.

Nothing here imports wrapture. The application is built by make_app()
rather than at import time, so a test can apply the instrumentation
first and then construct the app, the order the runner guarantees in
real use (the config applies before the application module imports).
The blueprint, the MethodView and the plain views are all registered
from here, which is the "views from elsewhere" shape: every one
reaches Flask.add_url_rule when make_app() registers it.
"""

from __future__ import annotations

from collections.abc import Iterator

from flask import (
    Blueprint,
    Flask,
    Response,
    jsonify,
    render_template,
    render_template_string,
    stream_template,
)
from flask.views import MethodView
from jinja2 import DictLoader

CATALOG = {"widget": 25, "gadget": 120}

TEMPLATES = {
    "pricing.html": (
        "<ul>{% for item, price in catalog %}"
        "<li>{{ item }}: {{ price }}</li>"
        "{% endfor %}</ul>"
    ),
    "pricelist.csv": (
        "{% for item, price in catalog %}{{ item }},{{ price }}\n{% endfor %}"
    ),
}


def quote(item: str) -> dict[str, str | int]:
    """The helper beneath a view, so nesting has something to show."""

    return {"item": item, "price": CATALOG[item]}


def index() -> Response:
    return jsonify(sorted(CATALOG))


def quoted(item: str) -> Response:
    return jsonify(quote(item))


def pricing() -> str:
    """The rendered price list, so template rendering has a view."""

    return render_template("pricing.html", catalog=sorted(CATALOG.items()))


def pricelist() -> Response:
    """The price list as a streamed template render: the template
    yields as it evaluates, and the render event stays open while the
    server consumes the chunks."""

    stream = stream_template("pricelist.csv", catalog=sorted(CATALOG.items()))
    return Response(stream, mimetype="text/csv")


def motd() -> str:
    """A string-template render, the source given inline."""

    return render_template_string(
        "<em>{{ count }} items on sale</em>", count=len(CATALOG)
    )


def export() -> Response:
    """A streaming view: the body is a generator the server consumes."""

    def rows() -> Iterator[str]:
        for item in sorted(CATALOG):
            yield f"{item},{CATALOG[item]}\n"

    return Response(rows(), mimetype="text/csv")


reports = Blueprint("reports", __name__, url_prefix="/reports")


@reports.route("/summary")
def summary() -> Response:
    return jsonify({"items": len(CATALOG)})


class CatalogView(MethodView):
    """A class-based view, registered through as_view()."""

    def get(self) -> Response:
        return jsonify(CATALOG)


def make_app(name: str = "shop") -> Flask:
    """Build the application, registering every kind of view."""

    app = Flask(name)
    app.jinja_env.loader = DictLoader(TEMPLATES)

    app.add_url_rule("/", "index", index)
    app.add_url_rule("/pricing", "pricing", pricing)
    app.add_url_rule("/pricelist", "pricelist", pricelist)
    app.add_url_rule("/motd", "motd", motd)
    app.add_url_rule("/quote/<item>", view_func=quoted)
    app.add_url_rule("/export", "export", export)
    app.add_url_rule("/catalog", view_func=CatalogView.as_view("catalog"))
    app.register_blueprint(reports)

    return app
