"""The xmlrpc.server patches: the POST handler as the request
boundary, the dispatcher beneath it, and the response status.

SimpleXMLRPCRequestHandler.do_POST is where an XML-RPC request has
arrived and nothing has been done with it yet: the headers are
parsed, the body is still unread, and everything the server will do
happens inside it. It is bound as behaviour only (`when=False`), and
the behaviour opens a `wrapture.block()` around the handling: the
block is the request boundary, labelled `xmlrpc.server` and
categorised `server`, seeded with the request method, path and
client address plus `system` (`xmlrpc`), and handed the request's
headers as `joins=` so a request carrying a `traceparent` makes the
handling part of the caller's distributed trace, exactly as the WSGI
and ASGI middlewares join at their boundary. A request with no such
header roots a trace of its own, and the `join` setting off never
parses the headers at all; the category, being a declaration of what
the operation is rather than where its identity came from, holds
either way, so wrapture's OpenTelemetry export renders the boundary
as a SERVER span (named access-log style, `POST /RPC2`) whether or
not it joined anything.

SimpleXMLRPCDispatcher._dispatch is where the request has become a
method name and arguments: one event per dispatched procedure,
annotated with the method name as `operation`, beneath the boundary.
A `system.multicall` shows the batch's own dispatch with each
sub-call's dispatch nested inside it, since the stdlib routes each
one back through `_dispatch`. What it does not see is the legacy
escape hatches that bypass `_dispatch`: a handler subclass defining
its own `_dispatch` (the pre-history hook `do_POST` still honours),
and `CGIXMLRPCRequestHandler`, which has no `do_POST` at all; the
boundary still records for the former, nothing does for the latter.

BaseHTTPRequestHandler.send_response is the one door every response
status leaves through: the 200 with a marshalled response, the 404
for a path outside `rpc_paths`, the 500 for an internal error and
the 501 for an unsupported content encoding. It is bound as
behaviour only on SimpleXMLRPCRequestHandler, annotating the status
onto the boundary, and only when the code in flight is inside a
boundary this instrumentation opened, so a documentation server's
GET pages and any unrelated in-flight event are left alone.

The capture policy, the `methods` aspect's declared defaults, mirrors
the client side: the params reduce to a count and the dispatch result
to its shape, both being application data whatever their form; the
request body is never read here at all. A `[instrument.methods]`
table replaces either, or switches the dispatch binding off. A
`Fault` a procedure raises is recorded on its dispatch event as any
exception is, while the response it marshals into is still the 200
the boundary reports, the failure being the application's.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import wrapture

# Whether the code in flight is inside a boundary this instrumentation
# opened, so the status hook annotates that boundary and never some
# unrelated event that happens to be in flight when a response leaves.

_inside: ContextVar[bool] = ContextVar(
    "wrapture_instrumentation_xmlrpc_server_inside", default=False
)


def captured(name: str | None, value: Any) -> Any:
    """Method names pass, params reduce to a count, and every result
    to its type: both are application data, a string included. The
    params arrive as a tuple from `_marshaled_dispatch` and as a list
    on a multicall's sub-calls, straight from the unmarshalled XML."""

    if name == "params" and isinstance(value, (tuple, list)):
        return f"<{len(value)} values>"

    if name is None:
        return f"<{type(value).__name__}>"

    return value


captured.description = "params as a count"  # type: ignore[attr-defined]


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the POST handler as the request boundary, each dispatched
    procedure as an event beneath it, and the response status onto
    the boundary; register their removal as this trigger's cleanup."""

    requests = instrumentation.settings["requests"]
    block_options = {
        key: value
        for key, value in requests.options.items()
        if key in ("leaf", "stack")
    }

    def boundary(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # One block per handled POST, rooted in the handler's thread,
        # joining the trace the request arrived with by the join
        # setting. The headers only ever feed the join parse; none of
        # them are recorded.

        joins = None
        if requests["join"]:
            joins = {str(name): str(value) for name, value in instance.headers.items()}

        data = {
            "system": "xmlrpc",
            "method": str(instance.command),
            "path": str(instance.path),
            "client": str(instance.client_address[0]),
        }

        with wrapture.block(
            "xmlrpc.server",
            category="server",
            data=data,
            joins=joins,
            **block_options,
        ):
            token = _inside.set(True)
            try:
                return wrapped(*args, **kwargs)
            finally:
                _inside.reset(token)

    def dispatch(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        method = args[0] if args else kwargs.get("method")

        if isinstance(method, str):
            wrapture.annotate(operation=method)

        return wrapped(*args, **kwargs)

    def status(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        code = args[0] if args else kwargs.get("code")

        if _inside.get() and isinstance(code, int):
            wrapture.annotate(status=code)

        return wrapped(*args, **kwargs)

    named: dict[str, wrapture.Binding] = {}

    # The requests aspect gates the boundary and the status stamped
    # onto it.

    if requests.enabled:
        handler = wrapture.binding(
            module.SimpleXMLRPCRequestHandler, "do_POST", when=False
        )
        handler.on_call.decorates(boundary)
        named["handler"] = handler

        response = wrapture.binding(
            module.SimpleXMLRPCRequestHandler, "send_response", when=False
        )
        response.on_call.decorates(status)
        named["status"] = response

    # The methods aspect gates the dispatch binding and supplies its
    # recording options, the params-to-count policy and the shape of
    # the result being its declared defaults.

    methods = instrumentation.settings["methods"]
    if methods.enabled:
        dispatched = wrapture.binding(
            module.SimpleXMLRPCDispatcher, "_dispatch", **methods.options
        )
        dispatched.on_call.decorates(dispatch)
        named["dispatch"] = dispatched

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)
