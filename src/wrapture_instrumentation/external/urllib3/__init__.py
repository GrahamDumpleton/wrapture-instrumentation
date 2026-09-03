"""Instrumentation for urllib3: every outbound request made through a
connection pool or a pool manager recorded as an external call,
carrying the current trace identity onward in its headers.

This module imports only wrapture. Everything that touches urllib3
lives in the sibling pools module, importing only wrapture at top
level, so loading this class when a config loads never imports
urllib3 ahead of the hooks meant to fire on its import.

Two hooks patch the two doors a request can enter by: the pool
manager's `urlopen`, the redirect-following entry a manager, requests
and the module-level `urllib3.request` all use, and the connection
pool's `urlopen` beneath it, the entry bare-pool code uses directly.
One shared depth count across the two keeps a request to one leaf
whichever door it entered by, the nested calls a redirect, a retry or
the manager-to-pool delegation make folded into it.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import pools


class Urllib3Instrumentation(wrapture.Instrumentation):
    """Outbound request tracing and trace propagation for urllib3."""

    description = "Outbound request tracing and trace propagation for urllib3."

    target = "urllib3"
    supports = ">=1.26,<3"
    removable = True

    settings = {
        "leaf": Setting(
            True,
            "record each request as a terminal node, so the nested"
            " calls behind a redirect, a retry or the manager's"
            " delegation to a pool, and anything recorded beneath it,"
            " stay out of the tree",
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

    @wrapture.instrumentation_hook("urllib3.poolmanager")
    def urllib3_poolmanager(self, name: str, module: Any) -> None:
        """Bind PoolManager.urlopen once urllib3.poolmanager exists."""

        pools.instrument_manager(module, self)

    @wrapture.instrumentation_hook("urllib3.connectionpool")
    def urllib3_connectionpool(self, name: str, module: Any) -> None:
        """Bind HTTPConnectionPool.urlopen once urllib3.connectionpool
        exists."""

        pools.instrument_pool(module, self)
