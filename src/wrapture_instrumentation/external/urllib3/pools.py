"""The urllib3 patches: one recorder shared by the two doors a
request enters by, each an external leaf.

`PoolManager.urlopen` is the redirect-following entry. A manager,
requests on top of it and the module-level `urllib3.request` all
reach it, and it follows redirects by recursing on itself and does
the work by delegating to a connection pool's `urlopen`.
`HTTPConnectionPool.urlopen` is that lower door, reached directly by
bare-pool code, and it follows redirects and retries by recursing on
itself too. Binding it on the base class covers `HTTPSConnectionPool`
as well, which does not override it.

The two are bound with the one recorder, sharing a single depth count
across the thread or task. The first call, at depth zero whichever
door it is, is the request as the caller sees it: it records the
leaf and carries the trace identity onward. Every call beneath it,
the manager's delegation to a pool, a redirect hop, a retry, is at a
greater depth and, under a leaf, records and annotates nothing, so a
request is one event however deep the machinery goes.

The event carries the external category's contract keys, taken from
the pool instance and the request URL together: the pool knows its
scheme, host and port, and the URL carries the path and query (or,
at the manager door, the whole absolute URL). requests answers a 4xx
or 5xx with a response rather than an exception, and urllib3 hands
the status back the same way, so the status is whatever came back;
the event carries an exception only when the exchange really failed
(a refused connection, a name that did not resolve, retries
exhausted), in which case there is no status. The query is recorded
through wrapture.capture_query(), the built-in sensitive names
masked whatever else is said and the redact setting's names on top.
The call's arguments are not captured (the method and url are already
the contract keys in the event data, and urlopen's wide signature
would spell out every defaulted keyword as noise); the request body
is never recorded and the response reduces to its type.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import wrapture

DEFAULT_PORTS = {"http": 80, "https": 443}

# How many urlopen calls are in flight on this thread or task, shared
# by both doors, for telling the request the caller made from the
# nested calls a redirect, a retry or the manager's delegation makes.

_depth: ContextVar[int] = ContextVar(
    "wrapture_instrumentation.urllib3.depth", default=0
)


def describe(instance: Any, method: Any, url: Any, policy: Any) -> dict[str, Any]:
    """The external contract keys a urlopen call yields, the pool
    instance and the URL read together: method and url always, host,
    port, path and query where they can be found. The pool knows its
    scheme, host and port; the URL carries the path and query, or at
    the manager door the whole absolute URL, whose own host and port
    then win."""

    from urllib.parse import urlsplit

    text = url if isinstance(url, str) else ""
    parts = urlsplit(text)

    scheme = parts.scheme or getattr(instance, "scheme", None) or "http"
    host = parts.hostname or getattr(instance, "host", None)

    try:
        port = parts.port
    except ValueError:
        port = None
    if port is None:
        port = getattr(instance, "port", None)
    if port is None:
        port = DEFAULT_PORTS.get(scheme)

    path = parts.path or "/"

    # The recorded URL is absolute whichever door recorded it: the
    # manager's URL already is, the pool's path is joined to what the
    # pool knows.

    authority = host or ""
    if port is not None and port != DEFAULT_PORTS.get(scheme):
        authority = f"{authority}:{port}"

    data: dict[str, Any] = {
        "method": str(method),
        "url": f"{scheme}://{authority}{path}",
    }

    if host:
        data["host"] = host
    if port is not None:
        data["port"] = port
    if path:
        data["path"] = path
    if parts.query:
        data["query"] = wrapture.capture_query(parts.query, policy)

    return data


def propagate_into(instance: Any, kwargs: dict[str, Any], headers_arg: Any) -> None:
    """Add the current trace identity to the request's headers,
    leaving any header already there. The headers ride as a keyword
    argument; when none was passed, the pool's own default headers are
    the base, so nothing the pool would have sent is dropped."""

    identity = wrapture.trace_headers()

    if not identity:
        return

    base = (
        headers_arg if headers_arg is not None else getattr(instance, "headers", None)
    )
    headers = dict(base or {})

    for name, value in identity.items():
        if name not in headers:
            headers[name] = value

    kwargs["headers"] = headers


def _recorder(instrumentation: wrapture.Instrumentation, binding: Any) -> Any:
    """Build the record function the two doors share, closed over the
    settings, the query policy and the door's own binding."""

    settings = instrumentation.settings

    names = tuple(settings["redact"])
    policy: Any = wrapture.redact(*names) if names else "reference"

    def record(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        method = args[0] if args else kwargs.get("method")
        url = args[1] if len(args) > 1 else kwargs.get("url")

        # A call with no method or URL is not a request being made and
        # passes straight through.

        if method is None or url is None:
            return wrapped(*args, **kwargs)

        # The outermost call is the request the caller made; a nested
        # one under this target's own leaf has no event of its own and
        # must not overwrite the leaf's. Propagation and annotation
        # both belong to the level that records, so silenced beneath
        # another target's leaf the door neither injects the leaf's
        # identity downstream nor smears its keys onto the leaf's
        # event.

        owned = bool(wrapture.current_event(binding=binding))
        recording = owned and not (_depth.get() > 0 and settings["leaf"])

        if recording:
            if settings["propagate"]:
                headers_arg = args[3] if len(args) > 3 else kwargs.get("headers")
                propagate_into(instance, kwargs, headers_arg)

            wrapture.annotate(**describe(instance, method, url, policy))

        token = _depth.set(_depth.get() + 1)

        try:
            response = wrapped(*args, **kwargs)
        finally:
            _depth.reset(token)

        status = getattr(response, "status", None)
        if recording and status is not None:
            wrapture.annotate(status=status)

        return response

    return record


def _bind(owner: Any, instrumentation: wrapture.Instrumentation) -> wrapture.Binding:
    """Bind urlopen on one door as an external leaf with the shared
    recorder; register its removal as this trigger's cleanup."""

    settings = instrumentation.settings

    binding = wrapture.binding(
        owner,
        "urlopen",
        leaf=settings["leaf"],
        category="external",
        capture_args="none",
        capture_result="types",
    )
    binding.on_call.decorates(_recorder(instrumentation, binding))
    binding.apply()

    instrumentation.on_cleanup(binding.remove)

    return binding


def instrument_manager(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind PoolManager.urlopen, the redirect-following entry."""

    _bind(module.PoolManager, instrumentation)


def instrument_pool(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind HTTPConnectionPool.urlopen, the lower door, covering
    HTTPSConnectionPool with it."""

    _bind(module.HTTPConnectionPool, instrumentation)
