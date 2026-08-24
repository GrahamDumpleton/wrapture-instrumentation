"""Helpers shared by the framework_flask patch submodules.

This module imports only wrapture; nothing here touches Flask.
"""

from __future__ import annotations

from typing import Any

import wrapture

RegistrationWrapper = Any


def observing_registration(position: int, keyword: str) -> Any:
    """A decorates() wrapper that substitutes wrapture.observed() around
    the callable a registration method receives.

    The callable is found at `position` in the positional arguments or
    under `keyword`; a call without one passes through untouched. The
    registration stores the observed proxy, so the callback records as
    a call event whenever Flask later runs it, while the caller gets
    the original function back: Flask's registration decorators return
    the function they were given, and user code must keep its own
    name bound to its own function, not to our proxy.
    """

    def wrapper(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # Locate the callable being registered, wherever the caller
        # put it; registrations without one are not ours to touch.

        if keyword in kwargs:
            target = kwargs[keyword]
        elif len(args) > position:
            target = args[position]
        else:
            target = None

        if target is None:
            return wrapped(*args, **kwargs)

        # Substitute the proxy into the registration. Re-registering
        # the same function hands this wrapper the raw callable again,
        # so observations never stack.

        proxy = wrapture.observed(target)

        if keyword in kwargs:
            kwargs = dict(kwargs, **{keyword: proxy})
        else:
            args = (*args[:position], proxy, *args[position + 1 :])

        # A decorator-style registration returns what it was given,
        # which is now the proxy; hand the caller their original back
        # so their namespace keeps their function. Everything else
        # (register_error_handler returns None) passes through.

        outcome = wrapped(*args, **kwargs)
        return target if outcome is proxy else outcome

    return wrapper
