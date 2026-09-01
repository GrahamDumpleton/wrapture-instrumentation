# urllib instrumentation

Outbound request tracing and trace propagation for
[urllib.request](https://docs.python.org/3/library/urllib.request.html),
the standard library's HTTP client. Entry point name `urllib`; the
target is the standard library, so the supported range is a Python
version range, `>=3.12`, every Python wrapture itself runs on; fully
removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "urllib"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("urllib"):
    ...
```

## What you see

One event per request the application makes, whether through
`urlopen()`, `urlretrieve()`, an opener from `build_opener()`, or a
standard library module that uses urllib itself:

```
urllib.request:OpenerDirector.open(fullurl='http://127.0.0.1:8000/orders', data='<24 bytes>', timeout='<default>')  -> '<HTTPResponse>'  [3.1ms]
```

The name is the patched location, `module:qualname`, and the event
is what makes it an external call: its category is `external`, and
its data carries the keys that category promises. Each event holds
`method`, `url` (with the query string removed), `host`, `port`,
`path` and `query` from the request, and `status` from the response,
whether that came back normally or as the `HTTPError` urllib raises
for a 4xx or 5xx. A request that never got a status (a refused
connection, a name that does not resolve) records the error and no
status.

- The event is a terminal node of the tree, a leaf: it covers
  everything the open did, and nothing beneath it records. A
  redirect is one event named by the URL the application asked for,
  carrying the status of where it ended up; the nested open urllib
  made to follow it is hidden. That matches what the caller did,
  which was one request.

- The event covers connecting, sending the request and waiting for
  the status line and headers, which is when `open` returns. Reading
  the body happens afterwards on the response and is not part of the
  event, so a slow body download is not attributed to it.

- The current trace identity travels with every request, in the
  headers `wrapture.trace_headers()` gives (`traceparent` and
  `tracestate`), so a service that understands them joins the trace
  the request was made in. Every hop of a redirect carries it. A
  header the application set itself is left alone.

- The capture policy is deliberate about sensitive data: the query
  string is recorded once, as `query`, in the form wrapture's request
  middlewares record it inbound, with the built-in sensitive names
  (passwords, tokens, keys, session ids and signatures) always
  masked and the `redact` setting's names masked on top; the
  captured `fullurl` argument and the `url` key carry no query at
  all. The request body reduces to its size and the response to its
  type. URLs without their query, hostnames and paths pass; they name
  where the request went, not what it carried. The application's own
  request headers are not recorded.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `leaf` | `true` | Whether each open is a terminal node. Off, the nested open behind a redirect or an authentication retry records as a child of the outer open, and anything else instrumented beneath it shows too, for looking at what urllib itself did. |
| `propagate` | `true` | Whether the trace identity is added to each request's headers. Off when calling services that should not see it, or when the application manages its own trace headers. Recording is unaffected. |
| `redact` | `[]` | Query string parameters to mask by name in the recorded `query`, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the server; only the recording is masked. |

```toml
[[instrument]]
name = "urllib"
propagate = false
redact = ["voucher"]
```

## With a framework instrumentation

Nothing to configure: with `flask` applied as well, a request handled
by the application records as one tree, and each urllib request the
view makes is a leaf beneath it, carrying the tree's trace identity
onward.

## How it patches

For the implementation detail see the module docstring of
[request.py](request.py).
