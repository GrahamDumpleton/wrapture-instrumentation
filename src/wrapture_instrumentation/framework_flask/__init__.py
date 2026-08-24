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

from . import app


class FlaskInstrumentation(wrapture.Instrumentation):
    """Request and view tracing for Flask applications."""

    # The description defaults to the distribution's summary, which
    # describes the whole collection; each class in a multi-target
    # package says what it alone does.

    description = "Request and view tracing for Flask applications."

    target = "flask"
    supports = ">=3.0,<4"
    removable = True

    @wrapture.instrumentation_hook("flask.app")
    def flask_app(self, name: str, module: Any) -> None:
        """Patch the Flask class's choke points once flask.app exists."""

        app.instrument(module, self)
