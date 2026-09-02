"""Instrumentation for xmlrpc.server: every XML-RPC POST a
SimpleXMLRPCServer handles recorded as one request boundary that
joins the distributed trace the request arrived with, and every
dispatched procedure recorded beneath it.

This module imports only wrapture. Everything that touches
xmlrpc.server lives in the sibling server module, named for the
xmlrpc.server module it patches, importing only wrapture at top
level, so loading this class when a config loads never imports
xmlrpc.server ahead of the hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import server


class XMLRPCServerInstrumentation(wrapture.Instrumentation):
    """Request and dispatch tracing for xmlrpc.server."""

    description = "Request and dispatch tracing for xmlrpc.server."

    # The target is the standard library module the class patches, so
    # its version is the interpreter's and supports is a Python version
    # range: every Python wrapture itself runs on.

    target = "xmlrpc.server"
    supports = ">=3.12"
    removable = True

    settings = {
        "join": Setting(
            True,
            "join the distributed trace an arriving request's"
            " traceparent header carries, rather than minting a fresh"
            " identity per request",
        ),
    }

    @wrapture.instrumentation_hook("xmlrpc.server")
    def xmlrpc_server(self, name: str, module: Any) -> None:
        """Bind the handler and dispatcher once xmlrpc.server exists."""

        server.instrument(module, self)
