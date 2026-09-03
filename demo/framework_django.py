"""Drive a Django application with the django and sqlite3
instrumentations applied together.

The instrumentations are resolved by their entry point names, the way
a config file finds them, and the application is the tests' own shop
app, configured and imported only after the instrumentations apply,
the order the runner guarantees in real use. Applying both is the
point: with the django target's `leaf` on (the default) each ORM
query is a terminal node and the sqlite3 driver's events fold into
it, one database event per query.

The requests go through the real handlers, a WSGIHandler driven by
the tests' WSGI driver and then an ASGIHandler driven by the ASGI
one, covering every view shape: plain views, a route with an int
converter, a class-based view, an async view, views that query and
populate the database inside atomic(), a DTL render, a streaming
response, an Http404 (its status, no failure), a 404 that matched no
route, and a view that raises (Django answers 500 and the exception
is noted against the request event).

Two views of the run always print: the live stream, one line as each
operation begins and a closing line with its outcome, and the tidy
tree reconstructed afterwards with timings. With --otel the same
events also export as OpenTelemetry spans to a local OTLP endpoint
(http://localhost:4318 unless OTEL_EXPORTER_OTLP_ENDPOINT says
otherwise), for verifying the spans in a backend such as Jaeger:

    docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one
"""

from __future__ import annotations

import argparse
import os
import sys

import wrapture

WSGI_REQUESTS: tuple[tuple[str, str, str], ...] = (
    ("GET", "/", ""),
    ("GET", "/quote/widget/", "token=hunter2&item=widget"),
    ("GET", "/archive/1999/", ""),
    ("GET", "/catalog/", ""),
    ("GET", "/restock/", ""),
    ("GET", "/stocked/", ""),
    ("GET", "/pricelist/", "person=pat"),
    ("GET", "/export/", ""),
    ("GET", "/missing/", ""),
    ("GET", "/nowhere", ""),
    ("GET", "/quote/missing/", ""),
)

ASGI_REQUESTS: tuple[tuple[str, str, str], ...] = (
    ("GET", "/motd/", ""),
    ("GET", "/", ""),
)


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink, exporting the run's events as
    spans; exits with guidance when the optional dependencies are
    missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-django --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-django-demo"))


def configure_django() -> None:
    """Configure the minimum settings the shop app needs and set
    Django up, the demo's stand-in for a project's settings module."""

    from pathlib import Path

    import django
    from django.conf import settings

    import tests.framework.django

    settings.configure(
        DEBUG=False,
        SECRET_KEY="demo-only",
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
                "DIRS": [
                    str(Path(tests.framework.django.__file__).parent / "templates")
                ],
                "APP_DIRS": False,
                "OPTIONS": {},
            }
        ],
        ALLOWED_HOSTS=["*"],
        USE_TZ=True,
    )
    django.setup()


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentations, drive the requests
    through both handlers, print the live stream and the tree, and
    flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.framework_django",
        description="Drive a Django application with the django and"
        " sqlite3 instrumentations applied, printing the live stream"
        " and the tree.",
    )
    parser.add_argument(
        "--otel",
        action="store_true",
        help="also export the events as OpenTelemetry spans over OTLP",
    )
    options = parser.parse_args(arguments)

    # The exporting sink registers first, mirroring the config loader,
    # which always puts the [otel] table's sink ahead of the [[sink]]
    # list; the printer writes to stdout so the stream and the demo's
    # own headings interleave in order.

    if options.otel:
        add_otel_sink()

    wrapture.add_sink(wrapture.Printer(stream=sys.stdout))

    print("== live stream ==")

    with wrapture.instrumentation("django", "sqlite3"), wrapture.timeline() as tape:
        configure_django()

        from django.db import connection

        from tests import asgi, wsgi
        from tests.framework.django.shop import make_asgi_app, make_wsgi_app
        from tests.framework.django.shop.models import Item

        # The model's table, created without migrations; the schema
        # editor's statements record like any other, an honest look
        # at what setup costs.

        with connection.schema_editor() as editor:
            editor.create_model(Item)

        app = make_wsgi_app()
        for method, path, query in WSGI_REQUESTS:
            wsgi.request(app, method, path, query=query)

        aapp = make_asgi_app()
        for method, path, query in ASGI_REQUESTS:
            asgi.request(aapp, method, path, query=query)

    print()
    print("== tree ==")
    print(tape.tree(times=True))

    # Deliver everything owed: batched spans push to the exporter here
    # rather than at interpreter exit, so the closing hint below is
    # true by the time it prints.

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print(f"spans flushed to {endpoint} as service wrapture-django-demo")


if __name__ == "__main__":
    main()
