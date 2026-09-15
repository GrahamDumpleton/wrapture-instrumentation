# xmlrpc.server instrumentation

Request and dispatch tracing for
[xmlrpc.server](https://docs.python.org/3/library/xmlrpc.server.html),
the standard library's XML-RPC server. Entry point name
`xmlrpc.server`, the module it patches; the supported range is a
Python version range, `>=3.12`; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "xmlrpc.server"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("xmlrpc.server"):
    ...
```

## What you see

One tree per XML-RPC POST a `SimpleXMLRPCServer` handles: a request
boundary labelled `xmlrpc.server`, with one event beneath it for
each procedure the request dispatched:

```
xmlrpc.server(method='POST', path='/RPC2', client='127.0.0.1', status=200)
  xmlrpc.server:SimpleXMLRPCDispatcher._dispatch(method='inventory.count', params='<2 values>')  -> '<int>'
```

- The boundary is a `block` event of category `server` carrying
  `system` (`xmlrpc`), the request `method`, `path` and `client`
  address, and the response `status` the handler sent: 200 with a
  marshalled response, 404 for a path outside the handler's
  `rpc_paths`, 500 for an internal error. Its recorded path is the
  call site inside this instrumentation, so the label
  `xmlrpc.server` is what names it. On wrapture's OpenTelemetry
  export the category makes it a SERVER span named access-log style
  (`POST /RPC2`), with the request keys on their semantic-convention
  names, `system` as `rpc.system`, and only a 5xx marking the span
  in error, since on the server side a 4xx is the caller's fault.

- The boundary is where distributed trace identity arrives: a
  request carrying a `traceparent` header (the one an instrumented
  `xmlrpc.client` sends) makes the handling part of the caller's
  trace, exactly as the WSGI and ASGI middlewares join at their
  boundary, so both sides of a call share one trace id across
  processes. A request with no such header roots a trace of its own.

- Each dispatched procedure records as one event on
  `SimpleXMLRPCDispatcher._dispatch`, annotated with the method name
  as `operation`. A `system.multicall` shows the batch's dispatch
  with each sub-call's dispatch nested inside it. A `Fault` a
  procedure raises is recorded on its dispatch event as any
  exception is, while the boundary still reports the 200 the fault
  was marshalled into, the failure being the application's.

- The capture policy mirrors the client side: the call's params
  reduce to a count and every result to its type, both being
  application data; the request headers only ever feed the trace
  join and are never recorded; the body is never read.

Two shapes stay out of view: `CGIXMLRPCRequestHandler` has no
`do_POST` and records nothing, and a request-handler subclass that
defines its own `_dispatch` (the legacy hook `do_POST` still
honours) bypasses the per-procedure event, though the boundary still
records.

## Aspects

The instrumentation binds these aspects, each a group of call sites
with a switch, recording defaults and settings of its own:

| Aspect | Wraps | Records by default |
| ---- | ----- | ------------------ |
| `requests` (primary) | the POST handler, one `server` boundary per request | a `block()` event, which captures no values: the aspect takes `stack` and `leaf` and refuses the capture keys |
| `methods` | each dispatched procedure on `_dispatch`, beneath its request | params as a count (`capture_args`) and the result as its shape (`capture_result = "shape"`), both being application data whatever their form |

An aspect is addressed as a sub-table of the entry,
`[instrument.methods]`, and takes the recording keys an `[[observe]]`
entry does (`capture`, `capture_args`, `capture_result`, `redact`,
`redact_result`, `redact_marker`, `leaf` and `stack`) beside the
settings listed below, so `capture_result = "types"` or
`redact = ["token"]` under an aspect means exactly what it means on an
observe entry. `enabled = false` under an aspect switches it off, and a
bare `methods = false` on the entry means the same. The primary aspect's
keys may be written flat on the entry. The [aspects
section](https://wrapture.readthedocs.io/en/latest/instrumentation-packages.html#aspects)
of the wrapture documentation has the whole scheme.

## Settings

| Setting | Aspect | Default | Controls |
| ------- | ---- | ------- | -------- |
| `join` | `requests` | `true` | Whether the boundary joins the distributed trace an arriving request's `traceparent` header carries. Off, every request roots a trace of its own and the headers are never parsed. Recording is unaffected. |

```toml
[[instrument]]
name = "xmlrpc.server"
join = false

[instrument.methods]
capture_result = "summary"
```
## How it patches

For the implementation detail see the module docstring of
[server.py](server.py).
