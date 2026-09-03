"""The fastapi.routing patches: route dispatch annotated, and
endpoint functions observed as their routes are built.

Two bindings on APIRoute, both behaviour only (`when=False`), the
fastapi spellings of the starlette target's Route bindings. They are
needed in their own right, not as duplicates: APIRoute builds itself
without calling Route.__init__, and newer fastapi gives APIRoute a
handle of its own that can dispatch without reaching Route.handle,
so the starlette target's bindings see neither.

- APIRoute.handle annotates the in-flight request event with the
  route's path pattern ("/items/{item_id}", the prefix of any
  including router folded in) and its name (the endpoint function's
  name unless the route was given one), the low-cardinality grouping
  key the raw path is not. A request that matched no route (a 404)
  reaches no APIRoute and gains no annotation. wrapture's
  OpenTelemetry export reads `route` as `http.route`. With the
  starlette target applied as well, a dispatch that does fall
  through to Route.handle annotates the same keys with the same
  values, so the two targets never disagree.

- APIRoute.__init__ substitutes wrapture.observed(endpoint) as
  routes are built, labelled with the route's name, so every
  endpoint function records as a "call" event beneath its request
  under the name FastAPI itself knows it by, dependency injection,
  response models and OpenAPI generation all reading the observed
  proxy as the function it wraps. Only a plain function or method is
  wrapped; anything else is FastAPI's to handle untouched.
  include_router() registers copies of a router's routes through
  this same constructor, handing back the already-observed proxy,
  and observed() returns such a proxy unchanged, so endpoints do not
  stack observations however often they register. Routes built
  before the instrumentation applied keep their bare endpoints: in
  real use the config applies before the application module imports.

WebSocket routes are left alone: only HTTP requests record, and the
boundary middleware passes websocket scopes through untouched.
"""

from __future__ import annotations

import inspect
from typing import Any

import wrapture


async def annotate_route(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Annotate the in-flight request event with the matched route
    pattern and name, then run the dispatch."""

    # The plumbing bindings record nothing of their own, so the
    # innermost event annotate() reaches is the request the boundary
    # middleware recorded; annotate() is a no-op when nothing is
    # recording.

    wrapture.annotate(route=instance.path, endpoint=instance.name)

    return await wrapped(*args, **kwargs)


def observing_endpoints(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Substitute an observed endpoint, labelled by the route's name,
    into an APIRoute construction.

    The signature is APIRoute(path, endpoint, *, name=None, ...), and
    FastAPI's own registration paths pass the endpoint by keyword, so
    both spellings are handled. Only a plain function or method is
    wrapped: anything else is FastAPI's to handle untouched, and the
    observed proxy still reads as its function to FastAPI's signature
    analysis, async endpoints included.
    """

    if "endpoint" in kwargs:
        endpoint = kwargs["endpoint"]
    elif len(args) >= 2:
        endpoint = args[1]
    else:
        return args, kwargs

    if not (inspect.isfunction(endpoint) or inspect.ismethod(endpoint)):
        return args, kwargs

    name = kwargs.get("name") or getattr(endpoint, "__name__", None)
    observed = wrapture.observed(endpoint, label=name)

    if "endpoint" in kwargs:
        return args, {**kwargs, "endpoint": observed}

    return (args[0], observed, *args[2:]), kwargs


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind APIRoute's construction and dispatch, apply them as one
    group, and register the group's removal as this trigger's
    cleanup."""

    constructor = wrapture.binding(module.APIRoute, "__init__", when=False)
    constructor.on_call.transforms_args(observing_endpoints)

    dispatch = wrapture.binding(module.APIRoute, "handle", when=False)
    dispatch.on_call.decorates(annotate_route)

    group = wrapture.bindings(constructor=constructor, dispatch=dispatch)
    group.apply()

    instrumentation.on_cleanup(group.remove)
