"""The ORM query and transaction seams, recorded as database events.

Two hook modules share this file. Every query from every backend,
ORM and raw alike, funnels through CursorWrapper in
django.db.backends.utils: its execute and executemany are the
statement seam (CursorDebugWrapper's DEBUG-mode overrides call
straight through them, so one binding covers both wrappers). The
transaction ends are BaseDatabaseWrapper.commit and rollback in
django.db.backends.base.base: autocommit means many statements never
hit these, which is honest, they show the real transaction
boundaries atomic() and manual transactions create.

Every event carries `system` (the connection's vendor: `sqlite`,
`postgresql`) and `operation` (the SQL's leading keyword, or
COMMIT/ROLLBACK), the database category's contract keys, plus the
`database` and, for a server database, `host` and `port` from the
connection's settings. The SQL text itself is recorded only when the
`statement` setting is on, and then as an annotation, never with its
bound parameters, which no setting captures; with the setting off
the text reduces to its length in the captured arguments.

With `leaf` on (the default) each event is a terminal node, so an
instrumented driver beneath it (the sqlite3 target, a future
per-backend package) is folded in and the query records once; with
it off the driver's own events nest beneath. The `queries` setting
gates the whole file: with it off, neither hook binds anything.
"""

from __future__ import annotations

from typing import Any

import wrapture

from .common import captured, operation_of


def connection_data(connection: Any) -> dict[str, Any]:
    """The database contract keys the connection can supply: the
    vendor as the system, and the database, host and port from its
    settings."""

    data: dict[str, Any] = {"system": connection.vendor}

    settings_dict = getattr(connection, "settings_dict", None) or {}

    name = settings_dict.get("NAME")
    if name:
        data["database"] = str(name)

    host = settings_dict.get("HOST")
    if host:
        data["host"] = host

    port = settings_dict.get("PORT")
    if port:
        data["port"] = int(port) if str(port).isdigit() else port

    return data


def statement_binding(
    owner: Any,
    name: str,
    instrumentation: wrapture.Instrumentation,
) -> wrapture.Binding:
    """A ready binding on execute or executemany, annotating each
    call with the database contract keys."""

    settings = instrumentation.settings
    record_statement = bool(settings["statement"])

    def executes(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        # The cursor wrapper holds the connection as db, whose vendor
        # and settings say where this statement went.

        sql = args[0] if args else kwargs.get("sql")

        data = connection_data(instance.db)
        data["operation"] = operation_of(sql)

        if record_statement:
            data["statement"] = str(sql)

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


def instrument_cursors(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the statement seam on CursorWrapper; register its removal
    as this trigger's cleanup. The queries setting gates the whole
    trigger: with it off, nothing binds and there is nothing to clean
    up."""

    if not instrumentation.settings["queries"]:
        return

    group = wrapture.bindings(
        execute=statement_binding(module.CursorWrapper, "execute", instrumentation),
        executemany=statement_binding(
            module.CursorWrapper, "executemany", instrumentation
        ),
    )
    group.apply()

    instrumentation.on_cleanup(group.remove)


def instrument_transactions(
    module: Any, instrumentation: wrapture.Instrumentation
) -> None:
    """Bind the transaction ends on BaseDatabaseWrapper; register
    their removal as this trigger's cleanup. Gated by the queries
    setting exactly as the cursor seam is."""

    settings = instrumentation.settings

    if not settings["queries"]:
        return

    def performs(operation: str) -> Any:
        def record(
            wrapped: Any,
            instance: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:
            data = connection_data(instance)
            data["operation"] = operation

            wrapture.annotate(**data)

            return wrapped(*args, **kwargs)

        return record

    def boundary(name: str, operation: str) -> wrapture.Binding:
        binding = wrapture.binding(
            module.BaseDatabaseWrapper,
            name,
            category="database",
            leaf=bool(settings["leaf"]),
            capture_args=captured,
            capture_result=captured,
        )
        binding.on_call.decorates(performs(operation))

        return binding

    group = wrapture.bindings(
        commit=boundary("commit", "COMMIT"),
        rollback=boundary("rollback", "ROLLBACK"),
    )
    group.apply()

    instrumentation.on_cleanup(group.remove)
