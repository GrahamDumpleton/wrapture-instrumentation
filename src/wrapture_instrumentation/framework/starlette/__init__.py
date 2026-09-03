"""Instrumentation for Starlette: request and route tracing for
every application the process creates.

This module imports only wrapture. Everything that touches Starlette
lives in sibling submodules, one per starlette module patched
(applications.py for starlette.applications), each importing only
wrapture at top level, so loading this class when a config loads
never imports Starlette ahead of the hook meant to fire on its
import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import applications, routing


class StarletteInstrumentation(wrapture.Instrumentation):
    """Request and route tracing for Starlette applications."""

    description = "Request and route tracing for Starlette applications."

    target = "starlette"
    supports = ">=0.47,<2"
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

    @wrapture.instrumentation_hook("starlette.applications")
    def starlette_applications(self, name: str, module: Any) -> None:
        """Bind the request boundary once starlette.applications
        exists."""

        applications.instrument(module, self)

    @wrapture.instrumentation_hook("starlette.routing")
    def starlette_routing(self, name: str, module: Any) -> None:
        """Bind route construction and dispatch once starlette.routing
        exists."""

        routing.instrument(module, self)
