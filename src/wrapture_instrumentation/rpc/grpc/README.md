# gRPC instrumentation

Call and handler tracing for [gRPC](https://grpc.io/), client and
server sides in one instrumentation. Entry point name `grpc`, the
package it patches (the distribution is `grpcio`); supports grpcio
1.76 and later, below 2.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "grpc"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patches are in place before channels and servers are built; in a
test, the context manager `wrapture.instrumentation("grpc")` scopes
it to a block.

## What you see

One external leaf per RPC a channel makes, and one `server`
boundary per RPC a server handles:

```
grpc:Channel.unary_unary()  -> '<_UnaryOutcome>'
block: grpc
```

- Both sides ride gRPC's own interceptor machinery, injected at the
  public factories rather than reaching into internals:
  `insecure_channel` and `secure_channel` hand their channel back
  wrapped with a client interceptor covering all four call shapes,
  and `server()` gets a server interceptor prepended. The `client`
  and `server` settings switch either half off; by default both are
  on, and a process that only ever creates channels simply never
  builds a server interceptor.

- Every event carries `system` (`grpc`) with the `service` and
  `operation` split out of the method path
  (`/package.Service/Method`), which wrapture's OpenTelemetry export
  maps to `rpc.system`, `rpc.service` and `rpc.method`. Client
  events add the channel's `host` and `port`; server boundaries the
  calling `client` address.

- An error code is a status, not an exception: a failed RPC records
  its `code` (`NOT_FOUND`, `UNAVAILABLE`) on the client leaf, the
  `RpcError` still raised to the application by gRPC itself. On the
  server, an `abort()` is control flow, the boundary recording the
  code it set and staying clean; an exception the handler lets
  escape is the failure it is, recorded on the boundary beside the
  `UNKNOWN` gRPC answers with.

- Streaming follows the database targets' model: the client event
  is the call being made, and consuming a streamed response is the
  application's business, not tracked, so such an event carries no
  code (the same holds for a `future()` call still in flight). A
  server-side streaming handler is different: its generator body is
  the server's own work inside the RPC, so the boundary spans it to
  exhaustion.

- The boundary joins the distributed trace the invocation metadata
  carries (the `join` setting), and the client adds the current
  trace identity to each call's metadata (the `propagate` setting),
  a key the application set itself left alone: an instrumented
  client calling an instrumented server shares one trace id carried
  by nothing but the metadata.

- Request and response payloads are never captured, on either side,
  and metadata values are never recorded. An RPC no handler matches
  is answered `UNIMPLEMENTED` by gRPC before any handler exists to
  wrap, so only the client's leaf records it.

- `grpc.aio` is not yet covered: the async factories and
  interceptor interfaces are a separate surface, left to a
  follow-up.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `client` | `true` | Record every RPC made through a channel as an external leaf, with the trace identity carried in its metadata. |
| `server` | `true` | Record every RPC the server handles as a request boundary spanning the handler's run. |
| `propagate` | `true` | Add the current trace identity to each outgoing RPC's metadata so the service called can join the trace. |
| `join` | `true` | Join the distributed trace an incoming RPC's metadata carries instead of rooting a new one. |

```toml
[[instrument]]
name = "grpc"
server = false
```

## How it patches

For the implementation detail see the module docstring of
[interceptors.py](interceptors.py).
