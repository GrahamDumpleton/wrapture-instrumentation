"""The flask.app patches, at the Flask class's own choke points.

Six bindings, all created with when=False so they are behaviour-only:
the plumbing is not the trace, so they act without ever recording
their own calls.

- Flask.__init__ installs the recording WSGI middleware on each new
  instance's wsgi_app attribute, the documented place Flask middleware
  goes, so every request records as one "request" event however the
  instance was made: module level, an application factory, several
  applications in one process. The ignore_paths setting rides on the
  middleware as a filter_requests() filter with tree=True, so an
  ignored request records nothing at all, its view, callbacks and
  template renders included.

- Flask.add_url_rule substitutes wrapture.observed(view_func) as
  routes register, labelled with the route's endpoint, so every view
  handler records as a "call" event beneath its request under the
  name Flask itself knows it by ("quoted", "reports.summary",
  "catalog"), wherever the view came from: module functions,
  closures, blueprints from other modules, MethodView classes (which
  register a generated view function whose closure name would
  otherwise be the label). Flask captures view functions into its
  dispatch table the moment a route registers, before any observation
  could exist, which is why registration itself is the point to
  intercept. Registering the same function again hands this wrapper
  the caller's original callable, not the proxy from last time, so
  views do not stack observations however often they register.

- Flask.preprocess_request runs once routing has matched and before
  any user code, which makes it the moment the matched route pattern
  and endpoint are known and the in-flight event is still the request
  itself: the binding annotates the request event with them, giving
  every consumer the low-cardinality grouping key the raw path is
  not. A request that matched no route (a 404) is left alone.

- Flask.teardown_appcontext registers callbacks the way the
  lifecycle methods on Scaffold do, but lives on the application
  base class rather than Scaffold (blueprints have no application
  context), so it is patched here beside the class's other methods:
  registered callbacks are observed and record as calls beneath the
  request whose context pop runs them.

- Flask.handle_user_exception receives every exception a request
  raises before Flask decides its fate. When it returns normally a
  registered handler (or Flask's HTTPException handling) has turned
  the exception into a response, and for a non-HTTPException that
  outcome would otherwise leave no mark, so the binding notes the
  exception against the request. An HTTPException (abort() and
  friends) is control flow, not a failure, and is not noted; an
  exception with no handler is re-raised out of the method and noted
  by the handle_exception binding instead, so nothing is noted twice.

- Flask.handle_exception is the one place an unhandled exception can
  be seen after Flask catches it: wsgi_app catches around the
  dispatch and hands the exception here, which returns the 500
  response, so the request itself completes normally. The binding
  notes the exception against the enclosing request event with
  note_exception(), so the request shows the failure beside its
  status.

The six are applied as one group whose remove() is registered as a
cleanup callback with on_cleanup(), which is what lets remove(), and
with it AppliedConfig.revert() and the instrumentation() context
manager, take the whole thing down again.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import wrapture

from .common import observing_registration


def wrap_app(ignore_paths: Sequence[str], redact: Sequence[str]) -> Callable[..., Any]:
    """Build the Flask.__init__ decorator that installs the recording
    middleware on each new instance's wsgi_app, carrying the
    ignore_paths and redact settings into it.

    ignore_paths becomes a filter_requests() filter on the middleware's
    when=, with tree=True so that a declined request silences
    everything beneath it for its whole extent; without the flag the
    request's view, callbacks and renders would still record, each as
    a parentless root. tree= is only valid alongside a when=, so both
    are left unset when there is nothing to ignore.
    """

    request_filter = (
        wrapture.filter_requests(ignore={"path": list(ignore_paths)})
        if ignore_paths
        else None
    )
    policy = wrapture.redact(*redact) if redact else None

    def install(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        outcome = wrapped(*args, **kwargs)

        # Label with the app's own import name, so requests read as
        # "myapp.wsgi_app" and two apps in one process stay distinct.

        instance.wsgi_app = wrapture.WSGIMiddleware(
            instance.wsgi_app,
            label=f"{instance.name}.wsgi_app",
            when=request_filter,
            tree=request_filter is not None,
            capture_args=policy,
        )

        return outcome

    return install


def _endpoint(args: tuple[Any, ...], kwargs: dict[str, Any], view: Any) -> str:
    """The endpoint an add_url_rule call registers its view under.

    Flask's own fallback applies: an endpoint given by keyword or as
    the second positional argument wins, and a registration without
    one takes the view function's name, exactly as
    _endpoint_from_view_func does.
    """

    endpoint = kwargs.get("endpoint")
    if endpoint is None and len(args) >= 2:
        endpoint = args[1]

    return str(endpoint) if endpoint is not None else view.__name__


def wrap_view() -> Callable[..., Any]:
    """Build the add_url_rule transformer that substitutes an observed
    view function, labelled by its endpoint, into each registration.

    The signature is add_url_rule(rule, endpoint=None, view_func=None,
    ...), so the view is either the view_func keyword or the third
    positional argument; a registration without a view (an endpoint
    name alone) passes through untouched. The view needs no predicate
    of its own: an ignored request is silenced beneath the middleware,
    view included.
    """

    def transform(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        if kwargs.get("view_func") is not None:
            view = kwargs["view_func"]
            observed = wrapture.observed(view, label=_endpoint(args, kwargs, view))
            kwargs = dict(kwargs, view_func=observed)
        elif len(args) >= 3 and args[2] is not None:
            view = args[2]
            observed = wrapture.observed(view, label=_endpoint(args, kwargs, view))
            args = (*args[:2], observed, *args[3:])

        return args, kwargs

    return transform


def annotate_route(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Annotate the in-flight request event with the matched route
    pattern and endpoint, then run request preprocessing."""

    # preprocess_request runs after routing has matched and before any
    # user code, and the plumbing bindings record nothing of their
    # own, so the innermost event annotate() reaches is the request
    # itself. The route pattern is the grouping key (the raw path is
    # high-cardinality); a request that matched no route has no
    # url_rule and gains no annotation. annotate() is a no-op when
    # nothing is recording.

    from flask import request

    if request.url_rule is not None:
        wrapture.annotate(route=request.url_rule.rule, endpoint=request.endpoint)

    return wrapped(*args, **kwargs)


def note_handled(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Run handle_user_exception, and when it turned a real exception
    into a response, note the exception against the enclosing request
    event."""

    # A raise out of the wrapped call means no handler claimed the
    # exception: it propagates to handle_exception, whose binding
    # notes it, so letting it fly avoids a double note.

    outcome = wrapped(*args, **kwargs)

    # HTTPExceptions are control flow (abort(), 404s): the response
    # status already tells that story. Anything else that came back
    # as a response was a genuine failure a handler absorbed.

    from werkzeug.exceptions import HTTPException

    exception = args[0] if args else kwargs.get("e")
    if exception is not None and not isinstance(exception, HTTPException):
        wrapture.current_event(kind="request").note_exception(exception)

    return outcome


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
        wrapture.current_event(kind="request").note_exception(exception)

    return wrapped(*args, **kwargs)


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the six choke points on the Flask class found in the
    flask.app module, apply them as one group, and register the
    group's removal as this trigger's cleanup."""

    settings = instrumentation.settings

    constructor = wrapture.binding(module.Flask, "__init__", when=False)
    constructor.on_call.decorates(
        wrap_app(settings["ignore_paths"], settings["redact"])
    )

    registrar = wrapture.binding(module.Flask, "add_url_rule", when=False)
    registrar.on_call.transforms_args(wrap_view())

    router = wrapture.binding(module.Flask, "preprocess_request", when=False)
    router.on_call.decorates(annotate_route)

    named: dict[str, wrapture.Binding] = {
        "constructor": constructor,
        "registrar": registrar,
        "router": router,
    }

    # The category settings: teardown_appcontext registration is
    # lifecycle observation, and the handle_user_exception noting is
    # the handled-errors layer; each binds only when its switch is on.

    if settings["lifecycle"]:
        appcontext = wrapture.binding(module.Flask, "teardown_appcontext", when=False)
        appcontext.on_call.decorates(observing_registration(0, "f"))
        named["appcontext"] = appcontext

    if settings["handled_errors"]:
        user_handler = wrapture.binding(
            module.Flask, "handle_user_exception", when=False
        )
        user_handler.on_call.decorates(note_handled)
        named["user_handler"] = user_handler

    handler = wrapture.binding(module.Flask, "handle_exception", when=False)
    handler.on_call.decorates(note_failure)
    named["handler"] = handler

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)
