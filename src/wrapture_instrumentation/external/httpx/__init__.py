"""Instrumentation for httpx: every outbound request made through
its sync or async clients recorded as an external call, carrying the
current trace identity onward in its headers.

This module imports only wrapture. Everything that touches httpx
lives in the sibling _client module, named for the httpx._client
module it patches, importing only wrapture at top level, so loading
this class when a config loads never imports httpx ahead of the hook
meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import _client


class HTTPXInstrumentation(wrapture.Instrumentation):
    """Outbound request tracing and trace propagation for httpx."""

    description = "Outbound request tracing and trace propagation for httpx."

    target = "httpx"
    supports = ">=0.27,<1"
    removable = True

    settings = {
        "leaf": Setting(
            True,
            "record each send as a terminal node, so anything recorded"
            " beneath it stays out of the tree",
        ),
        "propagate": Setting(
            True,
            "add the current trace identity to each request's headers"
            " so the service called can join the trace",
        ),
        "redact": Setting(
            [],
            "query string parameters to mask by name, on top of the"
            " built-in sensitive set",
        ),
    }

    @wrapture.instrumentation_hook("httpx")
    def httpx_package(self, name: str, module: Any) -> None:
        """Bind both clients once the httpx package has finished
        importing: by then it has stamped its public name onto the
        re-exported classes, so the derived path is the public
        httpx:Client.send in every import order."""

        _client.instrument(module, self)
