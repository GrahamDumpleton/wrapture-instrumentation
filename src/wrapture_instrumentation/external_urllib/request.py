"""The urllib.request patch: one binding on OpenerDirector.open, the
point every request passes through.

urlopen(), urlretrieve(), any opener from build_opener() and the
standard library's own users of urllib all end up in
OpenerDirector.open, so one binding there sees every request. It is
declared an external leaf: the event is the exchange as the caller
sees it, and the opener's own machinery beneath it (the nested open
a redirect or an authentication retry makes, the http.client calls
that do the wire work) records nothing of its own. Unlike a client
library with separate request and response calls, open returns only
once the response headers are in, so the event covers connecting,
sending and waiting for the status line; reading the body happens
afterwards on the response and is not part of it.

The event carries the external category's contract keys, filled
from the Request the opener is handed: method, url (the query string
stripped), host, port, path and query, then status from the response
or from the HTTPError urllib raises for a 4xx or 5xx. The query is
recorded as wrapture.capture_query() gives it, the same form the
request middlewares record inbound: the built-in sensitive names
masked whatever else is said, and the redact setting's names masked
on top. The captured arguments show the URL without its query, so
the query appears in one place, protected; the request body reduces
to its size and the response to its type.

Propagation is the other half: the current trace identity, from
wrapture.trace_headers(), is added to the request's headers before
it is sent, so a service that understands them joins the trace. A
header the application set itself is left alone. The headers go on
as unredirected headers, which urllib drops when it follows a
redirect; the redirected request comes back through open and is
given its own.

A nested open (the one a redirect handler makes) runs beneath the
outer one on the same thread, and beneath a leaf its annotate()
would land on the leaf's own event, replacing the outer request's
URL with the redirect's. The wrapper tracks its own nesting depth,
so a nested open under a leaf still propagates but annotates
nothing; with the leaf setting off, every open is its own event and
annotates itself.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import wrapture

DEFAULT_PORTS = {"http": 80, "https": 443}

# How many opens are in flight on this thread or task, for telling a
# redirect's nested open from the one the application made.

_depth: ContextVar[int] = ContextVar("wrapture_instrumentation.urllib.depth", default=0)


def captured_argument(name: str | None, value: Any) -> Any:
    """The capture policy for open's arguments and result: the target
    reduces to its URL without the query string, the body to its size,
    the timeout passes when it is a number, and the response to its
    type."""

    if name == "fullurl":
        url = value if isinstance(value, str) else getattr(value, "full_url", None)
        if isinstance(url, str):
            return without_query(url)
        return f"<{type(value).__name__}>"

    if name == "data":
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray, memoryview)):
            return f"<{len(value)} bytes>"
        return f"<{type(value).__name__}>"

    if name == "timeout":
        if value is None or isinstance(value, (int, float)):
            return value
        return "<default>"

    if name is None:
        return f"<{type(value).__name__}>"

    return value


def without_query(url: str) -> str:
    """The URL with its query string and fragment removed."""

    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def describe(request: Any, policy: Any) -> dict[str, Any]:
    """The external contract keys a Request yields before it is sent:
    method and url always, host, port, path and query where the URL
    has them, the query recorded through the capture policy."""

    from urllib.parse import urlsplit

    url: str = request.full_url
    parts = urlsplit(url)

    data: dict[str, Any] = {
        "method": request.get_method(),
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

    for header, value in wrapture.trace_headers().items():
        if not request.has_header(header.title()):
            request.add_unredirected_header(header.title(), value)


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind OpenerDirector.open as an external call, leaf or not by the
    leaf setting, propagating the trace by the propagate setting;
    register its removal as this trigger's cleanup."""

    settings = instrumentation.settings

    # The query policy: redact() with the setting's names, or the
    # reference level, either way on top of the built-in sensitive set.

    names = tuple(settings["redact"])
    policy: Any = wrapture.redact(*names) if names else "reference"

    def record(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # Normalise the target to a Request, as open itself does
        # first thing, so the method and headers have somewhere to
        # live; the body given alongside a URL belongs on it too.

        if "fullurl" in kwargs:
            target = kwargs["fullurl"]
        elif args:
            target = args[0]
        else:
            return wrapped(*args, **kwargs)

        if isinstance(target, str):
            if "data" in kwargs:
                body = kwargs["data"]
            elif len(args) > 1:
                body = args[1]
            else:
                body = None

            target = module.Request(target, body)

        if not isinstance(target, module.Request):
            return wrapped(*args, **kwargs)

        if settings["propagate"]:
            propagate_into(target)

        # A nested open beneath a leaf has no event of its own to
        # annotate, and must not overwrite the leaf's.

        nested = _depth.get() > 0
        recording = not (nested and settings["leaf"])

        if recording:
            wrapture.annotate(**describe(target, policy))

        if "fullurl" in kwargs:
            kwargs = dict(kwargs, fullurl=target)
        else:
            args = (target, *args[1:])

        # urllib raises for a 4xx or 5xx, and the raised HTTPError is
        # also the response, so the status is on it either way.

        token = _depth.set(_depth.get() + 1)

        try:
            response = wrapped(*args, **kwargs)
        except module.HTTPError as exc:
            if recording:
                wrapture.annotate(status=exc.code)
            raise
        finally:
            _depth.reset(token)

        status = getattr(response, "status", None)
        if recording and status is not None:
            wrapture.annotate(status=status)

        return response

    opener = wrapture.binding(
        module.OpenerDirector,
        "open",
        leaf=settings["leaf"],
        category="external",
        capture_args=captured_argument,
        capture_result=captured_argument,
    )
    opener.on_call.decorates(record)
    opener.apply()

    instrumentation.on_cleanup(opener.remove)
