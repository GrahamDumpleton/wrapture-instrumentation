"""The flask.templating patches: template rendering observed, with the
render context and the rendered output kept out of capture.

The four public rendering functions are module-level functions rather
than methods, and applications reach them two ways: through the
module ("flask.templating.render_template", rare) and through the
flask namespace re-export ("from flask import render_template", the
documented spelling). Both attributes are patched. When the
instrumentation applies after flask has imported, the namespace copy
is its own binding; when it applies before (the runner case), this
trigger fires while the flask package body is still executing, the
names do not exist there yet, and the package's own from-import then
copies the already-wrapped functions, so only the templating module
needs binding and a cleanup callback restores the namespace copies
that removal cannot otherwise reach.

These bindings record (the rendering is the trace, unlike the
plumbing patches elsewhere in this package), and their capture policy
is deliberate about sensitive data: the template name (or the source
text, truncated) is captured, the render context is masked wholesale
(it is arbitrary application data: user objects, form contents), and
the rendered output is captured only as its size. The stream
functions return generators, which wrapture records around the
iteration, so a streamed render shows its item count and timing like
any other streamed body.
"""

from __future__ import annotations

import sys
from typing import Any

import wrapture

FUNCTIONS = (
    "render_template",
    "render_template_string",
    "stream_template",
    "stream_template_string",
)


def masked(name: str | None, value: Any) -> Any:
    """The capture policy for the rendering functions: template names
    pass, template source is truncated, everything else (the context,
    the rendered output) is reduced to a marker or a size."""

    if name == "template_name_or_list":
        return value if isinstance(value, str) else list(value)

    if name == "source":
        text = str(value)
        return text if len(text) <= 60 else text[:57] + "..."

    # The result side has no parameter name: a rendered string reports
    # its size, a streamed chunk likewise, anything else its type.

    if name is None:
        if isinstance(value, str):
            return f"<{len(value)} chars>"
        return f"<{type(value).__name__}>"

    return "<context>"


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the four rendering functions on flask.templating and their
    flask namespace re-exports, apply them as one group, and register
    the removal, with a fixup for namespace copies made after apply.

    The templates setting gates the whole trigger: with it off,
    nothing binds and there is nothing to clean up.
    """

    if not instrumentation.settings["templates"]:
        return

    named: dict[str, wrapture.Binding] = {}

    # Taken before apply, for the namespace fixup below.

    originals = {name: getattr(module, name) for name in FUNCTIONS}

    # Both spellings of each function carry the same explicit label,
    # the documented one, so an event reads identically whether the
    # call went through the namespace or the module, in either apply
    # order.

    for name in FUNCTIONS:
        bound = wrapture.binding(
            module,
            name,
            label=f"flask.{name}",
            capture_args=masked,
            capture_result=masked,
        )
        named[name] = bound

    # The namespace re-exports: bindable only when they exist, which
    # they do whenever flask finished importing before this trigger
    # fired. During a fresh import they are absent, and the package's
    # own from-import will copy the wrapped functions instead.

    package = sys.modules["flask"]
    missing = [name for name in FUNCTIONS if not hasattr(package, name)]

    for name in FUNCTIONS:
        if name not in missing:
            bound = wrapture.binding(
                package,
                name,
                label=f"flask.{name}",
                capture_args=masked,
                capture_result=masked,
            )
            named[f"flask_{name}"] = bound

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)

    # The fresh-import case leaves the namespace holding copies of
    # the wrapped functions that removing the bindings cannot reach,
    # and a stale wrapper keeps recording; on cleanup, restore any
    # namespace copy that is still one of our wrappers to the
    # original taken before apply. Registered after group.remove and
    # therefore running before it (callbacks run most recent first),
    # which is fine: it works from the closure, not the module.

    if missing:
        wrappers = {name: getattr(module, name) for name in missing}

        def restore_namespace_copies() -> None:
            for name in missing:
                if getattr(package, name, None) is wrappers[name]:
                    setattr(package, name, originals[name])

        instrumentation.on_cleanup(restore_namespace_copies)
