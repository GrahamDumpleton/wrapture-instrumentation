# Changes

## Version 1.0.0

In development.

- Jinja2 (`jinja2`, Jinja2 3.x): every render traced in all its
  forms, sync, streamed and async, each annotated with the
  template's own name; the loading pipeline
  (`jinja2.load` on every get_template, `jinja2.compile` inside a
  cold load) beneath it, behind a `loading` switch; and the render
  context, output and template source kept out of capture or
  truncated.

- Flask (`flask`, Flask 3.x): every request records as one tree
  through the recording WSGI middleware installed at construction,
  annotated with the matched route pattern and endpoint; every view
  function is observed as it registers and labelled by its endpoint
  (blueprints and `MethodView`s included); lifecycle callbacks and
  error handlers are observed however they register; and failures
  are noted against the request, whether Flask answered 500 or a
  registered handler absorbed a real exception (an `HTTPException`
  is control flow and is not noted); and template rendering records
  beneath the view that asked for it, capturing the template name
  while the render context and output stay out of capture. Three
  settings switch the optional layers, all on by default:
  `lifecycle`, `handled_errors` and `templates`.
