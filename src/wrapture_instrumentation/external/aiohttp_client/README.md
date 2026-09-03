# aiohttp client instrumentation

Outbound request tracing and trace propagation for
[aiohttp](https://docs.aiohttp.org/)'s client. Entry point name
`aiohttp.client`, the module it patches; supports aiohttp 3.10 and
later, below 4.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "aiohttp.client"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patch is in place before the code that makes requests imports
aiohttp; in a test, the context manager
`wrapture.instrumentation("aiohttp.client")` scopes it to a block.

## What you see

One external leaf per request, named by the URL the application
asked for and carrying its status:

```
aiohttp.client:ClientSession._request(method='GET', str_or_url='http://api/quote')  -> '<ClientResponse>'
```

- The binding is on `ClientSession._request`, the one coroutine the
  verb helpers (`session.get` and friends), `session.request` and a
  streamed `async with` request all pass through. It is an external
  leaf: the event is the exchange as the caller sees it, and nothing
  beneath it records. The event carries the external category's
  contract keys: method, URL (the query string and any userinfo
  stripped), host, port, path, query (recorded with the built-in
  sensitive names masked, plus any the `redact` setting adds) and
  the status.

- aiohttp answers a 4xx or 5xx with a response rather than an
  exception (unless `raise_for_status` was asked for), so the status
  is recorded from whatever came back; the event carries an
  exception only when the exchange really failed (a refused
  connection, a name that does not resolve), in which case there is
  no status.

- A followed redirect is one event, not a nested request: aiohttp
  resolves the hops in a loop inside the one `_request` call, named
  by the URL asked for and carrying the status of where it ended up,
  whatever the `leaf` setting says.

- The coroutine returns once the response headers are in, the body
  read afterwards, so the event covers the exchange to the
  response's start, not the download. The request body is never
  recorded, and the call's arguments are not captured, the method
  and URL living in the event's data instead. Query parameters
  supplied through `params=` rather than in the URL are not folded
  into the recording.

- Propagation is the other half: the current trace identity is added
  to the request's headers before it is sent, so a service that
  understands them joins the trace; a header the application set
  itself is left alone, and aiohttp copies the headers onto each
  redirect hop, so the identity travels the whole chain.

## With the aiohttp.web instrumentation

An instrumented client driving an instrumented aiohttp server shares
one distributed trace: the client's leaf propagates the identity in
the `traceparent` header, and the server's request boundary joins
it, one trace id across the two sides carried by nothing but the
header.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `leaf` | `true` | Record each request as a terminal node, so anything recorded beneath it stays out of the tree. Off exposes what the client does internally, though a redirect stays one event either way. |
| `propagate` | `true` | Add the current trace identity to each request's headers so the service called can join the trace. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the server; only the recording is masked. |

```toml
[[instrument]]
name = "aiohttp.client"
propagate = false
redact = ["voucher"]
```

## How it patches

For the implementation detail see the module docstring of
[client.py](client.py).
