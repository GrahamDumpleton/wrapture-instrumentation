# requests instrumentation

Outbound request tracing and trace propagation for
[requests](https://requests.readthedocs.io/), the most widely used
Python HTTP client. Entry point name `requests`, the package it
patches; supports requests 2.31 and later in the 2.x line; fully
removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "requests"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("requests"):
    ...
```

## What you see

One event per request the application makes, whether through the
module-level helpers (`requests.get` and friends), `Session.request`,
or a `Session.send` it calls itself:

```
requests.sessions:Session.send(request='http://127.0.0.1:8000/orders', kwargs={'timeout': 5, 'allow_redirects': True, 'proxies': '<OrderedDict>', 'stream': False, 'verify': True, 'cert': None})  -> '<Response>'  [4.2ms]
```

The name is the patched location, `module:qualname`, and the event
is what makes it an external call: its category is `external`, and
its data carries the keys that category promises. Each event holds
`method`, `url` (with the query string and any credentials removed),
`host`, `port`, `path` and `query` from the request, and `status`
from the response. requests answers a 4xx or 5xx with a response
rather than an exception, so an error status is recorded like any
other status; the event carries an exception only when the exchange
really failed (a refused connection, a name that does not resolve,
too many redirects), and then there is no status.

- The event is a terminal node of the tree, a leaf: it covers
  everything the send did, and nothing beneath it records. A
  redirect is one event named by the URL the application asked for,
  carrying the status of where it ended up; the nested send each hop
  makes is hidden. That matches what the caller did, which was one
  request. With `allow_redirects=False` the caller handles the
  redirect itself, and the event carries the 3xx it was given.

- Unless the caller asked to stream, requests reads the whole body
  before `send` returns, so the event covers the exchange with its
  download included. With `stream=True` the event ends when the
  headers are in, and reading the body afterwards is not part of it.

- The current trace identity travels with every request, in the
  headers `wrapture.trace_headers()` gives (`traceparent` and
  `tracestate`), so a service that understands them joins the trace
  the request was made in. A redirect hop's request copies the outer
  request's headers, so every hop carries it. A header the
  application set itself is left alone.

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
| `leaf` | `true` | Whether each send is a terminal node. Off, the nested send behind each redirect hop records as a child of the outer send, and anything else instrumented beneath it shows too (the `http.client` wire phases, when that target is applied as well). |
| `propagate` | `true` | Whether the trace identity is added to each request's headers. Off when calling services that should not see it, or when the application manages its own trace headers. Recording is unaffected. |
| `redact` | `[]` | Query string parameters to mask by name in the recorded `query`, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the server; only the recording is masked. |

```toml
[[instrument]]
name = "requests"
propagate = false
redact = ["voucher"]
```

## With a framework instrumentation

Nothing to configure: with `flask` applied as well, a request handled
by the application records as one tree, and each requests call the
view makes is a leaf beneath it, carrying the tree's trace identity
onward.

## How it patches

For the implementation detail see the module docstring of
[sessions.py](sessions.py).
