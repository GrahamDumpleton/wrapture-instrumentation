"""The dialect execution seam: every statement and every connection
the dialect opens, recorded as database events.

Since SQLAlchemy 1.4 every execution path, Core and ORM, sync and
async engine alike, funnels into three methods on the dialect the
engine holds: `do_execute`, `do_executemany` and
`do_execute_no_params`, each handed the cursor, the compiled
statement, its parameters and the execution context. Binding them on
`DefaultDialect` covers every driver dialect at once, because they
all inherit the trio (a handful override `do_executemany` with a
driver fast path; the dialects module binds those overrides as their
modules load). An async engine runs the same synchronous dialect
under the hood, so the one seam covers it too.

`DefaultDialect.connect` is the fourth binding: the pool calls it
whenever it really opens a new database connection, so connection
churn shows up where a pooled checkout stays silent. Its arguments
are the driver's credentials, so nothing of them is captured.

Every event carries `system` (the dialect's name: `sqlite`,
`postgresql`) and `operation` (the SQL's leading keyword, or
`CONNECT`), the database category's contract keys, plus the
`database` and, for a server database, `host` and `port` from the
engine's URL. The SQL text itself is recorded only when the
`statement` setting is on, never with its bound parameters, which no
setting captures; with the setting off the text reduces to its
length in the captured arguments.

A failing statement records the driver-level exception the seam
sees; the `DBAPIError` the application catches is the wrapper
SQLAlchemy adds above it afterwards.
"""

from __future__ import annotations

from typing import Any

import wrapture


def operation_of(sql: str) -> str:
    """The SQL's leading keyword, uppercased: the low-cardinality
    operation name the database contract carries."""

    head = sql.split(None, 1)

    return head[0].upper() if head else "?"


def captured(name: str | None, value: Any) -> Any:
    """SQL text reduces to its length, parameters to a count, and
    everything else (cursors, contexts, results) to its type: the
    query and its data never reach the record through argument
    capture."""

    if name == "statement" and isinstance(value, str):
        return f"<{len(value)} chars>"

    if name == "parameters":
        if isinstance(value, (list, tuple, dict)):
            return f"<{len(value)} values>"
        return f"<{type(value).__name__}>"

    # The cursor and the execution context are live objects whose
    # reprs carry memory addresses; their types say all the record
    # needs.

    if name in ("cursor", "context") and value is not None:
        return f"<{type(value).__name__}>"

    if name is None:
        return f"<{type(value).__name__}>"

    return value


def statement_binding(
    owner: Any,
    name: str,
    instrumentation: wrapture.Instrumentation,
) -> wrapture.Binding:
    """A ready binding on one of the do_execute family, annotating
    each call with the database contract keys; shared with the
    dialects module for the overriding driver dialects."""

    settings = instrumentation.settings
    record_statement = bool(settings["statement"])

    # The trio's signatures differ only in do_execute_no_params
    # dropping the parameters slot, moving context one position up.

    context_slot = 2 if name == "do_execute_no_params" else 3

    def executes(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        statement = args[1] if len(args) > 1 else kwargs.get("statement")
        context = (
            args[context_slot] if len(args) > context_slot else kwargs.get("context")
        )

        if isinstance(statement, str):
            data: dict[str, Any] = {
                "system": instance.name,
                "operation": operation_of(statement),
            }

            # The execution context carries the engine, whose URL says
            # which database this statement went to.

            if context is not None:
                url = context.engine.url
                if url.database:
                    data["database"] = url.database
                if url.host:
                    data["host"] = url.host
                if url.port:
                    data["port"] = url.port

            if record_statement:
                data["statement"] = statement

            wrapture.annotate(**data)

        return wrapped(*args, **kwargs)

    binding = wrapture.binding(
        owner,
        name,
        category="database",
        leaf=bool(settings["leaf"]),
        capture_args=captured,
        capture_result=captured,
    )
    binding.on_call.decorates(executes)

    return binding


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the do_execute trio and the connect seam on
    DefaultDialect; register their removal as this trigger's
    cleanup."""

    settings = instrumentation.settings

    def opens(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        wrapture.annotate(system=instance.name, operation="CONNECT")

        return wrapped(*args, **kwargs)

    # The connect seam: its arguments are the driver's credentials,
    # so nothing of them is captured; the result reduces to its type.

    connect = wrapture.binding(
        module.DefaultDialect,
        "connect",
        category="database",
        leaf=bool(settings["leaf"]),
        capture_args="none",
        capture_result=captured,
    )
    connect.on_call.decorates(opens)

    group = wrapture.bindings(
        do_execute=statement_binding(
            module.DefaultDialect, "do_execute", instrumentation
        ),
        do_executemany=statement_binding(
            module.DefaultDialect, "do_executemany", instrumentation
        ),
        do_execute_no_params=statement_binding(
            module.DefaultDialect, "do_execute_no_params", instrumentation
        ),
        connect=connect,
    )
    group.apply()

    instrumentation.on_cleanup(group.remove)
