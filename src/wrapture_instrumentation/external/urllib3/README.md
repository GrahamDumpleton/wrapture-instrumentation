# urllib3 instrumentation

Outbound request tracing and trace propagation for
[urllib3](https://urllib3.readthedocs.io/). Entry point name
`urllib3`, the package it patches; supports urllib3 1.26 and later,
below 3.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "urllib3"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patches are in place before the code that makes requests imports
urllib3; in a test, the context manager
`wrapture.instrumentation("urllib3")` scopes it to a block.

## What you see

One external leaf per request, however it was issued, named by the
door it entered by and carrying its status:

```
urllib3.poolmanager:PoolManager.urlopen(method='GET', url='http://api/quote')  -> '<HTTPResponse>'
```

- A request enters by one of two doors. `PoolManager.urlopen` is the
  redirect-following entry a pool manager, the module-level
  `urllib3.request` and requests on top of urllib3 all use;
  `HTTPConnectionPool.urlopen` is the lower door bare-pool code uses
  directly (the binding on it covers `HTTPSConnectionPool`, which
  does not override it). Both are external leaves sharing one depth
  count, so the request the caller made is one event whichever door
  it entered by, and the nested calls beneath it, the manager's
  delegation to a pool, a followed redirect, a retry, are folded in.

- The event carries the external category's contract keys, read from
  the pool instance and the request URL together: the pool knows the
  scheme, host and port, and the URL carries the path and query (at
  the manager door the whole absolute URL, whose own host and port
  then win). The recorded URL is absolute whichever door recorded
  it.

- urllib3 answers a 4xx or 5xx with a response rather than an
  exception, so the status is recorded from whatever came back; the
  event carries an exception only when the exchange really failed (a
  refused connection, a name that does not resolve, retries
  exhausted), in which case there is no status.

- The query is recorded through `wrapture.capture_query()`, so the
  built-in sensitive names are always masked, plus any the `redact`
  setting adds. The call's arguments are not captured (method and URL
  are already the contract keys in the event's data, and `urlopen`'s
  wide signature would spell out every defaulted keyword as noise);
  the request body is never recorded and the response reduces to its
  type.

- Propagation is the other half: the current trace identity is added
  to the request's headers before it is sent, so a service that
  understands them joins the trace; a header the application set
  itself is left alone, and a redirect hop carries the identity as
  the header already present.

## With the requests instrumentation

requests does its wire work through urllib3, so with both applied the
requests leaf silences urllib3 beneath it and one event records per
request. Switch the requests `leaf` off and urllib3's request shows
beneath the send, itself a leaf that then hides `http.client` below
it, the same layering as urllib over http.client. A direct urllib3
call beside requests records its own leaf either way.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `leaf` | `true` | Record each request as a terminal node, so the nested calls behind a redirect, a retry or the manager's delegation to a pool, and anything recorded beneath it, stay out of the tree. Off exposes that machinery. |
| `propagate` | `true` | Add the current trace identity to each request's headers so the service called can join the trace. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the server; only the recording is masked. |

```toml
[[instrument]]
name = "urllib3"
redact = ["voucher"]
```

## How it patches

For the implementation detail see the module docstring of
[pools.py](pools.py).
