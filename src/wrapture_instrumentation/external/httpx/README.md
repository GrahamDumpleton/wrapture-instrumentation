# httpx instrumentation

Outbound request tracing and trace propagation for
[httpx](https://www.python-httpx.org/), the widely used sync and
async HTTP client. Entry point name `httpx`, the package it patches;
supports httpx 0.27 and later, below 1.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "httpx"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("httpx"):
    ...
```

## What you see

One event per request the application makes, whether through the
module-level helpers (`httpx.get` and friends), a `Client` or an
`AsyncClient`, `request`, `stream` or a `send` it calls itself. The
sync and async clients mirror each other, so the two patched
locations differ only in the class name:

```
httpx:Client.send(request='http://127.0.0.1:8000/orders', stream=False, auth='<UseClientDefault>', follow_redirects='<UseClientDefault>')  -> '<Response>'  [4.2ms]
httpx:AsyncClient.send(request='http://127.0.0.1:8000/orders', stream=False, auth='<UseClientDefault>', follow_redirects='<UseClientDefault>')  -> '<Response>'  [4.2ms]
```

The name is the patched location, `module:qualname` (the classes
live in `httpx._client`, but httpx stamps its re-exported classes
with the public package as their module, and the binding waits for
that, so the derived path says the public spelling in every import
order), and the event
is what makes it an external call: its category is `external`, and
its data carries the keys that category promises. Each event holds
`method`, `url` (with the query string and any credentials removed),
`host`, `port`, `path` and `query` from the request, and `status`
from the response. httpx answers a 4xx or 5xx with a response rather
than an exception, so an error status is recorded like any other
status; the event carries an exception only when the exchange really
failed (a refused connection, a name that does not resolve, too many
redirects), and then there is no status.

- The event is a terminal node of the tree, a leaf: it covers
  everything the send did, and nothing beneath it records. An async
  send records around the await, so its timing is the exchange, not
  the time to create the coroutine.

- httpx follows redirects only when asked. Unasked, the caller sees
  the 3xx itself and the event carries it. With `follow_redirects`
  on, the hops are resolved in a loop inside the one send, so a
  followed redirect is one event whatever the `leaf` key says,
  named by the URL the application asked for and carrying the status
  of where it ended up.

- Unless the caller asked to stream, httpx reads the whole body
  before `send` returns, so the event covers the exchange with its
  download included. With `stream()` or `send(..., stream=True)` the
  event ends when the headers are in, and reading the body
  afterwards is not part of it.

- The current trace identity travels with every request, in the
  headers `wrapture.trace_headers()` gives (`traceparent` and
  `tracestate`), so a service that understands them joins the trace
  the request was made in. A redirect hop's request copies the
  headers of the one before it, so every hop carries it. A header
  the application set itself is left alone.

- The capture policy is deliberate about sensitive data: the query
  string is recorded once, as `query`, in the form wrapture's request
  middlewares record it inbound, with the built-in sensitive names
  (passwords, tokens, keys, session ids and signatures) always
  masked and the `redact` key's names masked on top; the
  captured `request` argument and the `url` key carry no query and
  no userinfo credentials at all. The request body is never
  recorded, and the response reduces to its type. The application's
  own request headers are not recorded.

## Aspects

The instrumentation binds these aspects, each a group of call sites
with a switch, recording defaults and settings of its own:

| Aspect | Wraps | Records by default |
| ---- | ----- | ------------------ |
| `requests` (primary) | every send through a `Client` or an `AsyncClient`, as one external event | `leaf = true`; the recorded `query` through `capture_args` (a `redact` list composes into it), the call's own arguments and the response reduced by the package whatever the level: the URL without its query, a body as its size, a response as its type |

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
| `propagate` | `requests` | `true` | Whether the trace identity is added to each request's headers. Off when calling services that should not see it, or when the application manages its own trace headers. Recording is unaffected. |

```toml
[[instrument]]
name = "httpx"
propagate = false
redact = ["voucher"]
```
## With a framework instrumentation

Nothing to configure: with `flask` applied as well, a request handled
by the application records as one tree, and each httpx call the view
makes is a leaf beneath it, carrying the tree's trace identity
onward. The async client slots beneath async frameworks the same
way.

## How it patches

For the implementation detail see the module docstring of
[_client.py](_client.py).
