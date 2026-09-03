"""The jinja2.environment patches: rendering, and the loading pipeline
that gets a template ready.

Six bindings on two classes, all recording (the rendering is the
trace):

- Template.render, Template.generate and their async forms are the
  renders. generate returns a generator and generate_async an async
  generator, which wrapture records around the iteration, so a
  streamed render shows its chunk count and timing; render_async
  records around the await. Each render event carries the template
  category and is annotated with the template's own name (jinja2's
  "<template>" stands in for a string template), so the identity is
  data on the event while the name stays the derived path,
  jinja2.environment:Template.render and its siblings. The loading
  pipeline stays uncategorised: it is engine machinery around the
  render, not the render itself.

- Environment._load_template and Environment.compile are the loading
  pipeline: every get_template passes through _load_template (a
  cache hit is just a fast load), and a cold load compiles inside
  it; a string template compiles without a load. The load event is
  annotated with the template name and, once loaded, the source
  file's path. The loading setting gates both.

The capture policy is deliberate about sensitive data: the render
context is masked wholesale (it is arbitrary application data), the
rendered output and streamed chunks report only sizes, and compile's
template source is truncated. Template names and paths pass; they
name code, not data.
"""

from __future__ import annotations

from typing import Any

import wrapture

RENDERS = ("render", "render_async", "generate", "generate_async")


def masked(name: str | None, value: Any) -> Any:
    """The render-side capture policy: everything a template is given
    is masked, and everything it produces is reduced to a size."""

    if name is None:
        if isinstance(value, str):
            return f"<{len(value)} chars>"
        return f"<{type(value).__name__}>"

    return "<context>"


def compile_policy(name: str | None, value: Any) -> Any:
    """The compile-side capture policy: the source truncates, the
    name and filename pass, the rest reduces to markers."""

    if name == "source":
        text = str(value)
        return text if len(text) <= 60 else text[:57] + "..."

    # Everything else compile takes is engine configuration (the
    # name, the filename, plain flags), not application data.

    if name is not None:
        return value

    return masked(name, value)


def load_policy(name: str | None, value: Any) -> Any:
    """The load-side capture policy: the template name passes, the
    globals are masked, the loaded template reduces to its type."""

    if name == "name":
        return value

    return masked(name, value)


def stamp_template(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Annotate the in-flight render event with the template's own
    name, then run the render."""

    wrapture.annotate(template=getattr(instance, "name", None) or "<template>")

    return wrapped(*args, **kwargs)


def stamp_load(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Annotate the in-flight load event with the template name and,
    once the load returns, the source file's path where one exists."""

    name = args[0] if args else kwargs.get("name")
    if name is not None:
        wrapture.annotate(template=name)

    outcome = wrapped(*args, **kwargs)

    path = getattr(outcome, "filename", None)
    if path:
        wrapture.annotate(path=path)

    return outcome


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the renders on Template and, under the loading setting,
    the loading pipeline on Environment; apply them as one group and
    register the group's removal as this trigger's cleanup."""

    named: dict[str, wrapture.Binding] = {}

    for name in RENDERS:
        bound = wrapture.binding(
            module.Template,
            name,
            category="template",
            capture_args=masked,
            capture_result=masked,
        )
        bound.on_call.decorates(stamp_template)
        named[name] = bound

    if instrumentation.settings["loading"]:
        load = wrapture.binding(
            module.Environment,
            "_load_template",
            capture_args=load_policy,
            capture_result=load_policy,
        )
        load.on_call.decorates(stamp_load)
        named["load"] = load

        compiled = wrapture.binding(
            module.Environment,
            "compile",
            capture_args=compile_policy,
            capture_result=compile_policy,
        )
        named["compile"] = compiled

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)
