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
from wrapture import Aspect, Setting

from . import sessions


class RequestsInstrumentation(wrapture.Instrumentation):
    """Outbound request tracing and trace propagation for requests."""

    description = "Outbound request tracing and trace propagation for requests."

    target = "requests"
    supports = ">=2.31,<3"
    removable = True

    # One aspect, the request boundary, so its keys may be written flat
    # on the entry; a leaf by default, so anything recorded beneath a
    # request stays out of the tree.

    settings = {
        "requests": Aspect(
            "the request boundary: every send through a session",
            primary=True,
            leaf=True,
            propagate=Setting(
                True,
                "add the current trace identity to each request's headers"
                " so the service called can join the trace",
            ),
        ),
    }

    @wrapture.instrumentation_hook("requests.sessions")
    def requests_sessions(self, name: str, module: Any) -> None:
        """Bind the session once requests.sessions exists."""

        sessions.instrument(module, self)
