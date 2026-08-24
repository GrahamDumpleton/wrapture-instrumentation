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

from flask import Blueprint, Flask, Response, jsonify
from flask.views import MethodView

CATALOG = {"widget": 25, "gadget": 120}


def quote(item: str) -> dict[str, str | int]:
    """The helper beneath a view, so nesting has something to show."""

    return {"item": item, "price": CATALOG[item]}


def index() -> Response:
    return jsonify(sorted(CATALOG))


def quoted(item: str) -> Response:
    return jsonify(quote(item))


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

    app.add_url_rule("/", "index", index)
    app.add_url_rule("/quote/<item>", view_func=quoted)
    app.add_url_rule("/export", "export", export)
    app.add_url_rule("/catalog", view_func=CatalogView.as_view("catalog"))
    app.register_blueprint(reports)

    return app
