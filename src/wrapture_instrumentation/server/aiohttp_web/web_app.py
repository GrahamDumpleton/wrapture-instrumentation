"""The aiohttp.web_app patch: the application's request handling as
the request boundary.

Application._handle is where every request an aiohttp server carries
arrives with nothing done yet and leaves with the response decided:
the router resolves the match there, the application middlewares run
inside it, and a sub-application added with add_subapp() is resolved
through the root's dispatch, so it runs once per request however the
application is composed. aiohttp is neither WSGI nor ASGI, so the
recording middlewares do not speak for it; the binding is behaviour
only (`when=False`) and the behaviour opens a `wrapture.block()`
around the handling, the same boundary the xmlrpc.server target
opens at its door. The block is labelled `aiohttp.web` and
categorised `server`, seeded with the request method, path, scheme,
peer and query (recorded through `wrapture.capture_query()`, the
built-in sensitive names masked and the `redact` setting's names on
top), and handed the request's headers as `joins=` so a request
carrying a `traceparent` makes the handling part of the caller's
distributed trace, exactly as the WSGI and ASGI middlewares join at
their boundary. The `join` setting off never parses the headers at
all, and the category holds either way, so wrapture's OpenTelemetry
export renders the boundary as a SERVER span named access-log style
by the matched route (`GET /quote/{item}`). `ignore_paths` becomes a
`filter_requests()` filter evaluated by hand per request with its
matches() method, over the same fields the boundary records, the
answer handed to the block's when= with tree=True, so an ignored
request records nothing at all, its handler included.

Once dispatch has run, the boundary is annotated with the matched
route's canonical pattern as `route` (a sub-application's prefix
folded in) and the route's name, or failing that the handler's own
name, as `endpoint`; a request that matched no route records with
its raw path and no route keys. The response's status is annotated
as `status`, and that includes the aiohttp way of answering with an
`HTTPException`: raising `HTTPNotFound` is control flow that carries
a status, not a failure, so the boundary records the 404 (or
whatever the exception says) and no exception, while the exception
itself still propagates for the protocol to turn into the response.
An exception that is not an `HTTPException` is a real failure: it
records on the boundary and propagates, and the protocol answers the
500 on its own.

The block closes when the handling returns, so its duration is the
time to the response being decided: for a handler returning a
prepared `web.Response` the protocol writes the body just after, and
a `StreamResponse` or websocket handler does its writing inside the
handling, covered. Removal restores `_handle` for requests handled
afterwards.
"""

from __future__ import annotations

from typing import Any

import wrapture


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the application's request handling as the request
    boundary; register its removal as this trigger's cleanup."""

    settings = instrumentation.settings

    # The aiohttp modules are already imported once this hook fires;
    # HTTPException is the class the status-not-failure rule keys on.

    from aiohttp.web_exceptions import HTTPException

    # The query policy: redact() with the setting's names, or the
    # reference level, either way on top of the built-in sensitive set.

    names = tuple(settings["redact"])
    policy: Any = wrapture.redact(*names) if names else "reference"

    # The ignored paths become a filter over the boundary's own
    # recorded fields, evaluated by hand per request since the
    # boundary is a block rather than a request middleware.

    recording = (
        wrapture.filter_requests(ignore={"path": list(settings["ignore_paths"])})
        if settings["ignore_paths"]
        else None
    )

    def annotate_route(request: Any) -> None:
        """Annotate the matched route's pattern and name onto the
        boundary, when dispatch resolved one."""

        # Dispatch that failed before resolution leaves match_info
        # unset, and on some aiohttp versions asking for it then
        # raises rather than answering None: no match, no keys.

        try:
            info = request.match_info
        except Exception:
            return

        route = getattr(info, "route", None)
        resource = getattr(route, "resource", None)
        canonical = getattr(resource, "canonical", None)

        if not canonical:
            return

        wrapture.annotate(route=str(canonical))

        handler = getattr(info, "handler", None)
        endpoint = getattr(resource, "name", None) or getattr(handler, "__name__", None)

        if endpoint:
            wrapture.annotate(endpoint=str(endpoint))

    async def boundary(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        request = args[0] if args else kwargs.get("request")

        if request is None:
            return await wrapped(*args, **kwargs)

        # One block per handled request, joining the trace the request
        # arrived with by the join setting. The headers only ever feed
        # the join parse; none of them are recorded.

        joins = None
        if settings["join"]:
            joins = {str(name): str(value) for name, value in request.headers.items()}

        data: dict[str, Any] = {
            "method": str(request.method),
            "path": str(request.path),
            "scheme": str(request.scheme),
        }

        if request.remote:
            data["remote"] = str(request.remote)

        if request.query_string:
            data["query"] = wrapture.capture_query(request.query_string, policy)

        # The ignore filter is consulted over the same fields the
        # event records; a declined request records nothing at all,
        # its handler included, and its headers are never parsed.

        wanted = recording is None or recording.matches(data)

        # An HTTPException is aiohttp's way of answering with a status,
        # control flow rather than a failure: its status is annotated
        # and it is re-raised outside the block, so the boundary
        # records no exception while the protocol still turns it into
        # the response. Anything else escaping is a real failure and
        # records on the boundary as it propagates.

        control: BaseException | None = None
        response: Any = None

        with wrapture.block(
            "aiohttp.web",
            category="server",
            data=data,
            joins=joins,
            when=wanted,
            tree=recording is not None,
        ):
            try:
                response = await wrapped(*args, **kwargs)
            except HTTPException as exc:
                annotate_route(request)
                wrapture.annotate(status=exc.status)
                control = exc
            except BaseException:
                annotate_route(request)
                raise
            else:
                annotate_route(request)

                status = getattr(response, "status", None)
                if status is not None:
                    wrapture.annotate(status=status)

        if control is not None:
            raise control

        return response

    handled = wrapture.binding(module.Application, "_handle", when=False)
    handled.on_call.decorates(boundary)

    group = wrapture.bindings(handled=handled)
    group.apply()

    instrumentation.on_cleanup(group.remove)
