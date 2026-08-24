"""The Flask patches, at Flask's own choke points.

Three bindings, all created with when=False so they are behaviour-only:
the plumbing is not the trace, so they act without ever recording
their own calls.

- Flask.__init__ installs the recording WSGI middleware on each new
  instance's wsgi_app attribute, the documented place Flask middleware
  goes, so every request records as one "request" event however the
  instance was made: module level, an application factory, several
  applications in one process.
- Flask.add_url_rule substitutes wrapture.observed(view_func) as
  routes register, so every view handler records as a "call" event
  beneath its request, wherever the view came from: module functions,
  closures, blueprints from other modules, MethodView classes (which
  register a generated view function). Flask captures view functions
  into its dispatch table the moment a route registers, before any
  observation could exist, which is why registration itself is the
  point to intercept. observed() is idempotent, so a view registered
  twice is not wrapped twice.
- Flask.handle_exception is the one place a view's exception can be
  seen after Flask catches it: wsgi_app catches around the dispatch
  and hands the exception here, which returns the 500 response, so
  the request itself completes normally. The binding notes the
  exception against the enclosing request event with note_exception(),
  so the request shows the failure beside its status.

The three are applied as one group whose remove() is registered as a
cleanup callback with on_cleanup(), which is what lets remove(), and
with it AppliedConfig.revert() and the instrumentation() context
manager, take the whole thing down again.
"""

from __future__ import annotations

from typing import Any

import wrapture


def wrap_app(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Run Flask.__init__, then install the recording middleware on the
    new instance's wsgi_app."""

    outcome = wrapped(*args, **kwargs)

    # Label with the app's own import name, so requests read as
    # "myapp.wsgi_app" and two apps in one process stay distinct.

    instance.wsgi_app = wrapture.WSGIMiddleware(
        instance.wsgi_app, label=f"{instance.name}.wsgi_app"
    )

    return outcome


def wrap_view(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Substitute an observed view function into an add_url_rule call.

    The signature is add_url_rule(rule, endpoint=None, view_func=None,
    ...), so the view is either the view_func keyword or the third
    positional argument; a registration without a view (an endpoint
    name alone) passes through untouched.
    """

    if kwargs.get("view_func") is not None:
        kwargs = dict(kwargs, view_func=wrapture.observed(kwargs["view_func"]))
    elif len(args) >= 3 and args[2] is not None:
        args = (*args[:2], wrapture.observed(args[2]), *args[3:])

    return args, kwargs


def note_failure(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Note the exception handle_exception received against the
    enclosing request event, then let the handler run."""

    # The exception is the handler's one positional argument. Aim the
    # note at the request the middleware recorded, not at this call,
    # which is not recorded anyway; outside a request (a handler
    # invoked with nothing recording) this is a no-op.

    exception = args[0] if args else kwargs.get("e")
    if exception is not None:
        wrapture.note_exception(exception, event=wrapture.current_event(kind="request"))

    return wrapped(*args, **kwargs)


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the three choke points on the Flask class found in the
    flask.app module, apply them as one group, and register the
    group's removal as the instrumentation's cleanup."""

    constructor = wrapture.binding(module.Flask, "__init__", when=False)
    constructor.on_call.decorates(wrap_app)

    registrar = wrapture.binding(module.Flask, "add_url_rule", when=False)
    registrar.on_call.transforms_args(wrap_view)

    handler = wrapture.binding(module.Flask, "handle_exception", when=False)
    handler.on_call.decorates(note_failure)

    group = wrapture.bindings(
        constructor=constructor, registrar=registrar, handler=handler
    )
    group.apply()

    instrumentation.on_cleanup(group.remove)
