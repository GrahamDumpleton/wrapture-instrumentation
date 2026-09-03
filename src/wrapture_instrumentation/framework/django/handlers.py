"""The request boundaries: WSGIHandler and ASGIHandler on their own
__call__.

Django's handler is the WSGI or ASGI callable itself; unlike Flask
there is no attribute holding the application the way wsgi_app does,
so both bindings follow the Starlette shape: decorate __call__
(behaviour only, `when=False`) and delegate each call through
wrapture's recording middleware wrapped around the bound original.
Every request then records as one "request" event named by the
boundary the server actually calls,
django.core.handlers.wsgi:WSGIHandler.__call__ or its asgi twin,
with everything recorded while it is handled nested beneath. The
handler object itself is never modified beyond the cached wrapper
attribute.

One middleware per handler: the wrapper is cached on the instance
itself, so it lives exactly as long as the handler that made it
necessary and the instrumentation keeps nothing alive on its own.
Removal restores __call__, which un-wraps even handlers already
serving; the cached wrapper is then simply never consulted again.

A handler already wrapped from outside (the uvicorn target's
middleware, or any recording middleware a server interposed) still
records one boundary per request: the outer middleware records and
marks the scope, and this one sees the mark and passes through,
wrapture's rule of one request event per request. The route and
endpoint annotations land on whichever middleware recorded.

Unhandled exceptions never fly out of these boundaries on their own:
Django's catch-all turns them into a 500 and the request completes
normally, so the exceptions module notes them against the request
deliberately.

A StreamingHttpResponse body is pulled after the handler returns but
still inside the request event's window: the middleware tracks the
response iterable and closes the event when it is closed, and a
filtered tree keeps the streamed body silenced too.

The request boundary is where distributed trace identity arrives: a
request carrying a `traceparent` header joins the caller's trace,
and the query string is recorded with the built-in sensitive names
masked, plus any the `redact` setting adds. `ignore_paths` becomes a
filter_requests() filter on the middleware's when=, with tree=True,
so an ignored request records nothing at all, its view, queries and
template renders included.
"""

from __future__ import annotations

from typing import Any

import wrapture

from .common import request_options

# The attribute the wrapper is cached under on the handler instance,
# paired with nothing: the bound __call__ it wraps cannot change for
# the life of the instance.

_CACHE = "_wrapture_interposed"


def instrument_wsgi(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind WSGIHandler.__call__ to delegate through the recording
    middleware; register its removal as this trigger's cleanup."""

    request_filter, policy = request_options(instrumentation)

    def boundary(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # One wrapper per handler, built around the bound original on
        # first request; wrapped is bound afresh per call but the
        # underlying method and instance never change.

        middleware = getattr(instance, _CACHE, None) if instance is not None else None

        if middleware is None:
            middleware = wrapture.WSGIMiddleware(
                wrapped,
                when=request_filter,
                tree=request_filter is not None,
                capture_args=policy,
            )

            if instance is not None:
                setattr(instance, _CACHE, middleware)

        return middleware(*args, **kwargs)

    call = wrapture.binding(module.WSGIHandler, "__call__", when=False)
    call.on_call.decorates(boundary)

    group = wrapture.bindings(call=call)
    group.apply()

    instrumentation.on_cleanup(group.remove)


def instrument_asgi(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind ASGIHandler.__call__ to delegate through the recording
    middleware; register its removal as this trigger's cleanup."""

    request_filter, policy = request_options(instrumentation)

    async def boundary(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        middleware = getattr(instance, _CACHE, None) if instance is not None else None

        if middleware is None:
            middleware = wrapture.ASGIMiddleware(
                wrapped,
                when=request_filter,
                tree=request_filter is not None,
                capture_args=policy,
            )

            if instance is not None:
                setattr(instance, _CACHE, middleware)

        return await middleware(*args, **kwargs)

    call = wrapture.binding(module.ASGIHandler, "__call__", when=False)
    call.on_call.decorates(boundary)

    group = wrapture.bindings(call=call)
    group.apply()

    instrumentation.on_cleanup(group.remove)
