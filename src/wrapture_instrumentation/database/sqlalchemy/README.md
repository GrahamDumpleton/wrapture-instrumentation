# SQLAlchemy instrumentation

Query and transaction tracing for
[SQLAlchemy](https://www.sqlalchemy.org/) engines. Entry point name
`sqlalchemy`, the package it patches; supports SQLAlchemy 1.4 and
later, below 3.0; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "sqlalchemy"

[[sink]]
type = "printer"
```

run under wrapture's runner or through autowrapt injection, so the
patches are in place before the application imports SQLAlchemy; in a
test, the context manager `wrapture.instrumentation("sqlalchemy")`
scopes it to a block.

## What you see

One `database` leaf per statement, however it was issued, plus the
connections the pool really opens and each transaction boundary:

```
sqlalchemy.engine.default:DefaultDialect.connect()  -> '<Connection>'
sqlalchemy.engine.default:DefaultDialect.do_execute(cursor='<Cursor>', statement='<24 chars>', parameters='<1 values>', context='<SQLiteExecutionContext>')
sqlalchemy.engine.base:Connection._commit_impl()
```

- The statement bindings sit on the dialect seam every driver hides
  behind: since SQLAlchemy 1.4 every execution path, Core and ORM,
  sync and async engine alike, funnels into `do_execute`,
  `do_executemany` and `do_execute_no_params` on the dialect. One
  set of bindings on `DefaultDialect` therefore covers every
  database SQLAlchemy talks to, and the driver dialects that
  override `do_executemany` with a fast path of their own (psycopg2,
  mysqldb, cx_oracle, pyodbc) are bound in their own right as their
  modules load.

- Every event carries `system` (the dialect's name: `sqlite`,
  `postgresql`) and `operation` (the SQL's leading keyword, or
  `CONNECT`, `COMMIT`, `ROLLBACK`), the database category's contract
  keys, which wrapture's OpenTelemetry export maps to
  `db.system.name` and `db.operation.name`. Statement events add the
  `database` from the engine's URL and, for a server database, its
  `host` and `port`.

- The capture policy is deliberate about sensitive data: bound
  parameters are never recorded, under any setting; the SQL text
  reduces to its length unless the `statement` setting is on; and
  the connect event captures none of its arguments, which are the
  driver's credentials. SQL the expression language compiles carries
  placeholders rather than data, so recording it is safe; a `text()`
  fragment passes through as the application wrote it, literals
  included, which is why the setting is off by default.

- Transaction boundaries are recorded where SQLAlchemy really ends a
  transaction: an explicit `commit()` or `rollback()`, an
  `engine.begin()` block closing, an ORM session's commit, and the
  rollback that ends an autobegun transaction when a connection
  closes without committing. The pool's own reset-on-return rollback
  happens below this seam and does not record, so pooled checkins do
  not spray rollback events through the timeline.

- A failing statement records the driver-level exception the seam
  sees (`sqlite3.OperationalError`, not the `DBAPIError` wrapper
  SQLAlchemy raises to the application above it). Fetching is not
  recorded: a statement event closes when its execute returns, so
  time spent iterating rows afterwards is not attributed to the
  database.

## With a driver instrumentation

An instrumented driver beneath an instrumented SQLAlchemy composes
through the `leaf` setting. With the default `leaf = true` each
statement is one event and the driver's own events stay out of the
tree; with `leaf = false` the driver's events nest beneath each
statement, `sqlite3:Cursor.execute` under `do_execute`, the driver's
`connect` under the dialect's. Raw driver use elsewhere in the
application records at the top level either way. A little of
SQLAlchemy's own housekeeping also shows up beside the tree
regardless, because it runs straight against the driver outside the
recorded seams: the dialect's connection setup (an isolation-level
PRAGMA on SQLite) and the pool's reset-on-return rollback, both of
which an instrumented driver records even though this
instrumentation does not.

## Settings

| Setting | Default | Controls |
| ------- | ------- | -------- |
| `leaf` | `true` | Record each statement as a terminal node, so anything recorded beneath it (an instrumented driver such as sqlite3) stays out of the tree. Off exposes the driver's own events beneath each statement. |
| `statement` | `false` | Whether each statement event records the SQL text as compiled, as `statement`. Compiled SQL carries placeholders rather than data, but `text()` fragments pass through as written; turn it on when those are parameterized too. Bound parameters are never recorded either way. |

```toml
[[instrument]]
name = "sqlalchemy"
statement = true
```

## How it patches

For the implementation detail see the module docstrings of
[engine_default.py](engine_default.py) (the statement and connect
seams), [engine_base.py](engine_base.py) (the transaction
boundaries) and [dialects.py](dialects.py) (the driver dialects that
override `do_executemany`).
