"""Drive the shop application with the Flask instrumentation applied.

The instrumentation is resolved by its entry point name, the way a
config file finds it, and the applications are the tests' own shop
and portal, built only after the instrumentation applies, the order
the runner guarantees in real use. The shop requests cover every
view shape: plain views, a streaming response, a class-based view, a
blueprint, and a view that raises (Flask answers 500 and the
exception is noted against the request event). The portal requests
cover the lifecycle: before/after/teardown callbacks, a handled
exception (the handler runs and the failure is noted), and a 404
whose handler runs without any failure being noted.

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

# Every route the shop registers, the failing request last so that
# stream ends on the interesting case; then the portal's lifecycle
# and error handling shapes.

SHOP_REQUESTS: tuple[tuple[str, str], ...] = (
    ("GET", "/"),
    ("GET", "/quote/widget"),
    ("GET", "/pricing"),
    ("GET", "/pricelist"),
    ("GET", "/motd"),
    ("GET", "/export"),
    ("GET", "/catalog"),
    ("GET", "/reports/summary"),
    ("GET", "/quote/missing"),
)

PORTAL_REQUESTS: tuple[tuple[str, str], ...] = (
    ("GET", "/"),
    ("GET", "/admin/panel"),
    ("GET", "/shaky"),
    ("GET", "/nowhere"),
    ("GET", "/broken"),
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
            " demo through `just demo-flask --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-flask-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, drive the requests,
    print the live stream and the tree, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.framework_flask",
        description="Drive the shop application with the Flask"
        " instrumentation applied, printing the live stream and the"
        " tree.",
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

    with wrapture.instrumentation("flask"), wrapture.timeline() as tape:
        from tests.framework_flask.portal import make_portal
        from tests.framework_flask.shop import make_app
        from tests.wsgi import request

        shop = make_app()
        for method, path in SHOP_REQUESTS:
            request(shop, method, path)

        portal = make_portal()
        for method, path in PORTAL_REQUESTS:
            request(portal, method, path)

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
        print(f"spans flushed to {endpoint} as service wrapture-flask-demo")


if __name__ == "__main__":
    main()
