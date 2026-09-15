# aiohttp.web instrumentation

Request and route tracing for
[aiohttp](https://docs.aiohttp.org/) server applications. Entry
point name `aiohttp.web`, the module it patches; supports aiohttp
3.10 and later, below 4.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "aiohttp.web"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patches are in place before the application module imports and its
routes are registered; in a test, the context manager
`wrapture.instrumentation("aiohttp.web")` scopes it to a block.

## What you see

One `server`-categorised boundary per request, with the handler
function beneath it:

```
block: aiohttp.web  [148us, self 129us]
  quoted(request=<Request GET /quote/widget >)  -> <Response OK eof>  [19us]
```

- aiohttp is neither WSGI nor ASGI, so the request boundary is not a
  recording middleware but a block opened around the application's
  own dispatch (`Application._handle`), the seam every request
  passes through once however the application is composed, a
  sub-application's requests included. The boundary carries the
  method, path, scheme, peer and query (with the built-in sensitive
  names masked), and wrapture's OpenTelemetry export renders it as a
  SERVER span named access-log style by the matched route
  (`GET /quote/{item}`).

- Once routing matches, the boundary is annotated with the route's
  canonical pattern (`/quote/{item}`, a sub-application's prefix
  folded in) as `route`, the low-cardinality grouping key the raw
  path is not and what the OpenTelemetry export maps to
  `http.route`, and with the route's name, or failing that the
  handler's own name, as `endpoint`. A request that matched no route
  records with its raw path and no route keys.

- The response's status is annotated as `status`, and that includes
  aiohttp's way of answering with a raised `HTTPException`: raising
  `HTTPNotFound` is control flow that carries a status, so the
  boundary records the 404 and no exception. Anything else escaping
  the handling is a real failure: it records on the boundary, and
  the protocol answers its 500 on its own.

- Every handler function is observed as its route is registered,
  through any of the registration spellings, so each dispatch
  records the handler's call beneath the boundary, labelled by the
  route's name when one was given. A class-based `web.View`
  registers untouched and is named on the boundary only.

- The request boundary is where distributed trace identity arrives:
  a request carrying a `traceparent` header joins the caller's
  trace.

## Aspects

The instrumentation binds these aspects, each a group of call sites
with a switch, recording defaults and settings of its own:

| Aspect | Wraps | Records by default |
| ---- | ----- | ------------------ |
| `requests` (primary) | the application's request handling, one `server` boundary per request | the query string through `capture_args` (a `redact` list composes into it) on top of the built-in sensitive names; the boundary is a `block()` event, which captures no result, so the aspect takes `stack` and `leaf` beside that and refuses `capture_result` |
| `handlers` | handler functions, observed as their routes register | the request argument as its type (`capture_args = "types"`, its repr would carry the raw query string) and the result as its shape (`capture_result = "shape"`) |

An aspect is addressed as a sub-table of the entry,
`[instrument.handlers]`, and takes the recording keys an `[[observe]]`
entry does (`capture`, `capture_args`, `capture_result`, `redact`,
`redact_result`, `redact_marker`, `leaf` and `stack`) beside the
settings listed below, so `capture_result = "types"` or
`redact = ["token"]` under an aspect means exactly what it means on an
observe entry. `enabled = false` under an aspect switches it off, and a
bare `handlers = false` on the entry means the same. The primary
aspect's keys may be written flat on the entry. The [aspects
section](https://wrapture.readthedocs.io/en/latest/instrumentation-packages.html#aspects)
of the wrapture documentation has the whole scheme.

## Settings

| Setting | Aspect | Default | Controls |
| ------- | ---- | ------- | -------- |
| `ignore_paths` | `requests` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, its handler included. |
| `join` | `requests` | `true` | Joining the distributed trace an arriving request's `traceparent` header carries. Off, every request's tree mints its own identity. |

```toml
[[instrument]]
name = "aiohttp.web"
ignore_paths = ["/health"]
redact = ["voucher"]

[instrument.handlers]
capture_result = "types"
```
## How it patches

For the implementation detail see the module docstrings of
[web_app.py](web_app.py) and [web_urldispatcher.py](web_urldispatcher.py).
