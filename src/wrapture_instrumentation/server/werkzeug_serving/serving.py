"""The werkzeug.serving patch: the application interposed with the
recording middleware as the server is built.

BaseWSGIServer.__init__ is where every werkzeug development server
receives its application: run_simple() and make_server() both build
one (the threaded and forking servers are subclasses that call up),
and Flask's app.run() is run_simple() under another name. Unlike
wsgiref there is no accessor between server and application, the
handler reads `self.server.app` directly per request, so the
interposition happens where the application is handed over: the
__init__ binding is behaviour only (`when=False`) and its argument
transform replaces the application with wrapture's WSGIMiddleware
around it. Every request then records as one "request" event, named
by the application's own module and qualname, with everything
recorded while it is handled nested beneath. The application object
itself is never modified.

No cache is needed: the wrap happens once per server, at
construction, and the wrapper's lifetime is the server attribute it
sits in. The flip side against wsgiref's accessor seam is that
removal restores __init__ for servers built afterwards, while a
server built during instrumentation keeps its wrapper for its own
lifetime (recording only while sinks are active, as any middleware
does); an application assigned onto `server.app` after construction
bypasses the interposition.

An application that is already a WSGIMiddleware is left untouched,
and one that carries its own recording middleware inside (a Flask
application the flask instrumentation already wrapped) still records
one boundary per request: the outer middleware records and marks the
environ, and the inner one sees the mark and passes through,
wrapture's rule of one request event per request. run_simple's
reloader re-executes the program in a child process; instrumentation
applied by the program itself applies there again, so coverage
follows the child's own configuration.

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


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind BaseWSGIServer.__init__ to interpose the recording
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

    def wrap(app: Any) -> Any:
        # No application, or one already wrapped, passes through.

        if app is None or isinstance(app, wrapture.WSGIMiddleware):
            return app

        return wrapture.WSGIMiddleware(
            app,
            when=request_filter,
            tree=request_filter is not None,
            capture_args=policy,
        )

    def interpose(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        # __init__(host, port, app, ...): wrap the application where
        # it stands, positional or keyword.

        if "app" in kwargs:
            return args, {**kwargs, "app": wrap(kwargs["app"])}

        if len(args) >= 3:
            return (*args[:2], wrap(args[2]), *args[3:]), kwargs

        return args, kwargs

    init = wrapture.binding(module.BaseWSGIServer, "__init__", when=False)
    init.on_call.transforms_args(interpose)

    group = wrapture.bindings(init=init)
    group.apply()

    instrumentation.on_cleanup(group.remove)
