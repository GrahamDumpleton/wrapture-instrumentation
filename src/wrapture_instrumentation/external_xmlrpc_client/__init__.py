"""Instrumentation for xmlrpc.client: every remote procedure call
made through a ServerProxy recorded as an external call, carrying the
current trace identity onward in its request headers.

This module imports only wrapture. Everything that touches
xmlrpc.client lives in the sibling client module, named for the
xmlrpc.client module it patches, importing only wrapture at top
level, so loading this class when a config loads never imports
xmlrpc.client ahead of the hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import client


class XMLRPCClientInstrumentation(wrapture.Instrumentation):
    """Remote call tracing and trace propagation for xmlrpc.client."""

    description = "Remote call tracing and trace propagation for xmlrpc.client."

    # The target is the standard library module the class patches, so
    # its version is the interpreter's and supports is a Python version
    # range: every Python wrapture itself runs on.

    target = "xmlrpc.client"
    supports = ">=3.12"
    removable = True

    settings = {
        "leaf": Setting(
            True,
            "record each remote call as a terminal node, so the"
            " transport work beneath it (including its silent"
            " reconnect retry) stays out of the tree",
        ),
        "propagate": Setting(
            True,
            "add the current trace identity to each request's headers"
            " so the service called can join the trace",
        ),
    }

    @wrapture.instrumentation_hook("xmlrpc.client")
    def xmlrpc_client(self, name: str, module: Any) -> None:
        """Bind the proxy and transport once xmlrpc.client exists."""

        client.instrument(module, self)
