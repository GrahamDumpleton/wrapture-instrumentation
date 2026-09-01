"""Instrumentation for urllib: every outbound request made through
urllib.request recorded as an external call, carrying the current
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
from wrapture import Setting

from . import request


class UrllibInstrumentation(wrapture.Instrumentation):
    """Outbound request tracing and trace propagation for urllib."""

    description = "Outbound request tracing and trace propagation for urllib."

    # urllib is part of the standard library, so its version is the
    # interpreter's and supports is a Python version range: every
    # Python wrapture itself runs on.

    target = "urllib"
    supports = ">=3.12"
    removable = True

    settings = {
        "leaf": Setting(
            True,
            "record each open as a terminal node, so the nested opens"
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

    @wrapture.instrumentation_hook("urllib.request")
    def urllib_request(self, name: str, module: Any) -> None:
        """Bind the opener once urllib.request exists."""

        request.instrument(module, self)
