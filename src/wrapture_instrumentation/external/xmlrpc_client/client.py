"""The xmlrpc.client patches: the remote call on ServerProxy, and the
transport beneath it.

ServerProxy._ServerProxy__request is the one door every remote call
passes through, however it was spelled (attribute access, dotted
method names, a MultiCall), and it is where the call is still a
method name and arguments rather than an XML body. It is declared an
external leaf: one event per remote call, annotated with the
external contract keys (method is POST, the one verb XML-RPC uses;
url, host, port and path from where the proxy points; status 200 on
any parsed response, a Fault included, or the code a ProtocolError
carries) plus the RPC pair the path cannot say: `system`, always
`xmlrpc`, and the method name as `operation`. wrapture's
OpenTelemetry export maps the pair to `rpc.system` and `rpc.method`
and names the span by the operation. The private name is the honest
choke point, and the recorded path says exactly where the patch
lives.

Transport.request is bound as a plain event, not categorised and not
a leaf: beneath the default leaf it is silent, and with the leaf
setting off it shows the transport's own extent, including the
silent retry it makes when a kept-alive connection has gone cold
(visible as doubled wire work beneath one transport event when the
http.client instrumentation is enabled as well).

The capture policy is deliberate about sensitive data: a proxy URI
may carry basic-auth credentials in its netloc, so recorded hosts
are stripped of any userinfo; the call's params and result are
application data and reduce to a count and a type; the XML request
body reduces to its size; a handler path's query string, rare but
possible, is not recorded.

Propagation is the other half: Transport.send_headers is given every
header the request will carry, so the current trace identity from
wrapture.trace_headers() is appended there, unless a header of the
same name was already supplied (a ServerProxy(headers=...) the
application set itself). Behaviour still applies beneath this
target's own leaf, so propagation does not depend on the leaf
setting; but it does follow recording: silenced beneath another
target's leaf, the call injects and annotates nothing, so a leaf
that does not propagate at its own level sends no identity
downstream.
"""

from __future__ import annotations

from typing import Any

import wrapture


def cleaned_host(netloc: str) -> str:
    """The host[:port] of a netloc, with any userinfo removed."""

    return netloc.rpartition("@")[2]


def captured(name: str | None, value: Any) -> Any:
    """Method names pass, params reduce to a count, hosts lose their
    userinfo, bodies reduce to sizes, and every result to its type:
    a result is application data whatever its type, a string
    included."""

    if name == "params" and isinstance(value, tuple):
        return f"<{len(value)} values>"

    if name == "host" and isinstance(value, str):
        return cleaned_host(value)

    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>"

    if name is None:
        return f"<{type(value).__name__}>"

    return value


def describe(module: Any, proxy: Any, methodname: str) -> dict[str, Any]:
    """The external contract keys a proxy's call yields before it is
    sent, plus the RPC system and the method name as operation."""

    host = cleaned_host(proxy._ServerProxy__host)
    path = str(proxy._ServerProxy__handler).partition("?")[0]
    scheme = (
        "https"
        if isinstance(proxy._ServerProxy__transport, module.SafeTransport)
        else "http"
    )

    data: dict[str, Any] = {
        "system": "xmlrpc",
        "operation": methodname,
        "method": "POST",
        "url": f"{scheme}://{host}{path}",
        "path": path,
    }

    hostname, _, port = host.rpartition(":")
    if hostname and port.isdigit():
        data["host"] = hostname
        data["port"] = int(port)
    else:
        data["host"] = host
        data["port"] = 443 if scheme == "https" else 80

    return data


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the remote call as an external leaf (or not, by the leaf
    setting), the transport as a plain event, and the header hook for
    propagation; register their removal as this trigger's cleanup."""

    settings = instrumentation.settings

    def record(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        methodname = args[0] if args else kwargs.get("methodname")

        # Annotation belongs to the level that records: silenced
        # beneath another target's leaf, the call must not smear its
        # keys onto the leaf's event.

        owned = bool(wrapture.current_event(binding=call))

        if owned and isinstance(methodname, str):
            wrapture.annotate(**describe(module, instance, methodname))

        # Any parsed response was a 200, a Fault included; a
        # ProtocolError carries the status that stopped it; anything
        # else (a socket error, say) never had one.

        try:
            outcome = wrapped(*args, **kwargs)
        except module.Fault:
            if owned:
                wrapture.annotate(status=200)
            raise
        except module.ProtocolError as error:
            if owned:
                wrapture.annotate(status=error.errcode)
            raise

        if owned:
            wrapture.annotate(status=200)
        return outcome

    def inject(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        # send_headers(connection, headers): append the trace pairs to
        # the header list unless the application already supplied one
        # of the same name.

        if len(args) < 2 or not isinstance(args[1], list):
            return args, kwargs

        # Propagation follows recording: the headers are appended
        # only when the remote call's own binding recorded, so
        # silenced beneath another target's leaf nothing is injected.

        if not wrapture.current_event(binding=call):
            return args, kwargs

        headers: list[tuple[str, str]] = args[1]
        present = {str(name).casefold() for name, _ in headers}

        added = [
            (name.title(), value)
            for name, value in wrapture.trace_headers().items()
            if name.casefold() not in present
        ]

        return (args[0], headers + added, *args[2:]), kwargs

    call = wrapture.binding(
        module.ServerProxy,
        "_ServerProxy__request",
        leaf=settings["leaf"],
        category="external",
        capture_args=captured,
        capture_result=captured,
    )
    call.on_call.decorates(record)

    transport = wrapture.binding(
        module.Transport,
        "request",
        capture_args=captured,
        capture_result=captured,
    )

    named: dict[str, wrapture.Binding] = {"call": call, "transport": transport}

    if settings["propagate"]:
        headers = wrapture.binding(module.Transport, "send_headers", when=False)
        headers.on_call.transforms_args(inject)
        named["headers"] = headers

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)
