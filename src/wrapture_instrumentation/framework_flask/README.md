# Flask instrumentation

Request and view tracing for [Flask](https://flask.palletsprojects.com/)
applications. Entry point name `flask`; supported versions Flask 3.x
(`>=3.0,<4`); fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "flask"

[[sink]]
type = "printer"
```

run under wrapture's runner so the patches are in place before the
application imports Flask:

```console
$ python -m wrapture -m myapp
```

In a test, the context manager form applies it for a scope and
removes it on exit:

```python
with wrapture.instrumentation("flask"):
    ...
```

## What you see

Every request records as one tree: the request itself at the root,
and every view function that ran beneath it.

```
GET /quote/widget (shop.wsgi_app)  -> '200 OK'  [507us, self 458us]
  quoted(item='widget')  -> '<Response 29 bytes [200 OK]>'  [49us]
GET /quote/missing (shop.wsgi_app)  -> '500 INTERNAL SERVER ERROR'  !! KeyError  [2.9ms]
  quoted(item='missing')  !! KeyError  [3us]
```

- The request is recorded by wrapture's WSGI middleware, installed on
  each application's `wsgi_app` as it is constructed, so module-level
  applications, application factories and several applications in one
  process all record, each labelled `<name>.wsgi_app` after its own
  import name. The request event carries the method, path, query
  string (sensitive parameter names masked), scheme and peer, and its
  result is the status line. A streamed response holds the request
  open until the server finishes consuming the body, and records the
  chunk count and body timing.

- Once routing has matched, the request event is annotated with the
  matched route pattern (`route = "/quote/<item>"`) and endpoint
  (`endpoint = "quoted"`), the low-cardinality keys to group by; the
  raw path stays as the per-request detail. A request that matched no
  route (a 404) has neither key.

- Every view function is observed as its route registers, wherever it
  came from: plain functions, `view_func` by keyword or position,
  blueprint views, and the generated view a `MethodView` registers.
  Each records as a call beneath its request, labelled by its
  endpoint (`quoted`, `reports.summary`, `catalog`), with the
  captured view arguments; the event's path still locates the actual
  code that ran.

- When a view raises and Flask converts the exception into its 500
  response, the exception is noted against the request event, so the
  request line reports both the status it answered and the failure
  behind it.

Applications built while the instrumentation was applied keep their
middleware and observed views after removal; they simply record
nothing once no sink is listening. Applications built before it
applied are untouched, which is why the runner applies configuration
before the application imports.

## Settings

None yet. Planned: `ignore_paths` (path globs excluded from
recording), redaction of nominated view and query parameters, and
switches for the lifecycle and handled-error layers as they land.

## Deliberately not traced

- Flask's internal request-processing machinery
  (`preprocess_request`, `process_response`, `dispatch_request` and
  friends): the patches use those as interception points, but they
  are plumbing, not your code, and record nothing of their own.
- Flask signals: blinker plumbing; bind the receivers ad hoc with
  wrapture if you need them.
- `jsonify`, `send_file`, `send_static_file`: response plumbing;
  static file traffic is better excluded wholesale once
  `ignore_paths` lands.

## How it patches

For the implementation detail (which choke points, and why those),
see the module docstrings in this directory, starting with
[app.py](app.py) for the `flask.app` patches.
