"""Instrumentation for Flask: request and view tracing for every
application the process creates.

This module imports only wrapture. Everything that touches Flask
lives in sibling submodules, one per flask module patched (app.py for
flask.app), each importing only wrapture at top level, so loading
this class when a config loads never imports Flask ahead of the hook
meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import app, blueprints, scaffold, templating


class FlaskInstrumentation(wrapture.Instrumentation):
    """Request and view tracing for Flask applications."""

    # The description defaults to the distribution's summary, which
    # describes the whole collection; each class in a multi-target
    # package says what it alone does.

    description = "Request and view tracing for Flask applications."

    target = "flask"
    supports = ">=3.0,<4"
    removable = True

    # The category switches: which layers of the instrumentation are
    # in play. The request tree, route annotation, view observation
    # and unhandled-exception noting are the point and have no switch.

    settings = {
        "ignore_paths": Setting(
            [],
            "request paths not to record, as path globs ('/health', '/static/*')",
        ),
        "redact": Setting(
            [],
            "query string parameters to mask by name, on top of the"
            " built-in sensitive set",
        ),
        "lifecycle": Setting(
            True,
            "observe before/after/teardown callbacks as they register",
        ),
        "handled_errors": Setting(
            True,
            "note an exception a registered handler absorbed against its request",
        ),
        "templates": Setting(
            True,
            "observe template rendering beneath the view that asked for it",
        ),
    }

    @wrapture.instrumentation_hook("flask.app")
    def flask_app(self, name: str, module: Any) -> None:
        """Patch the Flask class's choke points once flask.app exists."""

        app.instrument(module, self)

    @wrapture.instrumentation_hook("flask.sansio.scaffold")
    def flask_sansio_scaffold(self, name: str, module: Any) -> None:
        """Patch Scaffold's registration methods, shared by
        applications and blueprints, once the module exists."""

        scaffold.instrument(module, self)

    @wrapture.instrumentation_hook("flask.sansio.blueprints")
    def flask_sansio_blueprints(self, name: str, module: Any) -> None:
        """Patch Blueprint's app-level registration methods once the
        module exists."""

        blueprints.instrument(module, self)

    @wrapture.instrumentation_hook("flask")
    def flask_package(self, name: str, module: Any) -> None:
        """Bind the rendering functions once the flask package has
        finished importing: both flask.templating and the namespace
        re-exports exist by then, in every import order."""

        templating.instrument(module, self)
