"""The template rendering patches, bound once the flask package has
finished importing.

The four public rendering functions exist in two places: defined in
flask.templating, and re-exported from the flask namespace, which is
the documented spelling. Both must trace, and both are bound with
ordinary bindings by triggering on the flask package itself rather
than on flask.templating: the package trigger fires only after
flask/__init__ has finished executing, by which point its from-import
has copied the original functions into the namespace, in every import
order (importing flask.templating first still completes the package
first). Nothing is wrapped until all copying is done, so no wrapper
object ever escapes into an attribute the bindings do not own, and
removal restores every patched attribute through the binding
machinery alone. This rests on two verified facts of Flask 3.x (both
ends of the supports range checked): flask/__init__ imports these
four functions from .templating unconditionally at top level, and no
other flask module imports them into its own namespace, so the eight
attributes bound here are every location Flask itself holds.

These bindings record (the rendering is the trace, unlike the
plumbing patches elsewhere in this package), and their capture policy
is deliberate about sensitive data: the template name (or the source
text, truncated) is captured, the render context is masked wholesale
(it is arbitrary application data: user objects, form contents), and
the rendered output is captured only as its size. The stream
functions return generators, which wrapture records around the
iteration, so a streamed render shows its item count and timing like
any other streamed body. Both spellings of each function carry the
same explicit label, the documented one, so an event reads
identically whichever path the call took.
"""

from __future__ import annotations

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
    """Bind the four rendering functions on flask.templating and on
    the flask namespace, apply them as one group, and register the
    group's removal as this trigger's cleanup.

    `module` is the flask package. The templates setting gates the
    whole trigger: with it off, nothing binds and there is nothing to
    clean up.
    """

    if not instrumentation.settings["templates"]:
        return

    # The same four functions are deliberately bound in both places,
    # under the same label, so both spellings trace identically.
    # Anything added later that exists only in flask.templating must
    # bind on module.templating alone, outside this loop.

    named: dict[str, wrapture.Binding] = {}

    for owner, prefix in ((module.templating, "templating"), (module, "namespace")):
        for name in FUNCTIONS:
            bound = wrapture.binding(
                owner,
                name,
                label=f"flask.{name}",
                capture_args=masked,
                capture_result=masked,
            )
            named[f"{prefix}_{name}"] = bound

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)
