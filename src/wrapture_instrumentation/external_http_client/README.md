# http.client instrumentation

Wire-level tracing for
[http.client](https://docs.python.org/3/library/http.client.html),
the standard library module that does the actual HTTP wire work
beneath urllib, urllib3 (and so requests) and xmlrpc.client. Entry
point name `http.client`, the module it patches; the supported range
is a Python version range, `>=3.12`; fully removable.

## What this is, and is not

This is a debugging aid, not something to reach for automatically.
A higher-level HTTP client's instrumentation records each request as
a terminal node (a leaf) that covers everything the request did, and
that is the right everyday recording: one event per request, the
wire machinery beneath it silent. Enable `http.client` alongside it
and, by default, you will see nothing new at all.

Reach for it when you need to see what a higher-level client is
doing under the covers: where time went inside one slow request,
whether a connection was really reused, what actually crossed the
wire when a request misbehaved. That takes two config moves: enable
this instrumentation, and switch the higher-level client's events
out of being leaves, presuming its instrumentation offers the
switch (the `urllib.request` instrumentation does, as `leaf`):

```toml
[[instrument]]
name = "urllib.request"
leaf = false

[[instrument]]
name = "http.client"

[[sink]]
type = "printer"
```

Whether anything records here depends only on what is in flight
above: the phases are silent beneath any enabled higher-level
client's leaf, and record in full wherever no such leaf covers
them. A direct http.client connection, or a client whose own
instrumentation is not enabled, or that has none (xmlrpc.client, at
the time of writing), therefore shows its phases with no switch;
when such a client gains an enabled instrumentation of its own, its
leaf hides the phases in the same way, with the same `leaf = false`
switch to reveal them.

## What you see

One plain event per phase of each exchange, named by the patched
location:

```
urllib.request:OpenerDirector.open(fullurl='http://127.0.0.1:8000/orders', ...)
  http.client:HTTPConnection.putrequest(method='GET', url='/orders', ...)
  http.client:HTTPConnection.endheaders(message_body=None, encode_chunked=False)
    http.client:HTTPConnection.connect()
  http.client:HTTPConnection.getresponse()  -> '<HTTPResponse>'
```

- `putrequest` is the request line; `endheaders` sends the headers
  and any body; `getresponse` waits for the status line and headers,
  which is where request latency lives, and is annotated with the
  status.

- `connect` records inside the phase that first touched the socket,
  so a cold exchange shows it nested in `endheaders` and a reused
  keep-alive connection shows no `connect` at all: cold and warm
  tell apart by shape. An HTTPS connection records the same event.

- The events are deliberately plain: no `external` category, no
  leaf, no trace propagation. The exchange as a whole, the external
  contract keys and the outgoing trace identity all belong to the
  higher-level client's event above; this layer only shows how that
  event's time was spent.

- The capture policy is deliberate about sensitive data: the query
  string in `putrequest`'s url is recorded with the built-in
  sensitive names masked and the `redact` setting's names masked on
  top, the request body reduces to its size, the response to its
  type, and header values are never recorded (`putheader` is not
  patched, precisely because headers are where credentials travel).

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `redact` | `[]` | Query string parameters to mask by name in the recorded request line, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the server; only the recording is masked. |

```toml
[[instrument]]
name = "http.client"
redact = ["voucher"]
```

## How it patches

For the implementation detail, including why `request()` and
`putheader` are deliberately not patched, see the module docstring
of [client.py](client.py).
