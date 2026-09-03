"""Instrumentation for requests: every outbound request made through
it recorded as an external call, carrying the current trace identity
onward in its headers.

This module imports only wrapture. Everything that touches requests
lives in the sibling sessions module, named for the requests.sessions
module it patches, importing only wrapture at top level, so loading
this class when a config loads never imports requests ahead of the
hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import sessions


class RequestsInstrumentation(wrapture.Instrumentation):
    """Outbound request tracing and trace propagation for requests."""

    description = "Outbound request tracing and trace propagation for requests."

    target = "requests"
    supports = ">=2.31,<3"
    removable = True

    settings = {
        "leaf": Setting(
            True,
            "record each send as a terminal node, so the nested sends"
            " behind a redirect and anything recorded beneath it stay"
            " out of the tree",
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

    @wrapture.instrumentation_hook("requests.sessions")
    def requests_sessions(self, name: str, module: Any) -> None:
        """Bind the session once requests.sessions exists."""

        sessions.instrument(module, self)
