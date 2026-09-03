"""The fastapi.applications patch: the request boundary on the
FastAPI class's own __call__.

FastAPI subclasses Starlette and, like it, is called as the
application itself, so the binding decorates FastAPI.__call__
(behaviour only, `when=False`) and delegates each call to wrapture's
recording ASGIMiddleware wrapped around the bound original, exactly
the starlette target's seam one class down. Every request then
records as one "request" event, named
`fastapi.applications:FastAPI.__call__`, with everything recorded
while it is handled nested beneath.

One middleware per application, cached on the instance, under an
attribute of this target's own: the starlette target caches its
wrapper the same way, and with both instrumentations applied the two
boundaries stack (this one outermost, the starlette one reached
through super().__call__), so sharing the attribute would hand one
target's wrapper to the other and loop. Distinct attributes keep
each binding's cache its own; the scope marker keeps the recording
to one boundary per request, the outer one, wherever both apply.

Removal restores __call__, which un-wraps even applications already
serving. Unhandled exceptions need no binding of their own:
starlette's ServerErrorMiddleware beneath answers 500 and always
re-raises, so the exception lands on the request event beside the
response's size; FastAPI's own validation and HTTP exceptions are
turned into responses inside the stack and record as nothing but
the status they produced.

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
# instance: named for this target, because the starlette target
# caches its own wrapper on the same instances (see the module
# docstring).

_CACHE = "_wrapture_fastapi_interposed"


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind FastAPI.__call__ to delegate through the recording
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

    call = wrapture.binding(module.FastAPI, "__call__", when=False)
    call.on_call.decorates(boundary)

    group = wrapture.bindings(call=call)
    group.apply()

    instrumentation.on_cleanup(group.remove)
