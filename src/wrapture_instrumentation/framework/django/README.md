# django instrumentation

Request, database and template tracing for
[Django](https://www.djangoproject.com/). Entry point name `django`,
the package it patches; supports Django 4.2 and later, below 7.0;
fully removable. One instrumentation whose events span three
categories: requests from the handler boundary, database events from
the ORM's cursor seam, template events from DTL rendering.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "django"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patches are in place before Django imports; in a test, the context
manager `wrapture.instrumentation("django")` scopes it to a block.

## What you see

One `request` event per request, WSGI and ASGI alike, with the
matched route on it, the view beneath it, and the view's queries and
template renders beneath that:

```
GET /quote/widget/ (django.core.handlers.wsgi:WSGIHandler.__call__)  -> '200 OK'
  quoted(...)  -> <HttpResponse ...>
    CursorWrapper.execute(...)  -> ...
    Template.render(...)  -> '<27 chars>'
```

- The request boundary is wrapture's recording WSGI or ASGI
  middleware, installed by decorating the handler's own `__call__`,
  the callable a server actually invokes. Each event carries the
  method, path, query (with the built-in sensitive names masked),
  scheme and peer, and the status line as its result. A request
  carrying a `traceparent` header joins the caller's trace.

- Once dispatch has resolved the URL, the request event is annotated
  with the route pattern (`archive/<int:year>/`) and the view name
  from `resolver_match`, the low-cardinality grouping key the raw
  path is not; wrapture's OpenTelemetry export reads the pattern as
  `http.route` and names the span by it. A request that matched no
  route (a 404) records with its raw path and no route keys. A view
  that raised still gets its route keys.

- Every view is observed as URL resolution constructs its
  `ResolverMatch`, labelled by the URL pattern's name when it has
  one, so it records as a call beneath its request under the name
  Django knows it by; an unnamed pattern's view keeps its
  module-qualified path as its identity. A class-based view records
  as one event for the whole view (its `dispatch` and HTTP-method
  methods run inside it), and an async view is still awaited: the
  observed proxy reads as a coroutine function to Django's own
  checks. The view's captured request argument reduces to its type
  (its repr carries the raw query string); URL-derived arguments
  pass. Two deliberate gaps: `resolve("/x/").func` compares equal
  to the view but is not the same object under instrumentation, and
  the 404/500 error-handler views resolve outside `ResolverMatch`
  and are not observed.

- An unhandled exception is noted against the request event at
  Django's own catch-all, so the request shows the failure beside
  the 500 it answered; the failing view's own event carries the
  exception directly. `Http404`, `PermissionDenied` and
  `SuspiciousOperation` are control flow that carry a status
  (404/403/400) and are never noted.

- Every ORM query, and raw SQL through a Django cursor, records as a
  `database` event at the `CursorWrapper` seam every backend funnels
  through (`DEBUG = True`'s debug cursor included), carrying
  `system` (the connection's vendor: `sqlite`, `postgresql`,
  `mysql`, `oracle`), `operation` (the SQL's leading keyword),
  `database` and, for a server database, `host` and `port`. Commit
  and rollback record the same way at the connection, showing the
  real transaction boundaries `atomic()` creates; under plain
  autocommit most statements never hit them. Bound parameters are
  never recorded; the SQL text (with placeholders, not values) only
  when the `statement` setting is on.

- Every DTL render records as a `template`-categorised event beneath
  the view that asked for it, annotated with the template's name,
  the render context masked wholesale and the output reduced to its
  size. Included and extended templates nest beneath the render that
  pulled them in.

## Composition

- Under an instrumented server (the `uvicorn` target, or any
  recording middleware a server interposed), a request still records
  as one tree: the outer middleware records and marks the scope, the
  handler's own passes through, and the route annotation lands on
  the one boundary.

- With the `sqlite3` target also applied and `leaf` on (the
  default), each Django query is a terminal node and the driver's
  own events beneath it are folded in, so a query records once; with
  `leaf` off they nest beneath it instead. A future per-backend
  driver package composes the same way.

- Django's Jinja2 template backend delegates to real Jinja2, so
  those renders are the `jinja2` target's to record; this
  instrumentation covers only DTL templates and the two never double
  up.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `ignore_paths` | `[]` | Request paths not to record, as path globs (`'/health'`, `'/static/*'`). An ignored request records nothing at all, its view, queries and template renders included. |
| `redact` | `[]` | Query string parameters to mask by name, on top of the built-in sensitive set (passwords, tokens, keys and session ids are always masked). The parameter still reaches the application; only the recording is masked. |
| `queries` | `true` | Record ORM statements and transaction ends as database events. |
| `statement` | `false` | Record the SQL text on each query event, as compiled with placeholders; bound parameters are never recorded regardless. |
| `leaf` | `true` | Record each query as a terminal node, folding an instrumented driver beneath it. |
| `templates` | `true` | Observe DTL template rendering beneath the view that asked for it. |

```toml
[[instrument]]
name = "django"
ignore_paths = ["/health"]
statement = true
```

## How it patches

For the implementation detail see the module docstrings of
[handlers.py](handlers.py), [dispatch.py](dispatch.py),
[resolvers.py](resolvers.py), [exceptions.py](exceptions.py),
[db.py](db.py) and [templates.py](templates.py).
