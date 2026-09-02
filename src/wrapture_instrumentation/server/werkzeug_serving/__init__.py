"""Instrumentation for werkzeug.serving: every application handed to
werkzeug's development server, Flask's app.run() included, is
wrapped in wrapture's recording WSGI middleware, so each request
records as one tree without the application changing at all.

This module imports only wrapture. Everything that touches
werkzeug.serving lives in the sibling serving module, named for the
werkzeug.serving module it patches, importing only wrapture at top
level, so loading this class when a config loads never imports
werkzeug ahead of the hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import serving


class WerkzeugServingInstrumentation(wrapture.Instrumentation):
    """Request tracing for applications served by werkzeug's development server."""

    description = (
        "Request tracing for applications served by werkzeug's development server."
    )

    # The target is the werkzeug module the class patches; the version
    # checked against supports is the werkzeug distribution's.

    target = "werkzeug.serving"
    supports = ">=3.0,<4"
    removable = True

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
    }

    @wrapture.instrumentation_hook("werkzeug.serving")
    def werkzeug_serving(self, name: str, module: Any) -> None:
        """Bind the server's construction once the module exists."""

        serving.instrument(module, self)
