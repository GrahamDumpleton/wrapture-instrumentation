"""The DTL render observation: Template.render as template events.

django.template.base.Template is the Django Template Language
engine's own template; every DTL render, whether through
shortcuts.render, a TemplateResponse or the backend wrapper, ends at
its render method. The binding records each render as an event
carrying the template category, named by its derived path
(django.template.base:Template.render, the jinja2 target's shape)
and annotated with the template's own name, so the identity is data
on the event while the name stays the path. An included or extended
template renders through the same method and nests beneath.

Django's Jinja2 backend delegates to real Jinja2, so if the jinja2
target is also applied those renders record through it; this binding
covers only DTL templates and does not double up.

The capture policy is deliberate about sensitive data: the render
context is masked wholesale (it is arbitrary application data), and
the rendered output reports only its size. The templates setting
gates the whole trigger.
"""

from __future__ import annotations

from typing import Any

import wrapture


def masked(name: str | None, value: Any) -> Any:
    """The capture policy: everything a template is given is masked,
    and everything it produces is reduced to a size."""

    if name is None:
        if isinstance(value, str):
            return f"<{len(value)} chars>"
        return f"<{type(value).__name__}>"

    return "<context>"


def stamp_template(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Annotate the in-flight render event with the template's own
    name, then run the render."""

    origin = getattr(instance, "origin", None)
    name = getattr(instance, "name", None) or getattr(origin, "template_name", None)

    wrapture.annotate(template=name or "<template>")

    return wrapped(*args, **kwargs)


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the render on Template and register its removal as this
    trigger's cleanup. The templates setting gates the whole trigger:
    with it off, nothing binds and there is nothing to clean up."""

    if not instrumentation.settings["templates"]:
        return

    render = wrapture.binding(
        module.Template,
        "render",
        category="template",
        capture_args=masked,
        capture_result=masked,
    )
    render.on_call.decorates(stamp_template)

    group = wrapture.bindings(render=render)
    group.apply()

    instrumentation.on_cleanup(group.remove)
