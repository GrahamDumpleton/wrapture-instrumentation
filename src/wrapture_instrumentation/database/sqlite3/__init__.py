"""Instrumentation for sqlite3: every query and transaction boundary
recorded as a database operation, through proxies around the
connections the module hands out, since the module's own connection
and cursor types are C types no patch can touch.

This module imports only wrapture. Everything that touches sqlite3
lives in the sibling dbapi2 module, named for the sqlite3.dbapi2
module where the real connect factory lives, importing only wrapture
and wrapt at top level, so loading this class when a config loads
never imports sqlite3 ahead of the hook meant to fire on its import.

One trigger module suffices: importing sqlite3 initialises
sqlite3.dbapi2 (the package's own __init__ does), so by the time the
hook fires both modules exist and both connect attributes are
patched from the one trigger.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import dbapi2


class SQLite3Instrumentation(wrapture.Instrumentation):
    """Query and transaction tracing for sqlite3."""

    description = "Query and transaction tracing for sqlite3."

    # The target is the standard library module the class patches, so
    # its version is the interpreter's and supports is a Python version
    # range: every Python wrapture itself runs on.

    target = "sqlite3"
    supports = ">=3.12"
    removable = True

    settings = {
        "statement": Setting(
            False,
            "record the SQL text as written on each query event; off"
            " by default because sqlite3 code commonly interpolates"
            " literals into its SQL, and the text is only safe to"
            " record when queries are parameterized",
        ),
    }

    @wrapture.instrumentation_hook("sqlite3")
    def sqlite3(self, name: str, module: Any) -> None:
        """Bind the connect factories once sqlite3 exists."""

        dbapi2.instrument(module, self)
