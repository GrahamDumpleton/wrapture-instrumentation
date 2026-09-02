"""The wsgiref.simple_server patch: the application interposed with
the recording middleware at the server's own seam.

WSGIServer.get_app is where the server fetches the application for
each request it handles, whether the application arrived through
make_server(), set_app() or a subclass: the one seam between the
server and the application. It is bound as behaviour only
(`when=False`), and the behaviour hands back the application wrapped
in wrapture's WSGIMiddleware, so every request records as one
"request" event, named by the application's own module and qualname,
with everything recorded while it is handled nested beneath. The
application object itself is never modified, and removing the
instrumentation restores get_app, which un-wraps even servers
already running.

One middleware per server: the wrapper is cached on the server
instance itself, beside the application it wraps, so it lives
exactly as long as the server that made it necessary and the
instrumentation keeps nothing alive on its own. A weak-keyed cache
looks like the obvious alternative and is wrong here: the middleware
must strongly wrap the application it calls, and a WeakKeyDictionary
whose values reference their keys keeps those keys alive, the
documented caveat, so the weakness would be silently defeated. A
set_app() replacing the application is caught by identity and
rebuilds the wrapper. An application that is already a
WSGIMiddleware is returned untouched, and one that carries its own
recording middleware inside (a framework the framework
instrumentation already wrapped) still records one boundary per
request: the outer middleware records and marks the environ, and the
inner one sees the mark and passes through, wrapture's rule of one
request event per request.

The request boundary is where distributed trace identity arrives: a
request carrying a `traceparent` header joins the caller's trace,
exactly as any wrapture-recorded WSGI application does, and the
query string is recorded with the built-in sensitive names masked,
plus any the `redact` setting adds. `ignore_paths` becomes a
filter_requests() filter on the middleware's when=, with tree=True,
so an ignored request records nothing at all, beneath it included.
"""

from __future__ import annotations

from typing import Any

import wrapture

# The attribute the wrapper is cached under on the server instance,
# paired with the application it was built for.

_CACHE = "_wrapture_interposed"


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind WSGIServer.get_app to interpose the recording middleware;
    register its removal as this trigger's cleanup."""

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

    def interpose(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        app = wrapped(*args, **kwargs)

        # No application, or one already wrapped, passes through.

        if app is None or isinstance(app, wrapture.WSGIMiddleware):
            return app

        # One middleware per server, cached on the server instance so
        # its lifetime is the server's own (see the module docstring
        # for why a weak-keyed cache would be wrong here); the pair
        # records which application it was built for, so a set_app()
        # replacing the application rebuilds the wrapper.

        cached = getattr(instance, _CACHE, None) if instance is not None else None
        if cached is not None and cached[0] is app:
            return cached[1]

        middleware = wrapture.WSGIMiddleware(
            app,
            when=request_filter,
            tree=request_filter is not None,
            capture_args=policy,
        )

        if instance is not None:
            setattr(instance, _CACHE, (app, middleware))

        return middleware

    get_app = wrapture.binding(module.WSGIServer, "get_app", when=False)
    get_app.on_call.decorates(interpose)

    group = wrapture.bindings(get_app=get_app)
    group.apply()

    instrumentation.on_cleanup(group.remove)
