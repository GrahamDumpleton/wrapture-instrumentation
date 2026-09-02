"""A small Flask portal for the lifecycle and error handler tests,
unaware it is being observed.

Where shop.py exercises routing and views, this application registers
every kind of lifecycle callback and error handler: app-level
before/after/teardown functions, an application context teardown, a
blueprint with both a blueprint-local before_request and app-level
variants, and handlers for an exception class and an HTTP status.
Everything registers inside make_portal(), after the instrumentation
has applied, the order the runner guarantees in real use.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Flask, Response, jsonify


def only_admin_routes() -> None:
    """A blueprint-local before_request: runs for admin routes only."""


def every_request() -> None:
    """A blueprint app-level before_app_request: runs for all routes."""


def audit_request() -> None:
    """An app-level before_request."""


def stamp_response(response: Response) -> Response:
    """An app-level after_request."""

    response.headers["X-Portal"] = "stamped"
    return response


def request_done(exc: BaseException | None) -> None:
    """An app-level teardown_request."""


def context_done(exc: BaseException | None) -> None:
    """An app-level teardown_appcontext."""


def shaky_handler(error: Exception) -> tuple[Response, int]:
    """The registered handler for ValueError: absorbs the failure and
    answers 422."""

    return jsonify({"error": str(error)}), 422


def missing_handler(error: Exception) -> tuple[Response, int]:
    """The registered handler for 404: shapes the not-found response."""

    return jsonify({"error": "no such page"}), 404


def panel() -> Response:
    return jsonify({"admin": True})


def index() -> Response:
    return jsonify({"portal": True})


def shaky() -> Any:
    raise ValueError("bad input")


def broken() -> Any:
    raise KeyError("wiring")


def make_portal(name: str = "portal") -> Flask:
    """Build the application, registering every kind of callback."""

    app = Flask(name)

    app.add_url_rule("/", "index", index)
    app.add_url_rule("/shaky", "shaky", shaky)
    app.add_url_rule("/broken", "broken", broken)

    app.before_request(audit_request)
    app.after_request(stamp_response)
    app.teardown_request(request_done)
    app.teardown_appcontext(context_done)

    # The blueprint is built per application: a blueprint refuses new
    # registrations once it has been registered, so a module-level one
    # could not be reused across the applications the tests build.

    admin = Blueprint("admin", __name__, url_prefix="/admin")
    admin.add_url_rule("/panel", "panel", panel)
    admin.before_request(only_admin_routes)
    admin.before_app_request(every_request)
    app.register_blueprint(admin)

    app.register_error_handler(ValueError, shaky_handler)
    app.register_error_handler(404, missing_handler)

    return app
