"""Instrumentation for SQLAlchemy: every statement an engine
executes, the connections its dialects open and the transaction
boundaries, recorded as database events at the dialect seam every
driver sits behind.

This module imports only wrapture. Everything that touches SQLAlchemy
lives in sibling submodules, one per SQLAlchemy module patched
(engine_default.py for sqlalchemy.engine.default), each importing
only wrapture at top level, so loading this class when a config loads
never imports SQLAlchemy ahead of the hooks meant to fire on its
import.

The last four hooks cover the driver dialects that override
`do_executemany` with a driver-specific fast path (psycopg2's
batch helpers and their kin): each fires only if its module is
imported, binding the override so those statements record like any
other.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import dialects, engine_base, engine_default


class SQLAlchemyInstrumentation(wrapture.Instrumentation):
    """Query and transaction tracing for SQLAlchemy engines."""

    description = "Query and transaction tracing for SQLAlchemy engines."

    target = "sqlalchemy"
    supports = ">=1.4,<3"
    removable = True

    settings = {
        "leaf": Setting(
            True,
            "record each statement as a terminal node, so anything"
            " recorded beneath it (an instrumented driver such as"
            " sqlite3) stays out of the tree",
        ),
        "statement": Setting(
            False,
            "record the SQL text as compiled on each statement event;"
            " off by default because text() fragments pass through as"
            " the application wrote them, literals included; SQL the"
            " expression language compiles carries placeholders, its"
            " parameters sent separately and never recorded",
        ),
    }

    @wrapture.instrumentation_hook("sqlalchemy.engine.default")
    def sqlalchemy_engine_default(self, name: str, module: Any) -> None:
        """Bind the dialect execution seam once the default dialect
        exists."""

        engine_default.instrument(module, self)

    @wrapture.instrumentation_hook("sqlalchemy.engine.base")
    def sqlalchemy_engine_base(self, name: str, module: Any) -> None:
        """Bind the transaction boundaries once Connection exists."""

        engine_base.instrument(module, self)

    @wrapture.instrumentation_hook("sqlalchemy.dialects.mssql.pyodbc")
    def sqlalchemy_dialects_mssql_pyodbc(self, name: str, module: Any) -> None:
        """Bind pyodbc's do_executemany override if that dialect
        loads."""

        dialects.instrument(module, "MSDialect_pyodbc", self)

    @wrapture.instrumentation_hook("sqlalchemy.dialects.mysql.mysqldb")
    def sqlalchemy_dialects_mysql_mysqldb(self, name: str, module: Any) -> None:
        """Bind mysqldb's do_executemany override if that dialect
        loads."""

        dialects.instrument(module, "MySQLDialect_mysqldb", self)

    @wrapture.instrumentation_hook("sqlalchemy.dialects.oracle.cx_oracle")
    def sqlalchemy_dialects_oracle_cx_oracle(self, name: str, module: Any) -> None:
        """Bind cx_oracle's do_executemany override if that dialect
        loads."""

        dialects.instrument(module, "OracleDialect_cx_oracle", self)

    @wrapture.instrumentation_hook("sqlalchemy.dialects.postgresql.psycopg2")
    def sqlalchemy_dialects_postgresql_psycopg2(self, name: str, module: Any) -> None:
        """Bind psycopg2's do_executemany override if that dialect
        loads."""

        dialects.instrument(module, "PGDialect_psycopg2", self)
