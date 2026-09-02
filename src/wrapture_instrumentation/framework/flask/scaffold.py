"""The flask.sansio.scaffold patches: lifecycle and error handler
registration, observed at the one place both applications and
blueprints register.

Scaffold is the shared base of Flask and Blueprint, and its
registration methods are where every before_request, after_request
and teardown_request callback passes, app-level or blueprint-local
alike; register_error_handler is likewise the funnel for the
errorhandler decorator, direct registration, and a blueprint's
app_errorhandler (which reaches it through the application at
blueprint registration time). Patching the four here therefore
covers every registration route except the blueprint *_app_request
variants, which append to the application's tables directly and are
patched in the sibling blueprints module.

Each binding is behaviour-only (when=False) and substitutes
wrapture.observed() around the callable being registered, so the
callback records as a call event beneath its request whenever Flask
later runs it, while the registering code gets its own function back
from the decorator form.
"""

from __future__ import annotations

from typing import Any

import wrapture

from .common import observing_registration


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the registration methods on Scaffold, apply them as one
    group, and register the group's removal as this trigger's
    cleanup.

    The lifecycle setting gates the callback registrations; error
    handler observation is core and always binds.
    """

    named: dict[str, wrapture.Binding] = {}

    if instrumentation.settings["lifecycle"]:
        before = wrapture.binding(module.Scaffold, "before_request", when=False)
        before.on_call.decorates(observing_registration(0, "f"))

        after = wrapture.binding(module.Scaffold, "after_request", when=False)
        after.on_call.decorates(observing_registration(0, "f"))

        teardown = wrapture.binding(module.Scaffold, "teardown_request", when=False)
        teardown.on_call.decorates(observing_registration(0, "f"))

        named.update(before=before, after=after, teardown=teardown)

    errors = wrapture.binding(module.Scaffold, "register_error_handler", when=False)
    errors.on_call.decorates(observing_registration(1, "f"))
    named["errors"] = errors

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)
