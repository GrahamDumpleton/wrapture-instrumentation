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
