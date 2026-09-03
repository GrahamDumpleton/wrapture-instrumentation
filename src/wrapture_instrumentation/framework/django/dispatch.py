"""The route annotation: BaseHandler's dispatch, both transports.

BaseHandler._get_response resolves the URL, sets
request.resolver_match, then invokes the view;
_get_response_async is its async twin, and both live on the base
class WSGIHandler and ASGIHandler share, so the one module covers
both transports. Each binding is behaviour only (`when=False`) and
annotates the in-flight request event with the matched route pattern
(the low-cardinality grouping key the raw path is not; wrapture's
OpenTelemetry export reads it as `http.route`) and the view's name
as Django knows it.

The annotation happens in a finally around the dispatch: an
unhandled exception propagates out of _get_response (Django's
process_exception_by_middleware re-raises it), and resolver_match
was set before the view ran, so the failed request still gets its
route keys. A request that matched no route (a 404 raised by
resolution) has no resolver_match and gains no route keys.
"""

from __future__ import annotations

from typing import Any

import wrapture


def annotate_route(request: Any) -> None:
    """Annotate the enclosing request event from the resolver match,
    when there is one; a no-op when nothing is recording."""

    match = getattr(request, "resolver_match", None)

    if match is not None:
        wrapture.current_event(kind="request").annotate(
            route=match.route, endpoint=match.view_name
        )


def annotating(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Run the dispatch, annotating the request event from its
    resolver match whether the view returned or raised."""

    request = args[0] if args else kwargs.get("request")

    try:
        return wrapped(*args, **kwargs)
    finally:
        annotate_route(request)


async def annotating_async(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """The async twin of annotating, for _get_response_async."""

    request = args[0] if args else kwargs.get("request")

    try:
        return await wrapped(*args, **kwargs)
    finally:
        annotate_route(request)


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind both dispatch methods on BaseHandler, apply them as one
    group, and register the group's removal as this trigger's
    cleanup."""

    respond = wrapture.binding(module.BaseHandler, "_get_response", when=False)
    respond.on_call.decorates(annotating)

    respond_async = wrapture.binding(
        module.BaseHandler, "_get_response_async", when=False
    )
    respond_async.on_call.decorates(annotating_async)

    group = wrapture.bindings(respond=respond, respond_async=respond_async)
    group.apply()

    instrumentation.on_cleanup(group.remove)
