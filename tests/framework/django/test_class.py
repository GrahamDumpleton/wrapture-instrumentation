"""The class as wrapture reads it: its data, its settings, and the
installed Django satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

# The trigger modules are imported for their side: the class's
# triggers fire on their import, so the applying test below works
# with this file run on its own.
import django.core.handlers.asgi  # noqa: F401
import django.core.handlers.base  # noqa: F401
import django.core.handlers.exception  # noqa: F401
import django.core.handlers.wsgi  # noqa: F401
import django.db.backends.base.base  # noqa: F401
import django.db.backends.utils  # noqa: F401
import django.template.base  # noqa: F401
import django.urls.resolvers  # noqa: F401
import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

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


def test_class_data() -> None:
    assert DjangoInstrumentation.target == "django"
    assert DjangoInstrumentation.removable is True
    assert DjangoInstrumentation.requires == ()
    assert DjangoInstrumentation.supports == ">=4.2,<7"

    assert set(DjangoInstrumentation.settings) == {
        "ignore_paths",
        "redact",
        "queries",
        "statement",
        "leaf",
        "templates",
    }
    assert DjangoInstrumentation.settings["ignore_paths"].default == []
    assert DjangoInstrumentation.settings["redact"].default == []
    assert DjangoInstrumentation.settings["queries"].default is True
    assert DjangoInstrumentation.settings["statement"].default is False
    assert DjangoInstrumentation.settings["leaf"].default is True
    assert DjangoInstrumentation.settings["templates"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    assert (DjangoInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request, database and template tracing for Django applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = DjangoInstrumentation()

    assert instance.settings == {
        "ignore_paths": [],
        "redact": [],
        "queries": True,
        "statement": False,
        "leaf": True,
        "templates": True,
    }
    assert instance.applied == ()
    assert instance.pending == MODULES


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="lifecycle"):
        DjangoInstrumentation(lifecycle=False)


def test_the_installed_django_is_within_supports() -> None:
    # wrapture gates on supports before firing any trigger and warns,
    # never errors, when the version is outside it; make that warning
    # an error here so a matrix entry outside the range fails loudly
    # instead of passing with nothing applied.

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(DjangoInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("django")
            assert applied.applied == MODULES
            assert applied.pending == ()
