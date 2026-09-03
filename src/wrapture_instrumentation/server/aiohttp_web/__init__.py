"""Instrumentation for aiohttp.web: every request an aiohttp server
handles recorded as one request boundary that joins the distributed
trace the request arrived with, annotated with the matched route,
and every registered handler function observed beneath it.

This module imports only wrapture. Everything that touches aiohttp
lives in the sibling modules, each named for the aiohttp module
whose classes it patches, importing only wrapture at top level, so
loading this class when a config loads never imports aiohttp ahead
of the hook meant to fire on its import. The one trigger is the
public aiohttp.web module, the face every server imports and the
last of the web modules to finish importing, which re-exports both
patched classes.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import web_app, web_urldispatcher


class AiohttpWebInstrumentation(wrapture.Instrumentation):
    """Request and route tracing for aiohttp.web server applications."""

    description = "Request and route tracing for aiohttp.web server applications."

    # The target is the aiohttp module the class patches; the version
    # checked against supports is the aiohttp distribution's.

    target = "aiohttp.web"
    supports = ">=3.10,<4"
    removable = True

    settings = {
        "ignore_paths": Setting(
            [],
            "request paths not to record, as path globs ('/health', '/static/*')",
        ),
        "join": Setting(
            True,
            "join the distributed trace an arriving request's"
            " traceparent header carries, rather than minting a fresh"
            " identity per request",
        ),
        "redact": Setting(
            [],
            "query string parameters to mask by name, on top of the"
            " built-in sensitive set",
        ),
    }

    @wrapture.instrumentation_hook("aiohttp.web")
    def aiohttp_web(self, name: str, module: Any) -> None:
        """Bind the application's request handling and route
        registration once the public web module exists."""

        web_app.instrument(module, self)
        web_urldispatcher.instrument(module, self)
