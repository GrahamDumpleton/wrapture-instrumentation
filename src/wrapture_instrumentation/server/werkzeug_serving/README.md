# werkzeug.serving instrumentation

Request tracing for applications served by
[werkzeug's development server](https://werkzeug.palletsprojects.com/en/stable/serving/),
which is also what Flask's `app.run()` starts. Entry point name
`werkzeug.serving`, the module it patches; supports werkzeug 3.x;
fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "werkzeug.serving"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("werkzeug.serving"):
    ...
```

## What you see

The application handed to the server, through `run_simple()`,
`make_server()`, a server class directly, or Flask's `app.run()`, is
wrapped in wrapture's recording WSGI middleware as the server is
built, without the application changing at all. Each request then
records as one `request` event named by the application's own module
and qualname, with everything recorded while it is handled nested
beneath:

```
request myapp:application(method='GET', path='/quote/widget')  -> '200 OK'
```

- The event carries the request `method`, `path`, `query` (recorded
  with the built-in sensitive parameter names masked, plus any the
  `redact` setting adds), `scheme` and `remote` peer, and the status
  line as its result. On wrapture's OpenTelemetry export it is a
  SERVER span, named access-log style.

- The boundary is where distributed trace identity arrives: a
  request carrying a `traceparent` header (from an instrumented
  client) joins the caller's trace, one with none roots a trace of
  its own.

- One boundary per request, however many layers record: an
  application that is already a `WSGIMiddleware` is passed through
  untouched, and one carrying its own recording middleware inside (a
  Flask application the `flask` instrumentation already wrapped)
  still records once, the outer middleware recording and the inner
  passing through. Framework annotations (the matched route, say)
  land on that one event, so the two instrumentations compose.

- That composition also means there is strictly no need to enable
  this target for a Flask application the `flask` instrumentation
  already covers: that instrumentation records every request on its
  own, wherever the application is served, `app.run()` included.
  This target is for an application served through werkzeug directly
  (`run_simple`, `make_server`, or a framework without an
  instrumentation of its own); enabling both is harmless, one
  boundary either way.

- The wrap happens at server construction, werkzeug having no seam
  between server and application on the request path: removing the
  instrumentation stops the wrapping for servers built afterwards,
  while a server built during it keeps its wrapper for its own
  lifetime, recording only while sinks are active. The reloader's
  child process applies whatever instrumentation the program itself
  applies, so coverage there follows the program's own
  configuration.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `ignore_paths` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, everything beneath it included. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set. |

```toml
[[instrument]]
name = "werkzeug.serving"
ignore_paths = ["/health"]
redact = ["voucher"]
```

## How it patches

For the implementation detail see the module docstring of
[serving.py](serving.py).
