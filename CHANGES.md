# Changes

## Version 1.0.0

In development.

- Package layout: the targets are grouped in role directories named
  for their categories (`framework/flask`, `external/urllib_request`,
  `server/xmlrpc_server`), the collection form of the naming
  guidance, a single-target package keeping the flat
  `<category>_<target>` name. Entry point names are unchanged, so
  nothing a config says is affected.

- urllib (`urllib.request`, standard library): every request made
  through `urllib.request`, by `urlopen`, `urlretrieve`, a custom opener or
  another standard library module, records as one external leaf on
  `OpenerDirector.open`, carrying the external category's contract
  keys (method, URL without its query string, host, port, path, the
  query with secrets masked, and the status whether returned or
  raised as an `HTTPError`); a redirect is one event named by the
  URL asked for. The trace identity from `wrapture.trace_headers()`
  is added to every request's headers, hop by hop, leaving a header
  the application set alone. The query is recorded through
  `wrapture.capture_query()`, so the built-in sensitive names are
  always masked, the body reduces to its size and the response to
  its type. Three settings: `leaf` (off to see the nested opens and
  anything instrumented beneath) and `propagate`, both on by
  default, and `redact` (query parameters masked by name on top of
  the built-in set). Supports Python 3.12 and later, the standard
  library's version being the interpreter's.

- http.client (`http.client`, standard library): the wire layer
  beneath urllib, urllib3 and xmlrpc.client, recorded phase by phase
  as plain events: `connect` nested inside the phase that first
  touched the socket, `putrequest` with the query string masked,
  `endheaders` with the body by size, `getresponse` annotated with
  the status. A debugging aid rather than default instrumentation:
  beneath a higher-level client's leaf event nothing records, so it
  pairs with switching that client to `leaf = false`; standalone
  http.client use records with no switch. One setting: `redact`
  (query parameters masked by name on top of the built-in set). No
  trace propagation at this layer; that belongs to the client above.
  Supports Python 3.12 and later.

- xmlrpc.client (`xmlrpc.client`, standard library): every remote
  call through a `ServerProxy` records as one external leaf on the
  proxy's private `ServerProxy.__request` method, the one door they
  all pass through, carrying the external
  contract keys (method `POST`, url, host, port, path, and status:
  200 for any parsed response, a `Fault` included, or the code a
  `ProtocolError` carries) plus the RPC pair `system` (always
  `xmlrpc`) and the method name as `operation`, which the
  OpenTelemetry export maps to `rpc.system` and `rpc.method`, naming
  the span by the operation.
  The trace identity from `wrapture.trace_headers()` is added to
  every request's headers, leaving one the application supplied
  alone. Hosts and URLs are stripped of basic-auth userinfo,
  arguments reduce to a count, results to a type and bodies to a
  size. Two settings, both on by default: `leaf` (off to see the
  transport event beneath each call, and the `http.client` wire
  phases under that when enabled) and `propagate`. Supports Python
  3.12 and later.

- xmlrpc.server (`xmlrpc.server`, standard library): every XML-RPC
  POST a `SimpleXMLRPCServer` handles records as one request
  boundary, a block labelled `xmlrpc.server` and categorised
  `server` opened around the handler's `do_POST`, carrying `system`
  (`xmlrpc`), the request method, path and client address and the
  response status (200 with a marshalled response, a `Fault`
  included; 404 for a path outside the handler's `rpc_paths`), and
  joining the distributed trace an arriving `traceparent` header
  carries, so both sides of a call between instrumented processes
  share one trace id; the OpenTelemetry export reads the category as
  a SERVER span named access-log style. Every dispatched
  procedure records beneath it on
  `SimpleXMLRPCDispatcher._dispatch`, annotated with the method name
  as `operation`, a `system.multicall` nesting its sub-calls inside
  the batch's own dispatch. Params reduce to a count and results to
  a type; the headers only ever feed the join and are never
  recorded. One setting: `join`, on by default. Supports Python 3.12
  and later.

- wsgiref (`wsgiref.simple_server`, standard library): every
  application the server is handed, through `make_server`,
  `set_app` or a subclass, is wrapped in wrapture's recording WSGI
  middleware at the server's own seam, `WSGIServer.get_app`, without
  the application changing at all: one request tree per request,
  named by the application's own module and qualname, carrying
  method, path, the query with secrets masked, scheme, peer and the
  status line, and joining the distributed trace an arriving
  `traceparent` header carries. One boundary per request however
  many layers record: an application already carrying its own
  recording middleware (a Flask application the flask
  instrumentation wrapped) passes the inner one through, and
  framework annotations land on the one event. Removal restores
  `get_app`, un-wrapping servers already running. Two settings:
  `ignore_paths` (path globs whose requests record nothing at all)
  and `redact` (query parameters masked by name on top of the
  built-in set). Supports Python 3.12 and later.

- werkzeug (`werkzeug.serving`, werkzeug 3.x): every application
  handed to werkzeug's development server, through `run_simple`,
  `make_server`, a server class directly or Flask's `app.run()`, is
  wrapped in wrapture's recording WSGI middleware as the server is
  built (`BaseWSGIServer.__init__`, the one place the application is
  handed over, werkzeug having no accessor on the request path):
  one request tree per request, named by the application's own
  module and qualname, carrying method, path, the query with
  secrets masked, scheme, peer and the status line, and joining the
  distributed trace an arriving `traceparent` header carries. One
  boundary per request however many layers record, so it composes
  with the flask instrumentation. Removal stops the wrapping for
  servers built afterwards; a server built while instrumented keeps
  its wrapper for its own lifetime. Two settings: `ignore_paths`
  and `redact`, as on the wsgiref target. Supports werkzeug 3.x.

- uvicorn (`uvicorn`, uvicorn 0.30+): every application the server
  loads, through `uvicorn.run()`, a `Server` built by hand or
  gunicorn's `UvicornWorker`, is wrapped in wrapture's recording
  ASGI middleware at the server's own seam, `Config.load`, without
  the application changing at all: one request tree per request,
  named by the application's own module and qualname, carrying
  method, path, the query with secrets masked, scheme, peer, the
  status line and the response's streaming shape, and joining the
  distributed trace an arriving `traceparent` header carries. The
  wrap lands inside uvicorn's own middlewares, around the
  application itself, so the event is named by the application and
  the recorded scope is the one the application sees (with proxy
  headers on, uvicorn's default, the client and scheme are the
  forwarded values). One boundary per request however many layers
  record; websocket and lifespan traffic passes through untouched.
  Removal restores `Config.load` for configs loaded afterwards; a
  server already running keeps its wrapper for its own lifetime,
  the werkzeug trade-off at the same kind of seam. Two settings:
  `ignore_paths` and `redact`, as on the WSGI server targets.
  Supports uvicorn 0.30 and later, below 1.0.

- sqlite3 (`sqlite3`, standard library): every query and transaction
  boundary records as one database leaf. The connection and cursor
  types are C types no patch can touch, so the `connect` factories
  (both the `sqlite3` and `sqlite3.dbapi2` spellings) are bound and
  each connection comes back wrapped in a recording proxy, cursors
  included, every event labelled with the sqlite3 name it stands
  for. Recorded: the connect, the execute family on cursors and the
  connection's shortcut forms, `commit`, `rollback`, and the
  connection's commit-or-rollback context manager, its exit saying
  which it performed. Every event carries `system` (`sqlite`) and
  `operation` (the SQL's leading keyword, or CONNECT, COMMIT,
  ROLLBACK), the database contract the OpenTelemetry export maps to
  `db.*` attributes. Bound parameters are never recorded; the SQL
  text is recorded only behind the `statement` setting, off by
  default, and reduces to its length otherwise. Fetching is not
  recorded. Supports Python 3.12 and later.

- requests (`requests`, requests 2.31+): every request made through
  the module-level helpers, `Session.request` or a `Session.send`
  the application calls itself records as one external leaf on
  `Session.send`, carrying the external category's contract keys
  (method, URL without its query string or userinfo, host, port,
  path, the query with secrets masked, and the status of whatever
  came back: requests answers a 4xx or 5xx with a response, so an
  error status is a status, and an exception is recorded only when
  the exchange really failed). A redirect is one event named by the
  URL asked for, and unless the caller streams, the event covers the
  body download too. The trace identity from
  `wrapture.trace_headers()` is added to every request's headers, a
  redirect hop's copied headers carrying it onward and a header the
  application set itself left alone. The request body is never
  recorded and the response reduces to its type. Three settings, as
  on the urllib target: `leaf`, `propagate` and `redact`. Supports
  requests 2.31 and later in the 2.x line.

- FastAPI (`fastapi`, fastapi 0.110+): every request records as one
  tree through wrapture's recording ASGI middleware, installed by
  decorating `FastAPI.__call__`, the starlette target's seam one
  class down, with a per-instance cache of this target's own so the
  two boundaries stack rather than loop when both are applied, the
  outer one recording. `APIRoute.handle` annotates the request event
  with the route's path pattern (an including router's prefix folded
  in) and name, needed in its own right because `APIRoute` builds
  and can dispatch without touching the `Route` seams the starlette
  target patches; `APIRoute.__init__` substitutes observed endpoint
  functions labelled by the route's name, with dependency
  injection, response models and OpenAPI generation reading the
  proxy as the function it wraps, and `include_router()` re-handing
  an observed endpoint back without stacking a second observation.
  A validation failure records as its 422 and an unhandled
  exception lands on the request event beside the 500. Two
  settings: `ignore_paths` and `redact`, as on the starlette
  target. Supports fastapi 0.110 and later, below 1.0.

- Starlette (`starlette`, starlette 0.47+): every request records
  as one tree through wrapture's recording ASGI middleware,
  installed by decorating `Starlette.__call__`, the application as a
  server calls it, one cached wrapper per application instance. Once
  routing matches, the request event is annotated with the route's
  path pattern and name (`Route.handle` being the moment both are
  known), the pattern being what the OpenTelemetry export maps to
  `http.route`; a 404 gains no route keys, and a route inside a
  `Mount` annotates the pattern it owns. Every endpoint function is
  observed as its `Route` is built, labelled by the route's name,
  sync and async endpoints alike; class-based endpoints, mounted
  ASGI applications and `functools.partial` endpoints pass through
  untouched. Unhandled exceptions need no extra machinery: starlette
  answers 500 and re-raises, so the request event carries status and
  exception together, while an `HTTPException` records as nothing
  but its status. One boundary per request under an instrumented
  server, the route annotation landing on it. Two settings:
  `ignore_paths` and `redact`, as on the server targets. Supports
  starlette 0.47 and later, below 2.0. The suites drive ASGI
  applications in process through a new tests/asgi.py driver, the
  ASGI counterpart of the WSGI one.

- httpx (`httpx`, httpx 0.27+): every request made through the
  module-level helpers, a `Client` or an `AsyncClient` records as
  one external leaf, on `Client.send` or its mirror
  `AsyncClient.send` (the async event recording around the await),
  carrying the same external contract keys as the requests target,
  with the same statuses-not-exceptions rule and the same capture
  policy (query masked, URL userinfo stripped, body never recorded,
  response by type). httpx follows redirects only when asked:
  unasked, the event carries the 3xx the caller saw; followed, the
  hops resolve in a loop inside the one send, so a redirect is one
  event whatever the leaf setting says, and the copied headers carry
  the propagated trace identity on every hop. Unless the caller
  streams, the event covers the body download too. Three settings,
  as on the requests target: `leaf`, `propagate` and `redact`.
  Supports httpx 0.27 and later, below 1.0.

- Jinja2 (`jinja2`, Jinja2 3.x): every render traced in all its
  forms, sync, streamed and async, each annotated with the
  template's own name; the loading pipeline
  (`Environment._load_template` on every get_template,
  `Environment.compile` inside a cold load) beneath it, behind a
  `loading` switch; every event named by its patched location as
  `module:qualname`; and the render context, output and template
  source kept out of capture or truncated.

- Flask (`flask`, Flask 3.x): every request records as one tree
  through the recording WSGI middleware installed at construction,
  annotated with the matched route pattern and endpoint (the route
  is what wrapture's OpenTelemetry export names the span by, as
  `http.route`); every view
  function is observed as it registers and labelled by its endpoint
  (blueprints and `MethodView`s included); lifecycle callbacks and
  error handlers are observed however they register; and failures
  are noted against the request, whether Flask answered 500 or a
  registered handler absorbed a real exception (an `HTTPException`
  is control flow and is not noted); and template rendering records
  beneath the view that asked for it, named by the spelling the call
  took (`flask:render_template` or
  `flask.templating:render_template`), capturing the template name
  while the render context and output stay out of capture. Three
  settings switch the optional layers, all on by default:
  `lifecycle`, `handled_errors` and `templates`; two more shape what
  a recorded request carries: `ignore_paths` (path globs whose
  requests record nothing at all, request and everything beneath it
  alike) and `redact`
  (query parameters masked by name on top of the built-in sensitive
  set).

- aiohttp client (`aiohttp.client`, aiohttp 3.10+): every outbound
  request made through a `ClientSession`, by the verb helpers,
  `session.request` or a streamed `async with`, records as one
  external leaf on `ClientSession._request`, the one coroutine they
  all pass through, carrying the external category's contract keys
  (method, URL without its query string or userinfo, host, port,
  path, the query with secrets masked, and the status whether
  returned or, for a real connection failure, absent). A followed
  redirect is one event named by the URL asked for: aiohttp resolves
  the hops in a loop inside the one call. The coroutine returns when
  the response headers are in, so the event covers the exchange to
  the response's start, not the body read afterwards. The trace
  identity from `wrapture.trace_headers()` is added to each request's
  headers, leaving a header the application set alone, and aiohttp
  carries them onto every redirect hop, so both sides of a call
  between instrumented processes share one trace id. The request body
  is never recorded and the call's arguments are not captured (the
  signature is wide, and the method and URL are already the event's
  contract keys); query supplied through `params=` rather than in the
  URL is not folded into the recording. Three settings, `leaf` and
  `propagate` on by default and `redact`, as on the other external
  clients. Supports aiohttp 3.10 and later, below 4.

- aiohttp (`aiohttp.web`, aiohttp 3.10+): every request an aiohttp
  server handles records as one `server`-categorised request
  boundary opened around the application's own dispatch
  (`Application._handle`, so a sub-application's requests land in
  the one boundary too), carrying method, path, scheme, peer and the
  query with secrets masked, annotated once dispatch has run with
  the matched route's canonical pattern and name (the pattern is
  what the OpenTelemetry export names the SERVER span by, and maps
  to `http.route`) and with the response's status: an
  `HTTPException` is control flow and records as the status it
  answers, while a real failure records as the exception, the
  protocol answering its 500 on its own. The boundary joins the
  distributed trace an arriving `traceparent` header carries, and
  every handler function is observed as its route registers, so each
  dispatch records the handler's call beneath the boundary, labelled
  by the route's name when one was given; class-based views register
  untouched and are named on the boundary only. Three settings:
  `ignore_paths` (path globs whose requests record nothing at all,
  the handler included, the filter evaluated by hand at the block
  boundary through `RequestFilter.matches()`), `join` (on by
  default) and `redact` (query parameters masked by name on top of
  the built-in set). Supports aiohttp 3.10 and later, below 4.
