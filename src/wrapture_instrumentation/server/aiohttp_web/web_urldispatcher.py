"""The aiohttp.web_urldispatcher patch: every handler observed as
its route is registered.

ResourceRoute.__init__ is the one door route registration passes
through: add_get() and the other verb helpers, add_route(),
add_view(), the route table decorators and a sub-application's
routes all end up constructing one ResourceRoute per method with the
handler in hand (add_get() registering HEAD alongside GET constructs
two, with the same handler). The binding is behaviour only
(`when=False`) and its argument transform substitutes
`wrapture.observed()` around the handler, labelled by the route's
name when one was given, so each dispatched request records the
handler's call beneath the request boundary, named by the function's
own module and qualname.

Only plain functions and methods are wrapped. A class-based
`web.View` arrives here as the class itself and is left alone, as is
anything else that is not a function, so registration shapes the
observation cannot speak for still register exactly as before.
`wrapture.observed()` is idempotent, so the handler a verb helper
registers twice (HEAD beside GET), or one function registered on
several routes, carries one observation, not a stack.

Removal restores registration for routes added afterwards; a route
already registered keeps its observed handler for the application's
lifetime, recording only while sinks are active, the werkzeug
target's trade-off at the same kind of seam.
"""

from __future__ import annotations

import inspect
from typing import Any

import wrapture


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind route construction to observe the handlers being
    registered; register its removal as this trigger's cleanup."""

    def observing(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        # __init__(method, handler, resource, ...): observe the
        # handler where it stands, positional or keyword, functions
        # and methods only.

        handler = args[1] if len(args) >= 2 else kwargs.get("handler")

        if not (inspect.isfunction(handler) or inspect.ismethod(handler)):
            return args, kwargs

        # The route's name, registration's own low-cardinality label,
        # names the observation when one was given; without one the
        # observation is named by the function itself.

        resource = args[2] if len(args) >= 3 else kwargs.get("resource")
        name = getattr(resource, "name", None)

        observed = (
            wrapture.observed(handler, label=str(name))
            if name
            else wrapture.observed(handler)
        )

        if "handler" in kwargs:
            return args, {**kwargs, "handler": observed}

        return (*args[:1], observed, *args[2:]), kwargs

    registered = wrapture.binding(module.ResourceRoute, "__init__", when=False)
    registered.on_call.transforms_args(observing)

    group = wrapture.bindings(registered=registered)
    group.apply()

    instrumentation.on_cleanup(group.remove)
