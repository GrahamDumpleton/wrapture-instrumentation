# Jinja2 instrumentation

Template rendering tracing for [Jinja2](https://jinja.palletsprojects.com/),
in an application or standalone. Entry point name `jinja2`; supported
versions Jinja2 3.x (`>=3.0,<4`); fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "jinja2"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("jinja2"):
    ...
```

## What you see

A cold render shows the whole pipeline; a warm one only the fast
load and the render:

```
jinja2.load(name='page.html', globals='<context>')  -> '<Template>'  [1.4ms, self 207us]
  jinja2.compile(source='<p>Hello {{ person }}</p>', ...)  -> '<code>'  [1.2ms]
jinja2.render(args='<context>', kwargs='<context>')  -> '<16 chars>'  [657us]
```

- `Template.render`, `Template.generate` and their async forms
  record as `jinja2.render`, `jinja2.generate`, `jinja2.render_async`
  and `jinja2.generate_async`. A streamed render stays open while
  its chunks are consumed and reports the chunk count and timing;
  `render_async` records around the await. Every render event is
  annotated with the template's own name (`template = "page.html"`,
  or `"<template>"` for a string template), so the identity is data
  on the event while the label stays the operation.

- `Environment._load_template` records as `jinja2.load` on every
  `get_template` (a cache hit is just a fast load), annotated with
  the template name and, for file-backed loaders, the source path;
  a cold load shows `jinja2.compile` nested inside it, and a string
  template compiles without a load.

- With `enable_async=True`, Jinja2's own sync `render()` drives
  `render_async()` internally, so a sync render in an async-enabled
  environment records both, parent and child. That is the engine's
  real call structure, traced honestly.

- The capture policy is deliberate about sensitive data: the render
  context is masked wholesale (it is arbitrary application data),
  rendered output and streamed chunks report only sizes, and
  compile's template source is truncated. Template names and paths
  pass; they name code, not data.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `loading` | `true` | Observing the loading pipeline, the `jinja2.load` and `jinja2.compile` events. Loads fire on every `get_template`, cache hit or not, so this is the layer to switch off when render events alone tell the story. The renders have no switch; they are the point. |

```toml
[[instrument]]
name = "jinja2"
loading = false
```

## With framework_flask

Nothing to configure: with both applied, `flask.render_template`
records with the `jinja2.render` work nested beneath it, one tree
from the request down through the engine.

## How it patches

For the implementation detail see the module docstrings in this
directory, starting with [environment.py](environment.py).
