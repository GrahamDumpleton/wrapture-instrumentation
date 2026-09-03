"""The driver dialects that override do_executemany with a fast
path of their own: psycopg2's batch helpers, mysqldb's, cx_oracle's
and pyodbc's. A statement through one of those overrides never
reaches `DefaultDialect.do_executemany`, so each override is bound
in its own right, by a hook that fires only if its dialect module
ever loads.

The class is looked up by name and the override checked for on the
class itself, so a SQLAlchemy version that drops or renames one of
these fast paths leaves the hook a quiet no-op rather than an
error.
"""

from __future__ import annotations

from typing import Any

import wrapture

from .engine_default import statement_binding


def instrument(
    module: Any,
    class_name: str,
    instrumentation: wrapture.Instrumentation,
) -> None:
    """Bind the named dialect class's own do_executemany, if this
    SQLAlchemy defines one; register its removal as this trigger's
    cleanup."""

    dialect = getattr(module, class_name, None)

    if dialect is None or "do_executemany" not in vars(dialect):
        return

    group = wrapture.bindings(
        do_executemany=statement_binding(dialect, "do_executemany", instrumentation)
    )
    group.apply()

    instrumentation.on_cleanup(group.remove)
