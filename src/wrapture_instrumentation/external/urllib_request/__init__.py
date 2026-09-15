"""Instrumentation for urllib.request: every outbound request made
through it recorded as an external call, carrying the current
trace identity onward in its headers.

This module imports only wrapture. Everything that touches urllib
lives in the sibling request module, named for the urllib.request
module it patches, importing only wrapture at top level, so loading
this class when a config loads never imports urllib.request ahead of
the hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Aspect, Setting

from . import request


class UrllibInstrumentation(wrapture.Instrumentation):
    """Outbound request tracing and trace propagation for urllib.request."""

    description = "Outbound request tracing and trace propagation for urllib.request."

    # The target is the standard library module the class patches, so
    # its version is the interpreter's and supports is a Python version
    # range: every Python wrapture itself runs on.

    target = "urllib.request"
    supports = ">=3.12"
    removable = True

    # One aspect, the request boundary, so its keys may be written flat
    # on the entry; a leaf by default, so anything recorded beneath a
    # request stays out of the tree.

    settings = {
        "requests": Aspect(
            "the request boundary: every open through an opener",
            primary=True,
            leaf=True,
            propagate=Setting(
                True,
                "add the current trace identity to each request's headers"
                " so the service called can join the trace",
            ),
        ),
    }

    @wrapture.instrumentation_hook("urllib.request")
    def urllib_request(self, name: str, module: Any) -> None:
        """Bind the opener once urllib.request exists."""

        request.instrument(module, self)
