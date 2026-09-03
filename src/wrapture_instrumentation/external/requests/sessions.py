"""The requests patch: one binding on Session.send, the point every
request passes through.

The module-level helpers (requests.get and friends), Session.request
and a send the application makes itself all end up in Session.send,
so one binding there sees every request. It is declared an external
leaf: the event is the exchange as the caller sees it, and the
machinery beneath it (the nested send each redirect hop makes, the
urllib3 and http.client calls that do the wire work) records nothing
of its own. requests reads the whole body before send returns unless
the caller asked to stream, so the event covers the exchange,
download included; with stream=True it ends when the headers are in,
and reading the body afterwards is not part of it.

The event carries the external category's contract keys, filled from
the PreparedRequest the session is handed: method, url (the query
string and any userinfo stripped), host, port, path and query, then
status from the response. requests answers a 4xx or 5xx with a
response rather than an exception, so the status is recorded from
whatever came back, and the event carries an exception only when the
exchange really failed (a refused connection, a name that does not
resolve, too many redirects), in which case there is no status. The
query is recorded as wrapture.capture_query() gives it, the same
form the request middlewares record inbound: the built-in sensitive
names masked whatever else is said, and the redact setting's names
masked on top. The captured request argument shows the URL without
its query, so the query appears in one place, protected; the request
body is never recorded, and the response reduces to its type.

Propagation is the other half: the current trace identity, from
wrapture.trace_headers(), is added to the request's headers before
it is sent, so a service that understands them joins the trace. A
header the application set itself is left alone. A redirect hop's
request is a copy of the outer one, headers included, so the
identity travels on every hop as the header already present.
Propagation follows recording: silenced beneath another target's
leaf, the send injects nothing, so a leaf that does not propagate at
its own level sends no identity downstream.

A nested send (the one a redirect hop makes) runs beneath the outer
one on the same thread, and beneath a leaf its annotate() would land
on the leaf's own event, replacing the outer request's URL with the
redirect's. The wrapper tracks its own nesting depth, so a nested
send under a leaf still runs, with the headers the hop copied, and
annotates nothing; with the leaf setting off, every send is its own
event and annotates itself.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import wrapture

DEFAULT_PORTS = {"http": 80, "https": 443}

# How many sends are in flight on this thread or task, for telling a
# redirect hop's nested send from the one the application made.

_depth: ContextVar[int] = ContextVar(
    "wrapture_instrumentation.requests.depth", default=0
)


def captured_argument(name: str | None, value: Any) -> Any:
    """The capture policy for send's arguments and result: the request
    reduces to its URL without the query string or userinfo, send's
    options arrive as one kwargs mapping and are captured one level
    down through the same rules, plain scalars pass, and everything
    else (the proxies mapping, a timeout tuple, the response) reduces
    to its type."""

    if name == "request":
        url = getattr(value, "url", None)
        if isinstance(url, str):
            return without_query(url)
        return f"<{type(value).__name__}>"

    if name == "kwargs" and isinstance(value, dict):
        return {key: captured_argument(key, item) for key, item in value.items()}

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
    """The external contract keys a PreparedRequest yields before it
    is sent: method and url always, host, port, path and query where
    the URL has them, the query recorded through the capture policy."""

    from urllib.parse import urlsplit

    url: str = request.url
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
    any header already there, whether the application set it or a
    redirect hop copied it, as it is."""

    headers = request.headers

    for name, value in wrapture.trace_headers().items():
        if name not in headers:
            headers[name] = value


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind Session.send as an external call, leaf or not by the leaf
    setting, propagating the trace by the propagate setting; register
    its removal as this trigger's cleanup."""

    settings = instrumentation.settings

    # The query policy: redact() with the setting's names, or the
    # reference level, either way on top of the built-in sensitive set.

    names = tuple(settings["redact"])
    policy: Any = wrapture.redact(*names) if names else "reference"

    def record(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # The one positional argument is the PreparedRequest; a call
        # carrying anything else is not a request being sent and
        # passes straight through.

        request = args[0] if args else kwargs.get("request")

        if not isinstance(getattr(request, "url", None), str):
            return wrapped(*args, **kwargs)

        # Propagation and annotation belong to the level that
        # records: silenced beneath another target's leaf, this
        # binding must neither inject the leaf's identity downstream
        # nor smear its keys onto the leaf's event.

        owned = bool(wrapture.current_event(binding=send))

        if owned and settings["propagate"]:
            propagate_into(request)

        # A nested send beneath this target's own leaf has no event
        # of its own to annotate, and must not overwrite the leaf's.

        nested = _depth.get() > 0
        recording = owned and not (nested and settings["leaf"])

        if recording:
            wrapture.annotate(**describe(request, policy))

        # requests answers an error status with a response, so the
        # status is whatever came back; an exception means there
        # never was one.

        token = _depth.set(_depth.get() + 1)

        try:
            response = wrapped(*args, **kwargs)
        finally:
            _depth.reset(token)

        status = getattr(response, "status_code", None)
        if recording and status is not None:
            wrapture.annotate(status=status)

        return response

    send = wrapture.binding(
        module.Session,
        "send",
        leaf=settings["leaf"],
        category="external",
        capture_args=captured_argument,
        capture_result=captured_argument,
    )
    send.on_call.decorates(record)
    send.apply()

    instrumentation.on_cleanup(send.remove)
