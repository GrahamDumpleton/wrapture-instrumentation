"""Instrumentation for wsgiref.simple_server: every application the
server is handed is wrapped in wrapture's recording WSGI middleware,
so each request records as one tree without the application changing
at all.

This module imports only wrapture. Everything that touches
wsgiref.simple_server lives in the sibling simple_server module,
named for the wsgiref.simple_server module it patches, importing
only wrapture at top level, so loading this class when a config
loads never imports wsgiref ahead of the hook meant to fire on its
import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Aspect, Setting

from ... import aspects
from . import simple_server


class WSGIRefSimpleServerInstrumentation(wrapture.Instrumentation):
    """Request tracing for applications served by wsgiref.simple_server."""

    description = "Request tracing for applications served by wsgiref.simple_server."

    # The target is the standard library module the class patches, so
    # its version is the interpreter's and supports is a Python version
    # range: every Python wrapture itself runs on.

    target = "wsgiref.simple_server"
    supports = ">=3.12"
    removable = True

    settings = {
        "requests": Aspect(
            "the request boundary: the application the server was given, one"
            " event per request",
            primary=True,
            ignore_paths=Setting(
                [],
                "request paths not to record, as path globs ('/health', '/static/*')",
            ),
        ),
    }

    def configure(self) -> None:
        """Refuse the recording keys the boundary middleware cannot
        honour."""

        aspects.honours(self, "requests", "capture_args", "capture_result", "leaf")

    @wrapture.instrumentation_hook("wsgiref.simple_server")
    def wsgiref_simple_server(self, name: str, module: Any) -> None:
        """Bind the server's application access once the module exists."""

        simple_server.instrument(module, self)
