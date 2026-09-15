# uvicorn instrumentation

Request tracing for applications served by
[uvicorn](https://www.uvicorn.org/), the most widely used ASGI
server. Entry point name `uvicorn`, the package it patches; supports
uvicorn 0.30 and later, below 1.0; fully removable, with the
werkzeug target's caveat that a server already running keeps its
wrapper for its own lifetime.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "uvicorn"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture uvicorn myapp:app`)
or through autowrapt injection, so the patch is in place before
uvicorn loads the application; in a test, the context manager
`wrapture.instrumentation("uvicorn")` scopes it to a block.

## What you see

One `request` event per request the server handles, whatever route
the application took into uvicorn: `uvicorn.run()`, a `Server` built
by hand around a `Config`, or gunicorn's `UvicornWorker`. The event
is named by the application's own module and qualname:

```
myapp:application(...)  -> '200 OK'  [4.1ms]
```

- The application is wrapped in wrapture's recording ASGI middleware
  at uvicorn's own seam, `Config.load`, where the server resolves
  the application; the application object itself never changes. The
  wrap lands inside uvicorn's own middlewares, around the
  application itself, so the event is named by the application
  rather than a uvicorn middleware, and the recorded scope is the
  one the application sees: with proxy headers on (uvicorn's
  default) the client and scheme are the forwarded values.

- Each event carries the method, path, query (with the built-in
  sensitive names masked), scheme and peer, the status line as its
  result, and the streaming shape of the response: the time to the
  response starting, the streaming tail, and the body message count.
  Everything recorded while the request is handled nests beneath it.

- The request boundary is where distributed trace identity arrives:
  a request carrying a `traceparent` header joins the caller's
  trace, so a request from an instrumented client (the `requests` or
  `httpx` targets, say) and the server's tree share one trace id.

- One boundary per request, however many layers record: an
  application that already carries its own recording middleware (an
  ASGI framework a framework instrumentation wrapped) still records
  once, the outer middleware marking the scope and the inner one
  passing through.

- Websocket and lifespan traffic passes through completely
  untouched; only HTTP requests record.

## Aspects

The instrumentation binds these aspects, each a group of call sites
with a switch, recording defaults and settings of its own:

| Aspect | Wraps | Records by default |
| ---- | ----- | ------------------ |
| `requests` (primary) | the application uvicorn loaded, wrapped in the recording ASGI middleware, one request event per request | the query string with the built-in sensitive names masked, plus any a `redact` list adds |

An aspect is addressed as a sub-table of the entry,
`[instrument.requests]`, and takes the recording keys an `[[observe]]`
entry does (`capture`, `capture_args`, `capture_result`, `redact`,
`redact_result`, `redact_marker`, `leaf` and `stack`) beside the
settings listed below, so `capture_result = "types"` or
`redact = ["token"]` under an aspect means exactly what it means on an
observe entry. `enabled = false` under an aspect switches it off, and a
bare `requests = false` on the entry means the same. The primary
aspect's keys may be written flat on the entry. The [aspects
section](https://wrapture.readthedocs.io/en/latest/instrumentation-packages.html#aspects)
of the wrapture documentation has the whole scheme.

## Settings

| Setting | Aspect | Default | Controls |
| ------- | ---- | ------- | -------- |
| `ignore_paths` | `requests` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, everything beneath it included. |

```toml
[[instrument]]
name = "uvicorn"
ignore_paths = ["/health"]
redact = ["voucher"]
```
## How it patches

For the implementation detail, including why the wrap lands inside
uvicorn's own middleware chain and what removal restores, see the
module docstring of [config.py](config.py).
