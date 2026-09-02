"""Instrumentation for http.client: the wire layer beneath urllib,
urllib3 and xmlrpc.client, recorded phase by phase.

This is a debugging aid rather than default instrumentation. A
higher-level HTTP client's events are terminal nodes, so beneath an
instrumented client nothing here records until that client is
switched to leaf = false; see the README in this directory for the
pairing. Standalone http.client use records with no switch.

This module imports only wrapture. Everything that touches
http.client lives in the sibling client module, named for the
http.client module it patches, importing only wrapture at top level,
so loading this class when a config loads never imports http.client
ahead of the hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import client


class HTTPClientInstrumentation(wrapture.Instrumentation):
    """Wire-level tracing for http.client."""

    description = "Wire-level tracing for http.client."

    # The target is the standard library module the class patches, so
    # its version is the interpreter's and supports is a Python version
    # range: every Python wrapture itself runs on.

    target = "http.client"
    supports = ">=3.12"
    removable = True

    settings = {
        "redact": Setting(
            [],
            "query string parameters to mask by name, on top of the"
            " built-in sensitive set",
        ),
    }

    @wrapture.instrumentation_hook("http.client")
    def http_client(self, name: str, module: Any) -> None:
        """Bind the connection phases once http.client exists."""

        client.instrument(module, self)
