"""Applying and removing: the patched names, and that removal leaves
Django as it was whatever the settings."""

from __future__ import annotations

from typing import Any

import django.core.handlers.asgi
import django.core.handlers.base
import django.core.handlers.exception
import django.core.handlers.wsgi
import django.db.backends.base.base
import django.db.backends.utils
import django.template.base
import django.urls.resolvers
import pytest
from wrapture import instrumentation

from wrapture_instrumentation.framework.django import DjangoInstrumentation

MODULES = (
    "django.core.handlers.wsgi",
    "django.core.handlers.asgi",
    "django.core.handlers.base",
    "django.core.handlers.exception",
    "django.urls.resolvers",
    "django.db.backends.utils",
    "django.db.backends.base.base",
    "django.template.base",
)

# The always-patched names, and the names the queries and templates
# settings gate.

CORE = (
    "wsgi_call",
    "asgi_call",
    "respond",
    "respond_async",
    "uncaught",
    "match",
)

QUERIES = ("execute", "executemany", "commit", "rollback")

TEMPLATES = ("render",)


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "wsgi_call": django.core.handlers.wsgi.WSGIHandler.__call__,
        "asgi_call": django.core.handlers.asgi.ASGIHandler.__call__,
        "respond": django.core.handlers.base.BaseHandler._get_response,
        "respond_async": django.core.handlers.base.BaseHandler._get_response_async,
        "uncaught": django.core.handlers.exception.handle_uncaught_exception,
        "match": django.urls.resolvers.ResolverMatch.__init__,
        "execute": django.db.backends.utils.CursorWrapper.execute,
        "executemany": django.db.backends.utils.CursorWrapper.executemany,
        "commit": django.db.backends.base.base.BaseDatabaseWrapper.commit,
        "rollback": django.db.backends.base.base.BaseDatabaseWrapper.rollback,
        "render": django.template.base.Template.render,
    }


@pytest.mark.parametrize(
    ("settings", "patched"),
    [
        ({}, CORE + QUERIES + TEMPLATES),
        ({"ignore_paths": ["/health"]}, CORE + QUERIES + TEMPLATES),
        ({"queries": False}, CORE + TEMPLATES),
        ({"templates": False}, CORE + QUERIES),
    ],
)
def test_apply_then_remove_leaves_the_modules_as_they_were(
    settings: dict[str, Any], patched: tuple[str, ...]
) -> None:
    # The request settings shape the middleware, not the patch; the
    # queries and templates switches gate whole binding groups, whose
    # triggers still count as applied with nothing bound.

    before = choke_points()

    with instrumentation(DjangoInstrumentation, **settings) as record:
        (instance,) = record.instrumentations

        assert instance.applied == MODULES

        current = choke_points()
        for name in before:
            if name in patched:
                assert current[name] is not before[name], name
            else:
                assert current[name] is before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied
