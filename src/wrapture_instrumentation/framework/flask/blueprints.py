"""The flask.sansio.blueprints patches: the blueprint registrations
that bypass Scaffold.

Blueprint.before_app_request, after_app_request and
teardown_app_request do not reuse the Scaffold registration methods:
each records a deferred closure that appends the callback straight
into the application's tables when the blueprint registers. They are
patched here on the Blueprint class so those callbacks are observed
like every other; app_errorhandler needs nothing, because its
deferred closure goes through the application's errorhandler and so
through the register_error_handler patch in the sibling scaffold
module.

Each binding is behaviour-only (when=False) and substitutes
wrapture.observed() around the callable being registered, exactly as
the scaffold module does.
"""

from __future__ import annotations

from typing import Any

import wrapture

from .common import observing_registration


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the three app-level registration methods on Blueprint,
    apply them as one group, and register the group's removal as this
    trigger's cleanup.

    Everything here is lifecycle observation, so with the aspect off
    the trigger applies nothing and there is nothing to clean up.
    """

    lifecycle = instrumentation.settings["lifecycle"]
    if not lifecycle.enabled:
        return

    observing = observing_registration(0, "f", lifecycle.options)

    before = wrapture.binding(module.Blueprint, "before_app_request", when=False)
    before.on_call.decorates(observing)

    after = wrapture.binding(module.Blueprint, "after_app_request", when=False)
    after.on_call.decorates(observing)

    teardown = wrapture.binding(module.Blueprint, "teardown_app_request", when=False)
    teardown.on_call.decorates(observing)

    group = wrapture.bindings(before=before, after=after, teardown=teardown)
    group.apply()

    instrumentation.on_cleanup(group.remove)
