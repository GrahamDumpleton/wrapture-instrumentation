"""The uvicorn patch: the application interposed with the recording
middleware as the server's configuration loads.

Config.load is where every uvicorn server resolves its application:
uvicorn.run(), a Server built by hand and gunicorn's UvicornWorker
all load the same Config, and a protocol that finds an unloaded
config loads it there. The binding is behaviour only (`when=False`):
after the original load has built the application chain, the
interposition walks uvicorn's own pass-through middlewares
(ProxyHeadersMiddleware, and MessageLoggerMiddleware at trace log
level) down to the application itself and wraps it in wrapture's
ASGIMiddleware where it stands. Every request then records as one
"request" event, named by the application's own module and qualname,
with everything recorded while it is handled nested beneath. The
application object itself is never modified.

Wrapping inside uvicorn's middlewares rather than around them keeps
two things right at once: the event is named by the application
rather than a uvicorn middleware, and the recorded scope is the one
the application sees, so with proxy headers on (uvicorn's default)
the client and scheme are the forwarded values, not the proxy's. An
application uvicorn adapted first (an ASGI2 application, or a WSGI
application under `--interface wsgi`) is wrapped around the adapter,
and the event is named by the adapter that stands for it.

No cache is needed: the wrap happens once per config, at load, and
the wrapper's lifetime is the attribute it sits in. Removal restores
Config.load for configs loaded afterwards, while a server already
running keeps its wrapper for its own lifetime (recording only while
sinks are active, as any middleware does), the werkzeug target's
trade-off at the same kind of seam.

An application that is already an ASGIMiddleware is left untouched,
and one that carries its own recording middleware inside (an ASGI
framework a framework instrumentation already wrapped) still records
one boundary per request: the outer middleware records and marks the
scope, and the inner one sees the mark and passes through, wrapture's
rule of one request event per request.

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

# uvicorn's pass-through middlewares: pure ASGI 3 wrappers that hand
# the scope on, safe to walk through to the application beneath. The
# adapters (ASGI2Middleware, uvicorn's own WSGIMiddleware) are not
# walked: what sits beneath them is not an ASGI 3 application.

_PASSTHROUGH = {"ProxyHeadersMiddleware", "MessageLoggerMiddleware"}


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind Config.load to interpose the recording middleware on the
    loaded application; register its removal as this trigger's
    cleanup."""

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

    def wrap(app: Any) -> Any:
        # No application, or one already wrapped, passes through.

        if app is None or isinstance(app, wrapture.ASGIMiddleware):
            return app

        return wrapture.ASGIMiddleware(
            app,
            when=request_filter,
            tree=request_filter is not None,
            capture_args=policy,
        )

    def interpose(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        outcome = wrapped(*args, **kwargs)

        if instance is None:
            return outcome

        # Walk uvicorn's pass-through middlewares down to the
        # application, remembering the wrapper the application sits
        # in, so the recording middleware lands where the application
        # stands.

        parent: Any = None
        app: Any = getattr(instance, "loaded_app", None)

        while (
            type(app).__name__ in _PASSTHROUGH
            and type(app).__module__.startswith("uvicorn.middleware")
            and hasattr(app, "app")
        ):
            parent, app = app, app.app

        interposed = wrap(app)
        if interposed is app:
            return outcome

        if parent is None:
            instance.loaded_app = interposed
        else:
            parent.app = interposed

        return outcome

    load = wrapture.binding(module.Config, "load", when=False)
    load.on_call.decorates(interpose)

    group = wrapture.bindings(load=load)
    group.apply()

    instrumentation.on_cleanup(group.remove)
