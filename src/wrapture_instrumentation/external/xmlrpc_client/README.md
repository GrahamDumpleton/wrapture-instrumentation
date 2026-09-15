# xmlrpc.client instrumentation

Remote call tracing and trace propagation for
[xmlrpc.client](https://docs.python.org/3/library/xmlrpc.client.html),
the standard library's XML-RPC client. Entry point name
`xmlrpc.client`, the module it patches; the supported range is a
Python version range, `>=3.12`; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "xmlrpc.client"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("xmlrpc.client"):
    ...
```

## What you see

One event per remote call made through a `ServerProxy`, however it
was spelled: an attribute call, a dotted method name, or a
`MultiCall` (one event for the batch, its operation
`system.multicall`):

```
xmlrpc.client:ServerProxy._ServerProxy__request(methodname='inventory.count', params='<2 values>')  -> '<int>'  [2.1ms]
```

The name is the patched location, `module:qualname` (the private
`__request` really is the one door every call passes through), and
the event is what makes it an external call: its category is
`external` and its data carries that category's keys, `method`
(always `POST`, the one verb XML-RPC uses), `url`, `host`, `port`
and `path` from where the proxy points, and `status`: 200 for any
parsed response, a `Fault` included, or the code a `ProtocolError`
carries; a call that never got a response (a refused connection)
records the error and no status. The RPC pair rides alongside, the
things the path cannot say: `system`, always `xmlrpc`, and the
method name as `operation`. wrapture's OpenTelemetry export maps
them to `rpc.system` and `rpc.method`, and names the span by the
operation (`inventory.count`) rather than by the URL every call to
the endpoint shares.

- The event is a terminal node of the tree, a leaf: it covers
  everything the call did, and nothing beneath it records, including
  the transport's silent retry when a kept-alive connection has gone
  cold. Switch `leaf = false` to see the transport's own event
  beneath each call, and enable the `http.client` instrumentation
  as well to see the wire phases under that.

- The current trace identity travels with every request, in the
  headers `wrapture.trace_headers()` gives, so a service that
  understands them joins the trace the call was made in. A header
  the application supplied itself (`ServerProxy(headers=...)`) is
  left alone.

- The capture policy is deliberate about sensitive data: a proxy URI
  may carry basic-auth credentials, so recorded hosts and URLs are
  stripped of any userinfo; the call's arguments reduce to a count
  and the result to its type, since both are application data; the
  XML body reduces to its size; and a `Fault`'s text is recorded
  only as part of the raised exception, as any exception is.

## Aspects

The instrumentation binds these aspects, each a group of call sites
with a switch, recording defaults and settings of its own:

| Aspect | Wraps | Records by default |
| ---- | ----- | ------------------ |
| `requests` (primary) | every remote call through a `ServerProxy`, as one external event, and the transport beneath it | `leaf = true`; params as a count, results as types, hosts stripped of credentials, an explicit capture key under the aspect replacing that |

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
name = "xmlrpc.client"
leaf = false
```
## How it patches

For the implementation detail see the module docstring of
[client.py](client.py).
