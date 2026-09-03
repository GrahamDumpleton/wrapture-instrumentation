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

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `ignore_paths` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, everything beneath it included. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the application; only the recording is masked. |

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
