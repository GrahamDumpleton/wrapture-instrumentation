"""The aiohttp client patch: one binding on ClientSession._request,
the point every outbound request passes through.

The verb helpers (session.get and friends), session.request, and a
streamed request opened with `async with` all end up in
ClientSession._request, the one coroutine that builds the request,
sends it and returns the response, so a single binding there covers
the client whatever spelling the caller used. It is declared an
external leaf: the event is the exchange as the caller sees it, and
the machinery beneath it records nothing of its own. A followed
redirect is not a nested request: aiohttp resolves the hops in a
loop inside the one call, so every request is one event whatever the
leaf setting says, named by the URL the application asked for and
carrying the status of where it ended up. The coroutine returns once
the response headers are in, the body read afterwards (`await
resp.read()`, or streamed inside the `async with`), so the event
covers the exchange to the response's start, not the download.

The event carries the external category's contract keys, filled
from the request's method and URL: method, url (the query string
and any userinfo stripped), host, port, path and query, then status
from the response. aiohttp answers a 4xx or 5xx with a response
rather than an exception (unless raise_for_status was asked for), so
the status is recorded from whatever came back, and the event
carries an exception only when the exchange really failed (a refused
connection, a name that does not resolve), in which case there is no
status. The query is recorded as wrapture.capture_query() gives it:
the built-in sensitive names masked whatever else is said, and the
redact setting's names masked on top. Query parameters supplied
through the `params=` argument rather than in the URL are not folded
into the recording, and the request body is never recorded: the
call's arguments are not captured at all (_request's signature is
wide, and the method and URL it matters on are already the event's
contract keys), and the response reduces to its type.

Propagation is the other half: the current trace identity, from
wrapture.trace_headers(), is added to the request's headers before
it is sent, so a service that understands them joins the trace. A
header the application set itself is left alone, and aiohttp copies
the request's headers onto each redirect hop, so the identity
travels the whole chain. Propagation follows recording: silenced
beneath another target's leaf, the request injects and annotates
nothing.
"""

from __future__ import annotations

from typing import Any

import wrapture

DEFAULT_PORTS = {"http": 80, "https": 443}


def without_query(url: str) -> str:
    """The URL with its query string, fragment and any userinfo
    removed."""

    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    netloc = parts.netloc.rpartition("@")[2]

    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def full_url(instance: Any, url: Any) -> str:
    """The absolute URL the request targets: the argument as given,
    joined onto the session's base_url when it was opened with one and
    the argument is relative."""

    from yarl import URL

    text = str(url)

    base = getattr(instance, "_base_url", None)
    if base is not None:
        try:
            return str(base.join(URL(text)))
        except Exception:
            return text

    return text


def describe(url: str, policy: Any) -> dict[str, Any]:
    """The external contract keys a request URL yields: method is
    added by the caller; host, port, path and query where the URL
    has them, the query recorded through the capture policy."""

    from urllib.parse import urlsplit

    parts = urlsplit(url)

    data: dict[str, Any] = {"url": without_query(url)}

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


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind ClientSession._request as an external call, leaf or not by
    the leaf setting, propagating the trace by the propagate setting;
    register the binding's removal as this trigger's cleanup."""

    settings = instrumentation.settings

    # CIMultiDict is aiohttp's own header container, present wherever
    # aiohttp is; the query policy is redact() with the setting's
    # names, or the reference level, either way on top of the built-in
    # sensitive set.

    from multidict import CIMultiDict

    names = tuple(settings["redact"])
    policy: Any = wrapture.redact(*names) if names else "reference"

    def propagate_into(kwargs: dict[str, Any]) -> None:
        """Add the current trace identity to the request's headers
        keyword, leaving any header the application already set as it
        is. Nothing is added when there is no identity to propagate."""

        headers = wrapture.trace_headers()
        if not headers:
            return

        existing = kwargs.get("headers")
        merged = CIMultiDict(existing) if existing is not None else CIMultiDict()

        for name, value in headers.items():
            if name not in merged:
                merged[name] = value

        kwargs["headers"] = merged

    async def record(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        method = args[0] if args else kwargs.get("method")
        raw_url = args[1] if len(args) > 1 else kwargs.get("str_or_url")

        if method is None or raw_url is None:
            return await wrapped(*args, **kwargs)

        # Propagation and annotation belong to the level that
        # records: silenced beneath another target's leaf, the
        # request must neither inject the leaf's identity downstream
        # nor smear its keys onto the leaf's event.

        owned = bool(wrapture.current_event(binding=request))

        if owned and settings["propagate"]:
            propagate_into(kwargs)

        if owned:
            wrapture.annotate(
                method=str(method), **describe(full_url(instance, raw_url), policy)
            )

        response = await wrapped(*args, **kwargs)

        status = getattr(response, "status", None)
        if owned and status is not None:
            wrapture.annotate(status=status)

        return response

    request = wrapture.binding(
        module.ClientSession,
        "_request",
        leaf=settings["leaf"],
        category="external",
        capture_args="none",
        capture_result="types",
    )
    request.on_call.decorates(record)

    group = wrapture.bindings(request=request)
    group.apply()

    instrumentation.on_cleanup(group.remove)
