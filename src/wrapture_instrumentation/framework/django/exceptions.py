"""The unhandled-exception noting: Django's catch-all before the 500.

Django catches a view's unhandled exception, produces a 500, and the
request still completes, so the exception never flies out of the
request boundary on its own; it must be noted deliberately, as the
flask target does at handle_exception. handle_uncaught_exception in
django.core.handlers.exception is the one place that sees exactly
the real failures: it is called only for the catch-all that becomes
a 500. Http404, PermissionDenied and SuspiciousOperation are control
flow that carry a status, and convert_exception_to_response turns
them into their 404/403/400 responses upstream of this seam, so
nothing extra is needed to exclude them and no guard should be
added here.

The binding is behaviour only (`when=False`): it notes the exception
against the enclosing request event with note_exception(), then lets
the handler produce its 500, so the request shows the failure beside
its status.
"""

from __future__ import annotations

from typing import Any

import wrapture


def note_failure(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Note the exception the catch-all received against the
    enclosing request event, then let the handler run."""

    # The signature is handle_uncaught_exception(request, resolver,
    # exc_info). Aim the note at the request the middleware recorded;
    # outside a request (nothing recording) this is a no-op.

    exc_info = args[2] if len(args) > 2 else kwargs.get("exc_info")

    if exc_info is not None and exc_info[1] is not None:
        wrapture.current_event(kind="request").note_exception(exc_info[1])

    return wrapped(*args, **kwargs)


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the catch-all and register its removal as this trigger's
    cleanup."""

    handler = wrapture.binding(module, "handle_uncaught_exception", when=False)
    handler.on_call.decorates(note_failure)

    group = wrapture.bindings(handler=handler)
    group.apply()

    instrumentation.on_cleanup(group.remove)
