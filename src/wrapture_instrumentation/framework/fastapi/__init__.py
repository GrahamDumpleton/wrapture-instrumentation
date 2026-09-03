"""Instrumentation for FastAPI: request and route tracing for every
application the process creates.

This module imports only wrapture. Everything that touches FastAPI
lives in sibling submodules, one per fastapi module patched
(applications.py for fastapi.applications), each importing only
wrapture at top level, so loading this class when a config loads
never imports FastAPI ahead of the hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import applications, routing


class FastAPIInstrumentation(wrapture.Instrumentation):
    """Request and route tracing for FastAPI applications."""

    description = "Request and route tracing for FastAPI applications."

    target = "fastapi"
    supports = ">=0.110,<1"
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

    @wrapture.instrumentation_hook("fastapi.applications")
    def fastapi_applications(self, name: str, module: Any) -> None:
        """Bind the request boundary once fastapi.applications
        exists."""

        applications.instrument(module, self)

    @wrapture.instrumentation_hook("fastapi.routing")
    def fastapi_routing(self, name: str, module: Any) -> None:
        """Bind route construction and dispatch once fastapi.routing
        exists."""

        routing.instrument(module, self)
