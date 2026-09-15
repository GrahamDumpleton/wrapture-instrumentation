"""Helpers for the aspects every target declares.

This module imports only wrapture; nothing here touches a target.
"""

from __future__ import annotations

from typing import Any

import wrapture


def honours(instrumentation: wrapture.Instrumentation, name: str, *keys: str) -> None:
    """Refuse the recording keys given under the named aspect that its
    bindings cannot honour, so a key with no effect fails when the
    config applies rather than being silently ignored.

    `keys` are the recording keys the aspect's bindings do take, as they
    appear in the resolved aspect's options: `capture_args`,
    `capture_result`, `stack` and `leaf`. A request boundary through
    wrapture's WSGI or ASGI middleware takes the two capture keys and
    `leaf`; a boundary opened with `wrapture.block()` takes `stack` and
    `leaf` and nothing about capture; an aspect that only switches a
    behaviour takes none. Call it from the class's configure(), which
    runs once before any trigger fires.
    """

    aspect = instrumentation.settings[name]
    refused = sorted(set(aspect.options) - set(keys))

    if refused:
        honoured = ", ".join(keys) if keys else "none"
        raise wrapture.ConfigError(
            f"instrumentation {instrumentation.name}: aspect {name!r} cannot apply"
            f" {refused} (a redact list composes into capture_args and"
            f" redact_result into capture_result); the recording keys it"
            f" honours are {honoured}"
        )


def boundary_options(aspect: Any, **defaults: Any) -> tuple[Any, dict[str, Any]]:
    """Split an outbound request aspect's options into the query policy
    and the binding options.

    At a request boundary `capture_args` is the policy for the
    request's descriptive data, the query string foremost, exactly as
    it is on wrapture's own request middlewares: the aspect's
    `capture_args` (a redact list already composed into it), or the
    reference level, either way on top of the built-in sensitive set,
    for `wrapture.capture_query()`. It never reaches the binding's own
    argument capture, which stays the package's structural policy (the
    URL without its query, a body as its size), so masking one query
    parameter can never expose the request object it rides in. The
    aspect's other keys splat over `defaults`, the package's binding
    options, so an explicit `capture_result`, `leaf` or `stack` under
    the aspect replaces the package's own.
    """

    options = dict(aspect.options)
    policy = options.pop("capture_args", "reference")

    return policy, {**defaults, **options}
