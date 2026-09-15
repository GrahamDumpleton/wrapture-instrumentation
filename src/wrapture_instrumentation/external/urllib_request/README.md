# urllib.request instrumentation

Outbound request tracing and trace propagation for
[urllib.request](https://docs.python.org/3/library/urllib.request.html),
the standard library's HTTP client. Entry point name
`urllib.request`, the module it patches; the
target is the standard library, so the supported range is a Python
version range, `>=3.12`, every Python wrapture itself runs on; fully
removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "urllib.request"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("urllib.request"):
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
  masked and the `redact` key's names masked on top; the
  captured `fullurl` argument and the `url` key carry no query at
  all. The request body reduces to its size and the response to its
  type. URLs without their query, hostnames and paths pass; they name
  where the request went, not what it carried. The application's own
  request headers are not recorded.

## Aspects

The instrumentation binds these aspects, each a group of call sites
with a switch, recording defaults and settings of its own:

| Aspect | Wraps | Records by default |
| ---- | ----- | ------------------ |
| `requests` (primary) | every open through an `OpenerDirector`, as one external event | `leaf = true`; the recorded `query` through `capture_args` (a `redact` list composes into it), the call's own arguments and the response reduced by the package whatever the level: the URL without its query, a body as its size, a response as its type |

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
name = "urllib.request"
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
