"""The starlette.applications patch: the request boundary on the
Starlette class's own __call__.

Starlette.__call__ is the application: servers call the instance
itself, there is no attribute holding the ASGI callable the way
Flask's wsgi_app holds the WSGI one, so the binding decorates
__call__ (behaviour only, `when=False`) and delegates each call to
wrapture's recording ASGIMiddleware wrapped around the bound
original. Every request then records as one "request" event, named
`starlette.applications:Starlette.__call__`, the boundary the server
actually calls, with everything recorded while it is handled nested
beneath. The application object itself is never modified beyond the
cached wrapper attribute.

One middleware per application: the wrapper is cached on the
instance itself, so it lives exactly as long as the application that
made it necessary and the instrumentation keeps nothing alive on its
own (the wsgiref target's reasoning at the same kind of seam).
Removal restores __call__, which un-wraps even applications already
serving; the cached wrapper is then simply never consulted again.

An application already wrapped from outside (the uvicorn target's
middleware, or any recording middleware a server interposed) still
records one boundary per request: the outer middleware records and
marks the scope, and this one sees the mark and passes through,
wrapture's rule of one request event per request. The route and
endpoint annotations land on whichever middleware recorded.

Unhandled exceptions need no binding of their own: starlette's
ServerErrorMiddleware always re-raises after answering 500, so the
exception flies out through this boundary and is recorded on the
request event beside the status. An HTTPException is turned into its
response by starlette's ExceptionMiddleware inside the stack, and
records as nothing but the status it produced: control flow, not a
failure.

The request boundary is where distributed trace identity arrives: a
request carrying a `traceparent` header joins the caller's trace,
and the query string is recorded with the built-in sensitive names
masked, plus any the `redact` setting adds. `ignore_paths` becomes a
filter_requests() filter on the middleware's when=, with tree=True,
so an ignored request records nothing at all, beneath it included.
"""

from __future__ import annotations

from typing import Any

import wrapture

# The attribute the wrapper is cached under on the application
# instance, paired with nothing: the bound __call__ it wraps cannot
# change for the life of the instance.

_CACHE = "_wrapture_interposed"


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind Starlette.__call__ to delegate through the recording
    middleware; register its removal as this trigger's cleanup."""

    settings = instrumentation.settings

    # The settings become the middleware's own options, built once:
    # ignored paths a filter on when= (tree=True so a declined request
    # silences its whole extent), redacted names a capture policy on
    # top of the built-in sensitive set.

    request_filter = (
        wrapture.filter_requests(ignore={"path": list(settings["ignore_paths"])})
        if settings["ignore_paths"]
        else None
    )

    policy = wrapture.redact(*settings["redact"]) if settings["redact"] else None

    async def boundary(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # One wrapper per application, built around the bound original
        # on first request; wrapped is bound afresh per call but the
        # underlying method and instance never change.

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

    call = wrapture.binding(module.Starlette, "__call__", when=False)
    call.on_call.decorates(boundary)

    group = wrapture.bindings(call=call)
    group.apply()

    instrumentation.on_cleanup(group.remove)
