"""The view observation: ResolverMatch construction at URL resolution.

Django has no registration-time seam for views the way Flask's
add_url_rule is one: path("x/", views.f) stores the view on a
URLPattern, resolved lazily per request into a ResolverMatch. So the
binding decorates ResolverMatch.__init__ (behaviour only,
`when=False`) and substitutes wrapture.observed(func) for the
resolved callback, labelled by the URL pattern's name when it has
one, so every view records as a "call" event beneath its request
under the name Django itself knows it by. An unnamed pattern's view
keeps its derived module:qualname path as the name.

Nested urlconfs construct a ResolverMatch at each enclosing
URLResolver level around the inner match's func, so the transform
fires more than once per request and the outer firing receives the
already-observed proxy; observed() dedupes by identity and returns
it unchanged, so views never stack observations.

Only a plain function or method is wrapped: view functions, and the
closure View.as_view() returns for a class-based view, are both
functions, so both record as one call event per view (the CBV's
dispatch and HTTP-method methods run inside it). Anything else is
Django's to handle untouched. The observed proxy still reads as a
function to Django's own checks, async views included: Django's
coroutine-function test passes through the proxy, so an async view
is still awaited.

The observed view's capture policy reduces the request argument to
its type: unlike Starlette's, Django's request repr carries the raw
path and query string, which would put an unredacted query into the
captured arguments. Everything else a view receives came out of the
URL itself and passes.

Two deliberate gaps: resolve("/x/").func is the proxy under
instrumentation (equality and introspection delegate, `is` does
not), and Django's 404/500 error-handler views resolve through
resolve_error_handler without a ResolverMatch, so they are not
observed.
"""

from __future__ import annotations

import inspect
from typing import Any

import wrapture


def masked(name: str | None, value: Any) -> Any:
    """The view capture policy: a request reduces to its type, so its
    repr's raw query string never reaches the record; URL-derived
    arguments pass."""

    from django.http import HttpRequest

    if isinstance(value, HttpRequest):
        return f"<{type(value).__name__}>"

    return value


def observing_views(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Substitute an observed view, labelled by the URL pattern's
    name, into a ResolverMatch construction.

    The signature is ResolverMatch(func, args, kwargs, url_name=None,
    ...), func always first, so the view is the first positional
    argument or the func keyword, and the pattern name the fourth
    positional or the url_name keyword.
    """

    if "func" in kwargs:
        func = kwargs["func"]
    elif args:
        func = args[0]
    else:
        return args, kwargs

    if not (inspect.isfunction(func) or inspect.ismethod(func)):
        return args, kwargs

    url_name = kwargs.get("url_name")
    if url_name is None and len(args) >= 4:
        url_name = args[3]

    observed = wrapture.observed(func, label=url_name, capture_args=masked)

    if "func" in kwargs:
        return args, {**kwargs, "func": observed}

    return (observed, *args[1:]), kwargs


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind ResolverMatch's construction and register its removal as
    this trigger's cleanup.

    Removal is complete on its own: the only proxies ever made live
    in per-request ResolverMatch objects, so restoring __init__
    restores the world.
    """

    constructor = wrapture.binding(module.ResolverMatch, "__init__", when=False)
    constructor.on_call.transforms_args(observing_views)

    group = wrapture.bindings(constructor=constructor)
    group.apply()

    instrumentation.on_cleanup(group.remove)
