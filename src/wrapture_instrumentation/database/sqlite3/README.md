# sqlite3 instrumentation

Query and transaction tracing for
[sqlite3](https://docs.python.org/3/library/sqlite3.html), the
standard library's SQLite interface. Entry point name `sqlite3`, the
module it patches; the supported range is a Python version range,
`>=3.12`; fully removable.

## Enabling it

An `[[instrument]]` entry in `wrapture.toml` (with at least one sink
to hear the events):

```toml
[[instrument]]
name = "sqlite3"

[[sink]]
type = "printer"
```

run under wrapture's runner (`python -m wrapture -m myapp`), or in a
test through the context manager:

```python
with wrapture.instrumentation("sqlite3"):
    ...
```

## What you see

One `database` leaf per operation: the connection being opened, each
query however it was issued (a cursor's `execute`, `executemany` or
`executescript`, or the connection's shortcut forms), and each
transaction boundary (`commit`, `rollback`, and the connection's
commit-or-rollback context manager, whose exit records which of the
two it performed):

```
sqlite3:connect('<str>')  -> '<Connection>'
sqlite3:Cursor.execute(sql='<38 chars>', parameters='<1 values>')
sqlite3:Connection.commit()
```

The connect event's data says which database was opened (`database`,
the path or `:memory:`), alongside the contract keys below.

- `sqlite3.Connection` and `sqlite3.Cursor` are C types no patch can
  touch, so the instrumentation binds the `connect` factories (both
  the `sqlite3` and `sqlite3.dbapi2` spellings) and wraps each
  connection in a recording proxy, cursors included. The application
  never sees the difference: attributes, row factories, iteration
  and chaining all pass through, and every event is labelled with
  the sqlite3 name it stands for.

- Every event carries the database contract keys `system`
  (`sqlite`) and `operation` (the SQL's leading keyword, or
  `CONNECT`, `COMMIT`, `ROLLBACK`), which wrapture's OpenTelemetry
  export maps to `db.system.name` and `db.operation.name`.

- The capture policy is deliberate about sensitive data: bound
  parameters are never recorded, under any setting; the SQL text
  reduces to its length unless the `statement` setting is on; and
  there is no obfuscation at this layer, because rewriting SQL to
  strip literals is a losing game outside a real lexer. Record the
  text where queries are parameterized, leave it off where they are
  not.

- Fetching is not recorded: a query event closes when its execute
  returns, so time spent iterating rows afterwards is not attributed
  to the database.

## Aspects

The instrumentation binds these aspects, each a group of call sites
with a switch, recording defaults and settings of its own:

| Aspect | Wraps | Records by default |
| ---- | ----- | ------------------ |
| `statements` (primary) | `execute`, `executemany` and `executescript` on cursors and as the connection's shortcut forms, as database events | `leaf = true`; SQL as its length and parameters as a count, an explicit capture key under the aspect replacing that |
| `connections` | `connect`, `commit`, `rollback` and the commit-or-rollback context manager exit, as database events | `leaf = true`; SQL as its length and parameters as a count, an explicit capture key under the aspect replacing that |

An aspect is addressed as a sub-table of the entry,
`[instrument.connections]`, and takes the recording keys an
`[[observe]]` entry does (`capture`, `capture_args`, `capture_result`,
`redact`, `redact_result`, `redact_marker`, `leaf` and `stack`) beside
the settings listed below, so `capture_result = "types"` or
`redact = ["token"]` under an aspect means exactly what it means on an
observe entry. `enabled = false` under an aspect switches it off, and a
bare `connections = false` on the entry means the same. The primary
aspect's keys may be written flat on the entry. The [aspects
section](https://wrapture.readthedocs.io/en/latest/instrumentation-packages.html#aspects)
of the wrapture documentation has the whole scheme.

## Settings

| Setting | Aspect | Default | Controls |
| ------- | ---- | ------- | -------- |
| `statement` | `statements` | `false` | Whether each query event records the SQL text as written, as `statement`. Off by default because sqlite3 code commonly interpolates literals into its SQL; turn it on when your queries are parameterized, the text then carrying placeholders rather than data. Bound parameters are never recorded either way. |

```toml
[[instrument]]
name = "sqlite3"
statement = true
```
## How it patches

For the implementation detail see the module docstring of
[dbapi2.py](dbapi2.py).
