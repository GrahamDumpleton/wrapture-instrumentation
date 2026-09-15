"""Instrumentation for gRPC: every RPC a channel makes recorded as an
external leaf, and every RPC a server handles as a request boundary,
through gRPC's own interceptor machinery injected at the public
factories.

This module imports only wrapture. Everything that touches gRPC lives
in the sibling interceptors module, which also imports only wrapture
at top level (the interceptor classes are built against the grpc
module the hook hands over), so loading this class when a config
loads never imports grpc ahead of the hook meant to fire on its
import.

The client and server halves patch disjoint seams and are each
behind a default-on setting: a process that only ever creates
channels never builds a server interceptor, and either half can be
switched off deliberately.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Aspect, Setting

from ... import aspects
from . import interceptors


class GRPCInstrumentation(wrapture.Instrumentation):
    """Call and handler tracing for gRPC clients and servers."""

    description = "Call and handler tracing for gRPC clients and servers."

    target = "grpc"
    supports = ">=1.76,<2"
    removable = True

    # Two aspects and no primary one: the client side and the server
    # side are peers, each with its own switch and setting.

    settings = {
        "client": Aspect(
            "every RPC made through a channel, as an external leaf",
            propagate=Setting(
                True,
                "add the current trace identity to each outgoing RPC's"
                " metadata so the service called can join the trace",
            ),
        ),
        "server": Aspect(
            "every RPC the server handles, as a request boundary",
            join=Setting(
                True,
                "join the distributed trace an incoming RPC's metadata"
                " carries instead of rooting a new one",
            ),
        ),
    }

    def configure(self) -> None:
        """Refuse the recording keys the server boundary cannot honour:
        the handler runs inside a block, which records no values."""

        aspects.honours(self, "server", "stack", "leaf")

    @wrapture.instrumentation_hook("grpc")
    def grpc(self, name: str, module: Any) -> None:
        """Bind the channel and server factories once grpc exists."""

        interceptors.instrument(module, self)
