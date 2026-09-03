"""Instrumentation for Django: request, database and template tracing
for every application the process serves.

This module imports only wrapture. Everything that touches Django
lives in sibling submodules, each importing only wrapture at top
level, so loading this class when a config loads never imports Django
ahead of the hooks meant to fire on its import.

A naming note: the shipped convention names each patch module after
the target module it patches, but Django's last components collide
(django.core.handlers.base and django.db.backends.base.base are both
"base", and django.db.backends.utils says nothing), so this target
uses descriptive module names instead. Each module still serves
exactly one hook module, except handlers.py (one function each for
the wsgi and asgi hooks) and db.py (one each for the cursor and
transaction hooks).
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Setting

from . import db, dispatch, exceptions, handlers, resolvers, templates


class DjangoInstrumentation(wrapture.Instrumentation):
    """Request, database and template tracing for Django applications.

    One target whose events span three categories: the WSGI/ASGI
    boundary records request events, the ORM cursor and transaction
    bindings record database events (the same contract keys the
    sqlite3 and sqlalchemy targets carry), and the DTL render binding
    records template events (as the jinja2 target does). The category
    on an event comes from the binding that records it, not from the
    directory the code lives in; the directory is chosen by the
    target's primary machinery, the request framework, hence
    framework/django.
    """

    description = "Request, database and template tracing for Django applications."

    target = "django"
    supports = ">=4.2,<7"
    removable = True

    # The category switches: which layers of the instrumentation are
    # in play. The request tree, route annotation, view observation
    # and unhandled-exception noting are the point and have no switch.

    settings = {
        "ignore_paths": Setting(
            [],
            "request paths not to record, as path globs ('/health', '/static/*')",
        ),
        "redact": Setting(
            [],
            "query string parameters to mask by name, on top of the"
            " built-in sensitive set",
        ),
        "queries": Setting(
            True,
            "record ORM statements and transaction ends as database events",
        ),
        "statement": Setting(
            False,
            "record the SQL text on each query event; off by default"
            " because raw SQL and literal filters can carry data; the"
            " ORM's bound parameters are sent separately and never"
            " recorded",
        ),
        "leaf": Setting(
            True,
            "record each query as a terminal node, so anything"
            " recorded beneath it (an instrumented driver such as"
            " sqlite3) stays out of the tree",
        ),
        "templates": Setting(
            True,
            "observe Django template rendering beneath the view that asked for it",
        ),
    }

    @wrapture.instrumentation_hook("django.core.handlers.wsgi")
    def django_core_handlers_wsgi(self, name: str, module: Any) -> None:
        """Bind the WSGI request boundary once WSGIHandler exists."""

        handlers.instrument_wsgi(module, self)

    @wrapture.instrumentation_hook("django.core.handlers.asgi")
    def django_core_handlers_asgi(self, name: str, module: Any) -> None:
        """Bind the ASGI request boundary once ASGIHandler exists."""

        handlers.instrument_asgi(module, self)

    @wrapture.instrumentation_hook("django.core.handlers.base")
    def django_core_handlers_base(self, name: str, module: Any) -> None:
        """Bind the route annotation on BaseHandler's dispatch, both
        transports, once the module exists."""

        dispatch.instrument(module, self)

    @wrapture.instrumentation_hook("django.core.handlers.exception")
    def django_core_handlers_exception(self, name: str, module: Any) -> None:
        """Bind the unhandled-exception noting once the catch-all
        exists."""

        exceptions.instrument(module, self)

    @wrapture.instrumentation_hook("django.urls.resolvers")
    def django_urls_resolvers(self, name: str, module: Any) -> None:
        """Bind the view observation at URL resolution once
        ResolverMatch exists."""

        resolvers.instrument(module, self)

    @wrapture.instrumentation_hook("django.db.backends.utils")
    def django_db_backends_utils(self, name: str, module: Any) -> None:
        """Bind the ORM query seam once CursorWrapper exists."""

        db.instrument_cursors(module, self)

    @wrapture.instrumentation_hook("django.db.backends.base.base")
    def django_db_backends_base_base(self, name: str, module: Any) -> None:
        """Bind the transaction ends once BaseDatabaseWrapper exists."""

        db.instrument_transactions(module, self)

    @wrapture.instrumentation_hook("django.template.base")
    def django_template_base(self, name: str, module: Any) -> None:
        """Bind the DTL render observation once Template exists."""

        templates.instrument(module, self)
