"""The starlette.routing patches: route dispatch annotated, and
endpoint functions observed as their routes are built.

Two bindings on Route, both behaviour only (`when=False`):

- Route.handle runs once routing has matched, which makes it the
  moment the matched route is known and the in-flight event is still
  the request itself: the binding annotates the request event with
  the route's path pattern ("/items/{id}") and its name (the
  endpoint function's name unless the route was given one), giving
  every consumer the low-cardinality grouping key the raw path is
  not. A request that matched no route (a 404) reaches no Route and
  gains no annotation. A route inside a Mount annotates the pattern
  it owns, the part below the mount point. wrapture's OpenTelemetry
  export reads `route` as `http.route`.

- Route.__init__ substitutes wrapture.observed(endpoint) as routes
  are built, labelled with the route's name, so every endpoint
  function records as a "call" event beneath its request under the
  name starlette itself knows it by. The substitution mirrors
  starlette's own test exactly: only a function or method (unwrapped
  through functools.partial) is treated as a request/response
  endpoint, so a class-based endpoint or a mounted ASGI application
  passes through untouched, and the observed proxy still reads as a
  function to starlette, async endpoints included. Routes built
  before the instrumentation applied keep their bare endpoints: in
  real use the config applies before the application module imports,
  so routes are built afterwards.

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
    into a Route construction.

    The signature is Route(path, endpoint, *, name=None, ...), so the
    endpoint is the second positional argument or the endpoint
    keyword. Only a plain function or method is wrapped: anything
    else (a functools.partial, a class-based endpoint, an ASGI app)
    is starlette's to handle untouched, and the observed proxy still
    reads as a function to starlette's own endpoint test, async
    endpoints included.
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
    """Bind Route's construction and dispatch, apply them as one
    group, and register the group's removal as this trigger's
    cleanup."""

    constructor = wrapture.binding(module.Route, "__init__", when=False)
    constructor.on_call.transforms_args(observing_endpoints)

    dispatch = wrapture.binding(module.Route, "handle", when=False)
    dispatch.on_call.decorates(annotate_route)

    group = wrapture.bindings(constructor=constructor, dispatch=dispatch)
    group.apply()

    instrumentation.on_cleanup(group.remove)
