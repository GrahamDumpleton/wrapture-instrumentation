"""Instrumentation for uvicorn: every application the server loads is
wrapped in wrapture's recording ASGI middleware, so each request
records as one tree without the application changing at all.

This module imports only wrapture. Everything that touches uvicorn
lives in the sibling config module, named for the uvicorn.config
module it patches, importing only wrapture at top level, so loading
this class when a config loads never imports uvicorn ahead of the
hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import config


class UvicornInstrumentation(wrapture.Instrumentation):
    """Request tracing for applications served by uvicorn."""

    description = "Request tracing for applications served by uvicorn."

    # The target is the uvicorn module the class patches; the version
    # checked against supports is the uvicorn distribution's.

    target = "uvicorn"
    supports = ">=0.30,<1"
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

    @wrapture.instrumentation_hook("uvicorn.config")
    def uvicorn_config(self, name: str, module: Any) -> None:
        """Bind the configuration's application loading once the
        module exists."""

        config.instrument(module, self)
