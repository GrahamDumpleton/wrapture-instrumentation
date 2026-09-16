# Changes

## Version 1.0.0b3

- A disabled aspect binds nothing. `enabled = false` under an aspect,
  or a bare `connections = false` on the entry, now leaves that
  aspect's call sites untouched in every package, as the READMEs
  said; in 1.0.0b2 the database packages and every request boundary
  and outbound request aspect ignored the switch. sqlite3's connect
  factories still wrap the connection they return with `connections`
  off, since the execute bindings live on that wrapper, but record
  nothing.

## Version 1.0.0b2

- Every instrumentation declares its aspects, the groups of call sites it
  binds, as `wrapture.Aspect` values in its settings: a request boundary,
  the views or handlers beneath it, the statements and connections of a
  database, the renders and loading of a template engine, the client
  and server sides of gRPC. An aspect is addressed in the config as a
  sub-table of the entry (`[instrument.views]`) and takes the recording
  keys an `[[observe]]` entry does, so `capture_result = "types"` or
  `redact = ["token"]` under an aspect means the same everywhere; a bare
  boolean under an aspect's name is its switch, and the primary aspect's
  keys may be written flat on the entry. Each README lists its aspects.

- `redact` and `leaf` are no longer settings of the packages' own:
  they are recording keys under the aspect they apply to, which for the
  framework, server and client packages is the primary `requests` aspect,
  so existing entries writing them flat read the same. The toggles
  (`lifecycle`, `templates`, `queries`, `loading`, `client`, `server`)
  are aspects, and `statement`, `propagate` and `join` live under theirs.

- Handler results are held back by default: the views of flask, django,
  fastapi and starlette, aiohttp.web's handlers, flask's error handlers
  and xmlrpc.server's methods record their result as its shape, a dict
  or list as its size rather than its contents, since that value is the
  response body. The fastapi, starlette and aiohttp.web aspects record
  their arguments as types. A `[instrument.views]` table restores any
  other level.

- Requires wrapture 1.0.0b4, for `Aspect` and the `shape` capture level.

## Version 1.0.0b1

The first beta. Everything is new in this version, so rather than
listing changes, see the [README](README.md) for what the package
provides: the table of covered targets there links to each target's
own notes describing what it records and its settings.
