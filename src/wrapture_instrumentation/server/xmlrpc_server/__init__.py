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
from wrapture import Aspect, Setting

from ... import aspects
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
        "requests": Aspect(
            "the request boundary: the POST handler, one event per request",
            primary=True,
            join=Setting(
                True,
                "join the distributed trace an arriving request's"
                " traceparent header carries, rather than minting a fresh"
                " identity per request",
            ),
        ),
        "methods": Aspect(
            "each dispatched procedure, beneath its request",
            capture_args=server.captured,
            capture_result="shape",
        ),
    }

    def configure(self) -> None:
        """Refuse the recording keys the boundary block cannot honour:
        it records no values, so only a stack and leaf apply."""

        aspects.honours(self, "requests", "stack", "leaf")

    @wrapture.instrumentation_hook("xmlrpc.server")
    def xmlrpc_server(self, name: str, module: Any) -> None:
        """Bind the handler and dispatcher once xmlrpc.server exists."""

        server.instrument(module, self)
