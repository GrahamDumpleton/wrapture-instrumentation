"""Shared Django setup for the suite.

Django wants its settings configured, and django.setup() run, before
most of it imports cleanly, and pytest imports this conftest before
any test module in the directory, so the configuration happens here
at import time: the test modules then import Django symbols at top
level like any other suite. The settings are the minimum the suite
needs: an in-memory sqlite database, the shop app and its urlconf,
the DTL backend over the suite's templates directory, and
ALLOWED_HOSTS wide open because the repo's wsgi/asgi drivers set the
host header, not Django's test client.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import django
import pytest
from django.conf import settings as django_settings
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation.framework.django import DjangoInstrumentation

if not django_settings.configured:
    django_settings.configure(
        DEBUG=False,
        SECRET_KEY="tests-only",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        ROOT_URLCONF="tests.framework.django.shop.urls",
        INSTALLED_APPS=["tests.framework.django.shop"],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [str(Path(__file__).parent / "templates")],
                "APP_DIRS": False,
                "OPTIONS": {},
            }
        ],
        ALLOWED_HOSTS=["*"],
        USE_TZ=True,
    )
    django.setup()


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(DjangoInstrumentation), timeline() as recorded:
        yield recorded


@pytest.fixture
def database() -> Iterator[None]:
    """The shop model's table, created without migrations.

    Tests that use this alongside tape list it first, so the schema
    editor's statements run before the instrumentation applies and
    stay off the tape; teardown runs after the tape closes for the
    same reason. The table is dropped explicitly: Django deliberately
    ignores close() on an in-memory sqlite connection, so the
    database, and anything left in it, outlives the test.
    """

    from django.db import connection

    from tests.framework.django.shop.models import Item

    with connection.schema_editor() as editor:
        editor.create_model(Item)

    try:
        yield
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Item)
