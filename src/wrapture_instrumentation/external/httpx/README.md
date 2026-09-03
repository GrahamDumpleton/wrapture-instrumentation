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
  followed redirect is one event whatever the `leaf` setting says,
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
  masked and the `redact` setting's names masked on top; the
  captured `request` argument and the `url` key carry no query and
  no userinfo credentials at all. The request body is never
  recorded, and the response reduces to its type. The application's
  own request headers are not recorded.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `leaf` | `true` | Whether each send is a terminal node. Off, anything else instrumented beneath it shows. httpx does not sit on `http.client`, and its redirect hops are not nested sends, so unlike the requests target there is nothing further from httpx itself to expose. |
| `propagate` | `true` | Whether the trace identity is added to each request's headers. Off when calling services that should not see it, or when the application manages its own trace headers. Recording is unaffected. |
| `redact` | `[]` | Query string parameters to mask by name in the recorded `query`, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the server; only the recording is masked. |

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
