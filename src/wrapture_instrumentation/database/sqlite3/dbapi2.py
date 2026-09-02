"""The sqlite3 patches: the connect factories bound, and the
connections they return wrapped in recording proxies.

sqlite3.Connection and sqlite3.Cursor are C extension types, so
there is no attribute on them a binding could patch: the one seam is
the module-level `connect` factory, on both `sqlite3` and
`sqlite3.dbapi2` (the same function, reached by either name). Each
is bound as a database leaf recording the connection being opened,
and its result comes back wrapped in the Connection proxy below.

The proxies derive from wrapt.BaseObjectProxy and override only the
operations worth recording; everything else, attributes, row
factories, iteration, passes straight through to the real object.
The overridden methods are themselves this module's classes' plain
Python methods, so they are bound with wrapture.binding() like any
target, each labelled with the sqlite3 name it notionally wraps
(`sqlite3:Cursor.execute`), the one thing its recorded path cannot
say. Removing the instrumentation removes those bindings and
restores the factories: connections already wrapped keep their
proxies, which then delegate without recording.

The recorded set is the acquisition, the execute family and the
transaction boundaries: `connect`; `execute`, `executemany` and
`executescript` on cursors and as the connection's shortcut forms
(the shortcuts must be recorded in their own right, since the C
implementation builds their cursor internally without consulting the
proxy); `commit` and `rollback`; and the connection's
commit-or-rollback context manager, whose exit records which of the
two it performed. Cursor creation and the fetch methods are not
recorded: fetching happens after the query event has closed, so time
spent iterating rows is not attributed to the database.

Every event carries `system` ("sqlite") and `operation` (the SQL's
leading keyword, or CONNECT, COMMIT, ROLLBACK), the database
category's contract keys. The SQL text itself is recorded only when
the `statement` setting is on, as written and never with its bound
parameters, which no setting captures; with the setting off the
text reduces to its length in the captured arguments. There is no
obfuscation at this layer: parameterized queries are safe to record
as written, and anything else is the reason the setting is off by
default.
"""

from __future__ import annotations

from typing import Any

import wrapt
import wrapture


class Cursor(wrapt.BaseObjectProxy[Any]):
    """A recording proxy around sqlite3.Cursor: the execute family is
    overridden for binding, everything else delegates."""

    def execute(self, sql: Any, parameters: Any = (), /) -> Any:
        outcome = self.__wrapped__.execute(sql, parameters)

        return self if outcome is self.__wrapped__ else outcome

    def executemany(self, sql: Any, parameters: Any, /) -> Any:
        outcome = self.__wrapped__.executemany(sql, parameters)

        return self if outcome is self.__wrapped__ else outcome

    def executescript(self, sql_script: Any, /) -> Any:
        outcome = self.__wrapped__.executescript(sql_script)

        return self if outcome is self.__wrapped__ else outcome

    # Iteration is looked up on the type, and BaseObjectProxy leaves
    # the special methods to the subclass: a sqlite3 cursor is its
    # own iterator, so both halves delegate. Fetching stays
    # unrecorded either way.

    def __iter__(self) -> Cursor:
        return self

    def __next__(self) -> Any:
        return self.__wrapped__.__next__()


class Connection(wrapt.BaseObjectProxy[Any]):
    """A recording proxy around sqlite3.Connection: cursors come back
    wrapped, the shortcut execute family and the transaction
    boundaries are overridden for binding, everything else
    delegates."""

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        return Cursor(self.__wrapped__.cursor(*args, **kwargs))

    def execute(self, sql: Any, parameters: Any = (), /) -> Any:
        return Cursor(self.__wrapped__.execute(sql, parameters))

    def executemany(self, sql: Any, parameters: Any, /) -> Any:
        return Cursor(self.__wrapped__.executemany(sql, parameters))

    def executescript(self, sql_script: Any, /) -> Any:
        return Cursor(self.__wrapped__.executescript(sql_script))

    def commit(self) -> None:
        self.__wrapped__.commit()

    def rollback(self) -> None:
        self.__wrapped__.rollback()

    # The context manager: the real __enter__ returns the raw
    # connection, so the proxy substitutes itself; __exit__ is where
    # sqlite3 commits or rolls back, bound below to record which.

    def __enter__(self) -> Connection:
        self.__wrapped__.__enter__()

        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return self.__wrapped__.__exit__(exc_type, exc_value, traceback)


def captured(name: str | None, value: Any) -> Any:
    """SQL text reduces to its length, parameters to a count or their
    type, a context manager exit's exception value and traceback to
    their types, and every unnamed value to its type: the query and
    its data never reach the record through argument capture."""

    if name in ("sql", "sql_script") and isinstance(value, str):
        return f"<{len(value)} chars>"

    if name == "parameters":
        if isinstance(value, (list, tuple)):
            return f"<{len(value)} values>"
        return f"<{type(value).__name__}>"

    # An exception's message is application data like any other; the
    # exit event's exception, when one escapes, is recorded properly
    # on the event itself.

    if name in ("exc_value", "traceback") and value is not None:
        return f"<{type(value).__name__}>"

    if name is None:
        return f"<{type(value).__name__}>"

    return value


def operation_of(sql: str) -> str:
    """The SQL's leading keyword, uppercased: the low-cardinality
    operation name the database contract carries."""

    head = sql.split(None, 1)

    return head[0].upper() if head else "?"


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the connect factories and the proxy methods; register
    their removal as this trigger's cleanup."""

    settings = instrumentation.settings
    record_statement = bool(settings["statement"])

    def queries(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        sql = args[0] if args else kwargs.get("sql") or kwargs.get("sql_script")

        if isinstance(sql, str):
            data: dict[str, Any] = {
                "system": "sqlite",
                "operation": operation_of(sql),
            }
            if record_statement:
                data["statement"] = sql
            wrapture.annotate(**data)

        return wrapped(*args, **kwargs)

    def performs(operation: str) -> Any:
        def record(
            wrapped: Any,
            instance: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:
            wrapture.annotate(system="sqlite", operation=operation)

            return wrapped(*args, **kwargs)

        return record

    def leaves(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # The context manager's exit is where sqlite3 commits, or
        # rolls back when an exception is on its way through.

        operation = "COMMIT" if args and args[0] is None else "ROLLBACK"
        wrapture.annotate(system="sqlite", operation=operation)

        return wrapped(*args, **kwargs)

    def opens(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        wrapture.annotate(system="sqlite", operation="CONNECT")

        # The C factory's arguments arrive unnamed, so the database
        # path rides as data rather than as a captured argument.

        database = args[0] if args else kwargs.get("database")
        if isinstance(database, (str, bytes)):
            wrapture.annotate(database=str(database))

        return Connection(wrapped(*args, **kwargs))

    def database_binding(target: Any, name: str, label: str | None = None) -> Any:
        return wrapture.binding(
            target,
            name,
            label=label,
            category="database",
            leaf=True,
            capture_args=captured,
            capture_result=captured,
        )

    # The factories: both module attributes, the same function under
    # two names, each recording the open and wrapping its result. The
    # paths say sqlite3:connect and sqlite3.dbapi2:connect already,
    # so neither takes a label.

    connect = database_binding(module, "connect")
    connect.on_call.decorates(opens)

    dbapi2_connect = database_binding(module.dbapi2, "connect")
    dbapi2_connect.on_call.decorates(opens)

    named: dict[str, wrapture.Binding] = {
        "connect": connect,
        "dbapi2_connect": dbapi2_connect,
    }

    # The execute family, on the cursor proxy and the connection's
    # shortcut forms alike, labelled with the sqlite3 names they
    # notionally wrap.

    for owner, cls in (("Cursor", Cursor), ("Connection", Connection)):
        for method in ("execute", "executemany", "executescript"):
            bound = database_binding(cls, method, label=f"sqlite3:{owner}.{method}")
            bound.on_call.decorates(queries)
            named[f"{owner.lower()}_{method}"] = bound

    # The transaction boundaries: the explicit calls, and the context
    # manager exit that performs one of them.

    for method, operation in (("commit", "COMMIT"), ("rollback", "ROLLBACK")):
        bound = database_binding(
            Connection, method, label=f"sqlite3:Connection.{method}"
        )
        bound.on_call.decorates(performs(operation))
        named[method] = bound

    closes = database_binding(
        Connection, "__exit__", label="sqlite3:Connection.__exit__"
    )
    closes.on_call.decorates(leaves)
    named["exit"] = closes

    group = wrapture.bindings(**named)
    group.apply()

    instrumentation.on_cleanup(group.remove)
