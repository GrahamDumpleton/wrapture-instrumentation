# starlette instrumentation

Request and route tracing for
[Starlette](https://www.starlette.io/), the ASGI framework FastAPI
builds on. Entry point name `starlette`, the package it patches;
supports starlette 0.47 and later, below 2.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "starlette"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patches are in place before the application module imports and its
routes are built; in a test, the context manager
`wrapture.instrumentation("starlette")` scopes it to a block.

## What you see

One `request` event per request, whatever server carries the
application, with the matched route on it and the endpoint function
beneath it:

```
GET /quote/widget (starlette.applications:Starlette.__call__)  -> '200 OK'
  quoted(...)  -> <PlainTextResponse ...>
```

- The request boundary is wrapture's recording ASGI middleware,
  installed by decorating `Starlette.__call__`, the application
  itself as a server calls it. Each event carries the method, path,
  query (with the built-in sensitive names masked), scheme and peer,
  and the status line as its result.

- Once routing matches, the request event is annotated with the
  route's path pattern (`/quote/{item}`) and its name, the
  low-cardinality grouping key the raw path is not; wrapture's
  OpenTelemetry export reads the pattern as `http.route` and names
  the span by it. A request that matched no route (a 404) records
  with its raw path and no route keys. A route inside a `Mount`
  annotates the pattern it owns, the part below the mount point.

- Every endpoint function is observed as its `Route` is built,
  labelled by the route's name (the function's name unless the route
  was given one), so it records as a call beneath its request, sync
  and async endpoints alike. A class-based endpoint, a mounted ASGI
  application or a `functools.partial` passes through untouched: the
  request boundary and its route annotation still tell the story.

- An unhandled exception needs no extra machinery: starlette answers
  500 and re-raises, so the request event carries the status and the
  exception together, and the failing endpoint's own event carries
  it too. An `HTTPException` is control flow and records as nothing
  but the status it produced.

- The request boundary is where distributed trace identity arrives:
  a request carrying a `traceparent` header joins the caller's
  trace.

## With a server instrumentation

Nothing to configure: under an instrumented server (the `uvicorn`
target, or any recording middleware a server interposes), a request
still records as one tree. The outer middleware records and marks
the scope, the application's own passes through, and the route
annotation lands on the one boundary.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `ignore_paths` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, its endpoint included. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the application; only the recording is masked. |

```toml
[[instrument]]
name = "starlette"
ignore_paths = ["/health"]
redact = ["voucher"]
```

## How it patches

For the implementation detail see the module docstrings of
[applications.py](applications.py) and [routing.py](routing.py).
