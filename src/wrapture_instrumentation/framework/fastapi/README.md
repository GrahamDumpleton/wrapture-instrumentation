# fastapi instrumentation

Request and route tracing for
[FastAPI](https://fastapi.tiangolo.com/) applications. Entry point
name `fastapi`, the package it patches; supports fastapi 0.110 and
later, below 1.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "fastapi"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patches are in place before the application module imports and its
routes are built; in a test, the context manager
`wrapture.instrumentation("fastapi")` scopes it to a block.

## What you see

One `request` event per request, whatever server carries the
application, with the matched route on it and the endpoint function
beneath it:

```
GET /quote/{item} (fastapi.applications:FastAPI.__call__)  -> '200 OK'
  quoted(item='widget')  -> {'item': 'widget', 'price': 42}
```

- The request boundary is wrapture's recording ASGI middleware,
  installed by decorating `FastAPI.__call__`, the application itself
  as a server calls it, the same seam the starlette target uses one
  class down. Each event carries the method, path, query (with the
  built-in sensitive names masked), scheme and peer, and the status
  line as its result.

- Once routing matches, the request event is annotated with the
  route's path pattern (`/quote/{item}`, an including router's
  prefix folded in) and its name, the low-cardinality grouping key
  the raw path is not; wrapture's OpenTelemetry export reads the
  pattern as `http.route` and names the span by it. A request that
  matched no route records with its raw path and no route keys.

- Every endpoint function is observed as its `APIRoute` is built,
  labelled by the route's name, sync and async endpoints alike, with
  FastAPI's dependency injection, response models and OpenAPI schema
  generation all reading the observed endpoint as the function it
  wraps. `include_router()` re-registers already-observed endpoints
  without stacking a second observation.

- An unhandled exception needs no extra machinery: the stack answers
  500 and re-raises, so the request event carries the exception
  beside the response's size, and the failing endpoint's own event
  carries it too. A validation failure (FastAPI's 422) and an
  `HTTPException` are control flow, and record as nothing but the
  status they produced.

- The request boundary is where distributed trace identity arrives:
  a request carrying a `traceparent` header joins the caller's
  trace.

## With the starlette and server instrumentations

Nothing to configure, and nothing doubled: FastAPI subclasses
Starlette, so with the `starlette` target applied as well both
boundaries stack and only the outer one records, the route
annotation landing on it; the fastapi target's own route bindings
exist because `APIRoute` builds and can dispatch without touching
the `Route` seams the starlette target patches. Under an
instrumented server (the `uvicorn` target), the same rule holds: one
boundary per request, however many layers record.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `ignore_paths` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, its endpoint included. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the application; only the recording is masked. |

```toml
[[instrument]]
name = "fastapi"
ignore_paths = ["/health"]
redact = ["voucher"]
```

## How it patches

For the implementation detail see the module docstrings of
[applications.py](applications.py) and [routing.py](routing.py).
