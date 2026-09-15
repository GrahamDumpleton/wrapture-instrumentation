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
from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

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

    settings = DjangoInstrumentation.settings
    assert list(settings) == ["requests", "views", "queries", "templates", "exceptions"]

    requests = settings["requests"]
    assert isinstance(requests, Aspect)
    assert requests.primary is True
    assert requests.defaults == {}
    assert set(requests.settings) == {"ignore_paths"}
    assert requests.settings["ignore_paths"].default == []

    views = settings["views"]
    assert isinstance(views, Aspect)
    assert views.primary is False
    assert callable(views.defaults["capture_args"])
    assert views.defaults["capture_result"] == "shape"
    assert set(views.settings) == set()

    queries = settings["queries"]
    assert isinstance(queries, Aspect)
    assert queries.primary is False
    assert queries.defaults == {"leaf": True}
    assert set(queries.settings) == {"statement"}
    assert queries.settings["statement"].default is False

    templates = settings["templates"]
    assert isinstance(templates, Aspect)
    assert templates.primary is False
    assert templates.defaults == {}
    assert set(templates.settings) == set()

    exceptions = settings["exceptions"]
    assert isinstance(exceptions, Aspect)
    assert exceptions.primary is False
    assert exceptions.defaults == {}
    assert set(exceptions.settings) == set()


def test_the_description_is_the_docstring_first_line() -> None:
    assert (DjangoInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request, database and template tracing for Django applications."
    )


def test_constructing_without_settings_works() -> None:
    instance = DjangoInstrumentation()

    requests = instance.settings["requests"]
    assert requests.enabled is True
    assert requests.options == {}
    assert requests.settings == {"ignore_paths": []}

    views = instance.settings["views"]
    assert views.enabled is True
    assert callable(views.options["capture_args"])
    assert views.options["capture_result"] == "shape"
    assert views.settings == {}

    queries = instance.settings["queries"]
    assert queries.enabled is True
    assert queries.options == {"leaf": True}
    assert queries.settings == {"statement": False}

    templates = instance.settings["templates"]
    assert templates.enabled is True
    assert templates.options == {}
    assert templates.settings == {}

    exceptions = instance.settings["exceptions"]
    assert exceptions.enabled is True
    assert exceptions.options == {}
    assert exceptions.settings == {}
    assert instance.applied == ()
    assert instance.pending == MODULES


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        DjangoInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': capture_result"):
        DjangoInstrumentation(requests={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': unknown keys"):
        DjangoInstrumentation(requests={"verbosity": 2})


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
