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
  quoted(item='widget')  -> <Response 29 bytes [200 OK]>  [49us]
GET /quote/missing (shop.wsgi_app)  -> '500 INTERNAL SERVER ERROR'  !! KeyError  [2.9ms]
  quoted(item='missing')  !! KeyError  [3us]
```

An application with lifecycle callbacks and error handlers records
those too, in the order Flask runs them:

```
GET /shaky (portal.wsgi_app)  -> '422 UNPROCESSABLE ENTITY'  !! ValueError  [671us]
  portal.audit_request()  -> None  [4us]
  shaky()  !! ValueError  [2us]
  portal.shaky_handler(error=ValueError('bad input'))  -> (<Response 22 bytes [422 ...]>, 422)  [36us]
  portal.stamp_response(response=<Response 22 bytes [422 ...]>)  -> <Response ...>  [7us]
  portal.request_done(exc=None)  -> None  [4us]
  portal.context_done(exc=None)  -> None  [3us]
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

- Every lifecycle callback is observed as it registers, however it
  registers: `before_request`, `after_request`, `teardown_request`
  and `teardown_appcontext` on the application, the same three on a
  blueprint (running only for its routes), and the blueprint
  `*_app_request` variants. Each run records as a call beneath the
  request whose handling invoked it, in Flask's own order.

- Error handlers registered with `register_error_handler`, the
  `errorhandler` decorator, or a blueprint's `app_errorhandler` are
  observed the same way, so a handled failure shows the handler
  running beneath its request.

- When a view raises and no handler claims the exception, Flask
  answers 500 and the exception is noted against the request event.
  When a registered handler absorbs a real exception and turns it
  into a response, the exception is still noted, so the failure
  leaves its mark beside whatever status the handler chose. An
  `HTTPException` (`abort()`, a 404) is control flow, not a failure,
  and is never noted; its handler is still observed. Either way the
  request line reports both the status it answered and any failure
  behind it.

Applications built while the instrumentation was applied keep their
middleware and observed views after removal; they simply record
nothing once no sink is listening. Applications built before it
applied are untouched, which is why the runner applies configuration
before the application imports.

## Settings

The instrumentation is layered, and the optional layers have
switches; the core (the request tree, route and endpoint annotation,
view observation, error handler observation, and unhandled-exception
noting) is the point of the instrumentation and is always on.

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `lifecycle` | `true` | Observing before/after/teardown callbacks as they register. Every registered callback runs on every request (extensions register these liberally: user loaders, session cleanup, header stamping), so this is the layer to switch off when the trees are noisier than they are informative. The callbacks still run; they run unobserved. |
| `handled_errors` | `true` | Noting an exception a registered handler absorbed against its request. The handler's own run is core and stays observed either way. |

Settings go in the `[[instrument]]` entry:

```toml
[[instrument]]
name = "flask"
lifecycle = false
```

Planned: `ignore_paths` (path globs excluded from recording) and
redaction of nominated view and query parameters.

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
