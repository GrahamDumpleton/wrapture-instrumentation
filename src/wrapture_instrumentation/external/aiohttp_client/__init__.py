"""Instrumentation for aiohttp's client: every outbound request made
through a ClientSession recorded as an external call, carrying the
current trace identity onward in its headers.

This module imports only wrapture. Everything that touches aiohttp
lives in the sibling client module, named for the aiohttp.client
module it patches, importing only wrapture at top level, so loading
this class when a config loads never imports aiohttp ahead of the
hook meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Aspect, Setting

from . import client


class AiohttpClientInstrumentation(wrapture.Instrumentation):
    """Outbound request tracing and trace propagation for aiohttp's client."""

    description = "Outbound request tracing and trace propagation for aiohttp's client."

    # The target is the aiohttp module the class patches; the version
    # checked against supports is the aiohttp distribution's.

    target = "aiohttp.client"
    supports = ">=3.10,<4"
    removable = True

    # One aspect, the request boundary, so its keys may be written flat
    # on the entry; a leaf by default, so anything recorded beneath a
    # request stays out of the tree.

    settings = {
        "requests": Aspect(
            "the request boundary: every request a client session makes",
            primary=True,
            leaf=True,
            propagate=Setting(
                True,
                "add the current trace identity to each request's headers"
                " so the service called can join the trace",
            ),
        ),
    }

    @wrapture.instrumentation_hook("aiohttp.client")
    def aiohttp_client(self, name: str, module: Any) -> None:
        """Bind ClientSession._request once the client module exists."""

        client.instrument(module, self)
