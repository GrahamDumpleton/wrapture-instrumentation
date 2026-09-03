"""The httpx patches: one binding each on Client.send and
AsyncClient.send, the points every request passes through.

The module-level helpers (httpx.get and friends), Client.request,
the streaming forms and a send the application makes itself all end
up in Client.send, and their async spellings in AsyncClient.send;
the two methods mirror each other exactly, so the async binding is
the sync one with an await in it. The classes live in httpx._client,
but the binding waits for the httpx package to finish importing:
httpx stamps its public name onto the re-exported classes as its
last act, so binding then derives the stable public path,
httpx:Client.send, in every import order. Each is declared an
external leaf:
the event is the exchange as the caller sees it, and the machinery
beneath it records nothing of its own. Unlike requests, a followed
redirect is not a nested send: httpx resolves the hops in a loop
inside the one call, so every send is one event whatever the leaf
setting says, named by the URL the application asked for and
carrying the status of where it ended up. httpx reads the whole
body before send returns unless the caller asked to stream, so the
event covers the exchange, download included; with stream=True it
ends when the headers are in.

The event carries the external category's contract keys, filled
from the Request the client is handed: method, url (the query
string and any userinfo stripped), host, port, path and query, then
status from the response. httpx answers a 4xx or 5xx with a
response rather than an exception, so the status is recorded from
whatever came back, and the event carries an exception only when
the exchange really failed (a refused connection, a name that does
not resolve, too many redirects), in which case there is no status.
The query is recorded as wrapture.capture_query() gives it, the
same form the request middlewares record inbound: the built-in
sensitive names masked whatever else is said, and the redact
setting's names masked on top. The captured request argument shows
the URL without its query, so the query appears in one place,
protected; the request body is never recorded, and the response
reduces to its type.

Propagation is the other half: the current trace identity, from
wrapture.trace_headers(), is added to the request's headers before
it is sent, so a service that understands them joins the trace.
Propagation follows recording: silenced beneath another target's
leaf, the send injects and annotates nothing. A
header the application set itself is left alone. A redirect hop's
request copies the headers of the one before it, so the identity
travels on every hop.
"""

from __future__ import annotations

from typing import Any

import wrapture

DEFAULT_PORTS = {"http": 80, "https": 443}


def captured_argument(name: str | None, value: Any) -> Any:
    """The capture policy for send's arguments and result: the request
    reduces to its URL without the query string or userinfo, plain
    scalars pass, and everything else (an auth object, the client
    default marker, the response) reduces to its type."""

    if name == "request":
        url = getattr(value, "url", None)
        if url is not None:
            return without_query(str(url))
        return f"<{type(value).__name__}>"

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    return f"<{type(value).__name__}>"


def without_query(url: str) -> str:
    """The URL with its query string, fragment and any userinfo
    removed."""

    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    netloc = parts.netloc.rpartition("@")[2]

    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def describe(request: Any, policy: Any) -> dict[str, Any]:
    """The external contract keys a Request yields before it is sent:
    method and url always, host, port, path and query where the URL
    has them, the query recorded through the capture policy."""

    from urllib.parse import urlsplit

    url = str(request.url)
    parts = urlsplit(url)

    data: dict[str, Any] = {
        "method": str(request.method),
        "url": without_query(url),
    }

    if parts.hostname:
        data["host"] = parts.hostname

        # An unparseable port is the URL's problem, not the trace's.

        try:
            port = parts.port
        except ValueError:
            port = None

        if port is None:
            port = DEFAULT_PORTS.get(parts.scheme)

        if port is not None:
            data["port"] = port

    if parts.path:
        data["path"] = parts.path

    if parts.query:
        data["query"] = wrapture.capture_query(parts.query, policy)

    return data


def propagate_into(request: Any) -> None:
    """Add the current trace identity to the request's headers, leaving
    any header the application already set as it is."""

    headers = request.headers

    for name, value in wrapture.trace_headers().items():
        if name not in headers:
            headers[name] = value


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind Client.send and AsyncClient.send as external calls, leaf
    or not by the leaf setting, propagating the trace by the propagate
    setting; register the group's removal as this trigger's cleanup."""

    settings = instrumentation.settings

    # The query policy: redact() with the setting's names, or the
    # reference level, either way on top of the built-in sensitive set.

    names = tuple(settings["redact"])
    policy: Any = wrapture.redact(*names) if names else "reference"

    def opening(binding: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        """The shared front half of both wrappers: pick out the
        request, propagate into it and annotate the contract keys,
        or return None when the call carries no request or the
        binding did not record."""

        request = args[0] if args else kwargs.get("request")

        if getattr(request, "url", None) is None:
            return None

        # Propagation and annotation belong to the level that
        # records: silenced beneath another target's leaf, the send
        # must neither inject the leaf's identity downstream nor
        # smear its keys onto the leaf's event.

        if not wrapture.current_event(binding=binding):
            return None

        if settings["propagate"]:
            propagate_into(request)

        wrapture.annotate(**describe(request, policy))

        return request

    def closing(response: Any) -> None:
        """The shared back half: the status of whatever came back.
        httpx answers an error status with a response, so the status
        is recorded from it; an exception means there never was one."""

        status = getattr(response, "status_code", None)
        if status is not None:
            wrapture.annotate(status=status)

    def record(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        if opening(send, args, kwargs) is None:
            return wrapped(*args, **kwargs)

        response = wrapped(*args, **kwargs)
        closing(response)

        return response

    async def record_async(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        if opening(send_async, args, kwargs) is None:
            return await wrapped(*args, **kwargs)

        response = await wrapped(*args, **kwargs)
        closing(response)

        return response

    send = wrapture.binding(
        module.Client,
        "send",
        leaf=settings["leaf"],
        category="external",
        capture_args=captured_argument,
        capture_result=captured_argument,
    )
    send.on_call.decorates(record)

    send_async = wrapture.binding(
        module.AsyncClient,
        "send",
        leaf=settings["leaf"],
        category="external",
        capture_args=captured_argument,
        capture_result=captured_argument,
    )
    send_async.on_call.decorates(record_async)

    group = wrapture.bindings(send=send, send_async=send_async)
    group.apply()

    instrumentation.on_cleanup(group.remove)
