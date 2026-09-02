# wsgiref.simple_server instrumentation

Request tracing for applications served by
[wsgiref.simple_server](https://docs.python.org/3/library/wsgiref.html#module-wsgiref.simple_server),
the standard library's WSGI server. Entry point name
`wsgiref.simple_server`, the module it patches; the supported range
is a Python version range, `>=3.12`; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "wsgiref.simple_server"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("wsgiref.simple_server"):
    ...
```

## What you see

The server's application, however it was handed over (`make_server`,
`set_app`, a subclass), is wrapped in wrapture's recording WSGI
middleware at the server's own seam, `WSGIServer.get_app`, without
the application changing at all. Each request then records as one
`request` event named by the application's own module and qualname,
with everything recorded while it is handled nested beneath:

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

- Removing the instrumentation restores `get_app`, which stops the
  wrapping immediately, servers already running included.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `ignore_paths` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, everything beneath it included. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set. |

```toml
[[instrument]]
name = "wsgiref.simple_server"
ignore_paths = ["/health"]
redact = ["voucher"]
```

## How it patches

For the implementation detail see the module docstring of
[simple_server.py](simple_server.py).
