# wrapture-instrumentation

Instrumentation for common Python packages, applied through
[wrapture](https://github.com/GrahamDumpleton/wrapture).

wrapture attaches bindings to arbitrary Python call sites without
modifying the code being observed, and its config layer can switch on
packaged instrumentation for a third-party package by name. This
project is the collection of that packaged instrumentation: one
`wrapture.Instrumentation` class per target package, each registered
under the bare target name, so that tracing a framework is one config
entry and no code.

> **Status: alpha, ahead of 1.0.0.** Developed against wrapture's
> alpha series, with pre-releases published to
> [PyPI](https://pypi.org/project/wrapture-instrumentation/), and
> until 1.0.0 is final a plain `pip install wrapture-instrumentation`
> picks up the latest pre-release automatically, so there is no need
> to pin a specific version. The table below lists what is covered,
> from web frameworks and the servers that carry them to HTTP
> clients, databases and template engines.

## Installation

```console
$ pip install wrapture-instrumentation
```

Installing it brings wrapture and nothing else. No target package is
a dependency: the instrumentation for a package you do not have is
inert, and wrapture checks the installed version of each target
against the range the instrumentation supports at apply time.

## Using it

An `[[instrument]]` entry in `wrapture.toml` names a target:

```toml
[[instrument]]
name = "flask"

[[sink]]
type = "printer"
```

and the runner applies it before the application starts, so the
patches are in place before the framework is imported:

```console
$ python -m wrapture -m myapp
```

The same config works through
[autowrapt](https://github.com/GrahamDumpleton/autowrapt) injection
(`AUTOWRAPT_BOOTSTRAP=wrapture python myapp.py`); through
[manual setup](https://wrapture.readthedocs.io/en/latest/manual-setup.html),
a few lines in the application's own startup applying the config
where wrapping the launch from outside is awkward (an embedded
interpreter, gunicorn and other multi-process managers); and, in a
test, through `wrapture.instrumentation("flask")` scoping the
instrumentation to a block. The
[ad-hoc tracing guide](https://wrapture.readthedocs.io/en/latest/ad-hoc-tracing.html)
covers the config file itself.

To see what is installed, what each instrumentation supports in the
current environment, and what settings it takes:

```console
$ python -m wrapture.tools instrumentation --verbose
```

and to generate the `[[instrument]]` entries to paste into a config,
every one disabled and every setting commented out at its default:

```console
$ python -m wrapture.tools instrumentation --toml
```

## Provided instrumentation

| Target | Supported versions | Records | Settings |
| ------ | ------------------ | ------- | -------- |
| [`aiohttp.client`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/external/aiohttp_client/README.md) | aiohttp 3.10+ (3.x) | Every outbound request through a `ClientSession` (the verb helpers, `session.request`, a streamed `async with`) as one external leaf on `_request` carrying method, URL, host, port, path, query and status (an error status is a status, not an exception); a followed redirect one event resolved inside it; the trace identity propagated hop by hop; the query and any URL credentials masked, the body never recorded. | `leaf`, `propagate`, `redact` |
| [`aiohttp.web`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/server/aiohttp_web/README.md) | aiohttp 3.10+ (3.x) | Every request an aiohttp server handles as one `server`-categorised request boundary carrying method, path, scheme, peer and redacted query, annotated with the matched route pattern (a sub-application's prefix folded in, exported as `http.route`) and status (an `HTTPException` is its status, not a failure), joining the trace a `traceparent` header carries; every registered handler function observed as its route is built and recorded beneath the boundary, labelled by the route's name. | `ignore_paths`, `join`, `redact` |
| [`django`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/framework/django/README.md) | Django 4.2+ (below 7.0) | Every request as one tree through the recording WSGI or ASGI middleware on the handler's own `__call__`, annotated with the matched route pattern and view name (the pattern exported as `http.route`); every view observed at URL resolution and labelled by its URL name, function, class-based and async views alike; ORM queries and transaction ends as database leaves at the cursor seam carrying system, operation and database, bound parameters never recorded and the SQL text only behind a setting; DTL renders as template events beneath their views, contexts never captured; unhandled failures noted on the request beside the 500 (an `Http404` is its status, not a failure). | `ignore_paths`, `redact`, `queries`, `statement`, `leaf`, `templates` |
| [`fastapi`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/framework/fastapi/README.md) | fastapi 0.110+ (below 1.0) | Every request as one tree through the recording ASGI middleware on the application's own `__call__`, annotated with the matched route pattern (router prefixes folded in) and name, the pattern exported as `http.route`; every endpoint function observed as its `APIRoute` is built, labelled by the route's name, dependency injection and response models undisturbed; validation failures record as their 422, unhandled failures on the request event beside the 500. | `ignore_paths`, `redact` |
| [`flask`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/framework/flask/README.md) | Flask 3.x | Every request as one tree, annotated with route and endpoint; every view observed and labelled by endpoint; template renders beneath their views; handled and unhandled failures noted on the request. | `ignore_paths`, `redact`, `lifecycle`, `handled_errors`, `templates` |
| [`grpc`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/rpc/grpc/README.md) | grpcio 1.76+ (1.x) | Every RPC a channel makes, all four call shapes, as one external leaf through an injected client interceptor, carrying the rpc system, service and method, host, port and status code (an error code is a status, not an exception; a streamed response records the call, its consumption deliberately not tracked); every RPC a server handles as one `server` boundary through an injected server interceptor spanning the handler's run (a streaming handler's whole body), joining the trace the metadata carries; an abort is its code with the boundary clean, an escaped exception the failure it is; payloads and metadata never recorded. | `client`, `server`, `propagate`, `join` |
| [`http.client`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/external/http_client/README.md) | Python 3.12+ (standard library) | The wire phases of each exchange (connect where the socket really opens, the request line with its query masked, headers and body out by size, the response wait with its status) as plain events. A debugging aid: beneath an instrumented higher-level client nothing records until that client is switched to `leaf = false`. | `redact` |
| [`httpx`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/external/httpx/README.md) | httpx 0.27+ (below 1.0) | Every request through the module-level helpers, a `Client` or an `AsyncClient`, sync and async alike, as one external leaf on `send` carrying method, URL, host, port, path, query and status (an error status is a status, not an exception); a followed redirect one event resolved inside it; the trace identity propagated hop by hop; the query and any URL credentials masked, the body never recorded. | `leaf`, `propagate`, `redact` |
| [`jinja2`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/template/jinja2/README.md) | Jinja2 3.x | Every render traced in all its forms (sync, async, streamed), annotated with the template name; the loading and compile pipeline beneath it; context and output kept out of capture. | `loading` |
| [`requests`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/external/requests/README.md) | requests 2.31+ (2.x) | Every request through the module-level helpers, `Session.request` or `Session.send` itself as one external leaf carrying method, URL, host, port, path, query and status (an error status is a status, not an exception); a redirect one leaf named by the URL asked for; the trace identity propagated hop by hop; the query and any URL credentials masked, the body never recorded. | `leaf`, `propagate`, `redact` |
| [`sqlalchemy`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/database/sqlalchemy/README.md) | SQLAlchemy 1.4+ (below 3.0) | Every statement an engine executes, Core and ORM, sync and async alike, as one database leaf at the dialect seam every driver sits behind, carrying the system, the SQL's leading keyword as the operation and the database; the connections the pool really opens and the transaction boundaries recorded the same way, the pool's own reset rollbacks excluded; bound parameters and credentials never recorded, the SQL text only behind a setting. | `leaf`, `statement` |
| [`sqlite3`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/database/sqlite3/README.md) | Python 3.12+ (standard library) | Every query and transaction boundary as one database leaf, through recording proxies around the connections `connect` hands out, carrying the system and the SQL's leading keyword as the operation; bound parameters never recorded, the SQL text only behind a setting. | `statement` |
| [`starlette`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/framework/starlette/README.md) | starlette 0.47+ (below 2.0) | Every request as one tree through the recording ASGI middleware on the application's own `__call__`, annotated with the matched route pattern and name (the pattern is what the OpenTelemetry export names the span by, as `http.route`); every endpoint function observed as its route is built, labelled by the route's name, sync and async alike; unhandled failures on the request event beside the 500. | `ignore_paths`, `redact` |
| [`urllib.request`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/external/urllib_request/README.md) | Python 3.12+ (standard library) | Every request through `urllib.request` as one external leaf carrying method, URL, host, port, path, query and status; the trace identity propagated in its headers; the query recorded with secrets masked, the body and response kept out of capture. | `leaf`, `propagate`, `redact` |
| [`urllib3`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/external/urllib3/README.md) | urllib3 1.26+ (below 3.0) | Every request through a pool manager, a connection pool or the module-level helper as one external leaf on `urlopen` (both doors sharing one depth count, so a redirect, a retry and the manager's delegation to a pool fold into it) carrying method, URL, host, port, path, query and status (an error status is a status, not an exception); the trace identity propagated in the headers; the query and any URL credentials masked, the body never recorded. Beneath the requests leaf it stays silent; standalone it records its own. | `leaf`, `propagate`, `redact` |
| [`uvicorn`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/server/uvicorn/README.md) | uvicorn 0.30+ (below 1.0) | Every application the server loads wrapped in the recording ASGI middleware at uvicorn's own seam, inside its proxy-headers middleware: one request tree per request, named by the application, with method, path, redacted query, status and streaming shape, joining the trace a `traceparent` header carries; an application's own recording middleware still records one boundary per request. | `ignore_paths`, `redact` |
| [`werkzeug.serving`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/server/werkzeug_serving/README.md) | werkzeug 3.x | Every application handed to werkzeug's development server (Flask's `app.run()` included) wrapped in the recording WSGI middleware as the server is built: one request tree per request with method, path, redacted query and status, joining the trace a `traceparent` header carries; a framework's own recording middleware still records one boundary per request. | `ignore_paths`, `redact` |
| [`wsgiref.simple_server`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/server/wsgiref_simple_server/README.md) | Python 3.12+ (standard library) | Every application the server is handed wrapped in the recording WSGI middleware at the server's own seam: one request tree per request with method, path, redacted query and status, joining the trace a `traceparent` header carries; an application already recording (a framework's own middleware) still records one boundary per request. | `ignore_paths`, `redact` |
| [`xmlrpc.client`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/external/xmlrpc_client/README.md) | Python 3.12+ (standard library) | Every remote call through a `ServerProxy` as one external leaf carrying the RPC system and method name, URL, host, port, path and status (a `Fault` is a 200, a `ProtocolError` its code); the trace identity propagated in its headers; credentials, arguments, results and bodies kept out of capture. | `leaf`, `propagate` |
| [`xmlrpc.server`](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/src/wrapture_instrumentation/server/xmlrpc_server/README.md) | Python 3.12+ (standard library) | Every XML-RPC POST a `SimpleXMLRPCServer` handles as one `server`-categorised request boundary carrying method, path, client and status, joining the distributed trace an arriving `traceparent` header carries; each dispatched procedure beneath it with the method name as `operation`, multicall sub-calls nested; params and results reduced to counts and types. | `join` |

The entry point name is the config's `name`; the table summarizes
each instrumentation, and the linked per-target README is its full
user documentation: what records, what the events carry, the
settings, and what is deliberately not traced. Settings, further
choke points and wider version ranges are being added target by
target.

This package deliberately covers only the standard library and
third-party packages that can be exercised in-process, with no
separate backend product or service needed to test against.
Instrumentation for targets that do need one (a real PostgreSQL,
MySQL or Redis to speak to, and their driver packages) will be
provided as separate self-contained packages, one per
product/service, each carrying its own test arrangements and release
cadence. No such packages exist yet; they are coming.

## Adding a target

Each target lives under `src/wrapture_instrumentation/` in a role
directory named for its category, as `<category>/<target>`:
`framework/flask`, `external/requests`, `database/sqlite3`. The
target's own name is its module path with dots as underscores
(`external/urllib_request` for `urllib.request`,
`server/xmlrpc_server` for `xmlrpc.server`), and the category says
what kind of thing the target is and, with it, which part of
wrapture the instrumentation mostly uses:

- `framework/`: web frameworks, and their extensions as compound
  names (`framework/flask_restful`).

- `external/`: outbound HTTP and RPC clients and service SDKs.

- `database/`: DB-API drivers and SQL toolkits.

- `datastore/`: other stores and caches.

- `task/`: task queues. `messaging/`: brokers and their clients.

- `rpc/`: RPC frameworks whose one package covers both the client
  and the server side.

- `server/`: servers handling inbound requests, WSGI and ASGI
  servers included.

- `template/`: template engines.

A new category is added when a target fits none of these. The role
directories are the collection form of the layout: a package
instrumenting a single target skips them and uses the flat
`<category>_<target>` name (`external_requests`), the same words
joined by an underscore instead of a directory. Either way the
layout is internal; the entry point name, and so the name a config
uses, is always the bare target.

The subpackage's `__init__.py` holds one `wrapture.Instrumentation`
subclass, with one `@wrapture.instrumentation_hook` method per
trigger module, and imports only wrapture; everything that touches
the target lives in sibling submodules named for what they patch
(`app.py` for `flask.app`), themselves importing only wrapture at top
level.
The class is registered in `pyproject.toml` under
`[project.entry-points."wrapture.instrumentation"]`, and gets its own
test suite under `tests/<category>/<target>/`, mirroring the source layout. Each subpackage also
carries a `README.md`, its user documentation, rendered by GitHub
when browsing the directory and linked from the table above; the
module docstrings stay the implementation commentary. The
[instrumentation packages](https://wrapture.readthedocs.io/en/latest/instrumentation-packages.html)
page of the wrapture documentation is the full contract; TESTING.md
here covers the tests.

## License

BSD 2-Clause. See
[LICENSE](https://github.com/GrahamDumpleton/wrapture-instrumentation/blob/develop/LICENSE).
