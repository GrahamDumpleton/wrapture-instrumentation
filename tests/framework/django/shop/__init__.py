"""The suite's Django app: models, views and urlconf, plus the
handler builders, made only when asked so the tests control whether
construction happens under instrumentation."""

from __future__ import annotations

from typing import Any


def make_wsgi_app() -> Any:
    """A fresh WSGIHandler, the real WSGI boundary the drivers call."""

    from django.core.wsgi import get_wsgi_application

    return get_wsgi_application()


def make_asgi_app() -> Any:
    """A fresh ASGIHandler, the real ASGI boundary the drivers call."""

    from django.core.asgi import get_asgi_application

    return get_asgi_application()
