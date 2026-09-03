"""Drive a Starlette application with the instrumentation applied.

The instrumentation is resolved by its entry point name, and the
application is built only after it applies, the order the runner
guarantees in real use, so its routes register observed endpoints.
The requests are driven in process through the ASGI test driver and
cover the shapes that matter: an async endpoint, a sync endpoint run
in starlette's threadpool, a path parameter with its route pattern
annotated, a query string with its secrets masked, a 404 that
matched no route, and an endpoint that raises (starlette answers 500
and re-raises, the failure landing on the request event and the
endpoint's own, the failing request last so the stream ends on it).

Two views of the run always print: the live stream and the tree
reconstructed with timings. With --otel the same events also export
as OpenTelemetry spans to a local OTLP endpoint
(http://localhost:4318 unless OTEL_EXPORTER_OTLP_ENDPOINT says
otherwise).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import wrapture

REQUESTS: tuple[tuple[str, str], ...] = (
    ("/", ""),
    ("/quote/widget", "token=hunter2&item=widget"),
    ("/pricing", ""),
    ("/nowhere", ""),
    ("/quote/missing", ""),
)


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-starlette --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-starlette-demo"))


def make_app() -> Any:
    """Build the shop application: async, sync, parameterised and
    failing endpoints."""

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    prices = {"widget": 42, "gadget": 7}

    async def index(request: Any) -> PlainTextResponse:
        return PlainTextResponse("shop")

    async def quoted(request: Any) -> PlainTextResponse:
        item = request.path_params["item"]

        return PlainTextResponse(f"{item}: {prices[item]} coins")

    def pricing(request: Any) -> PlainTextResponse:
        return PlainTextResponse("all prices on request")

    return Starlette(
        routes=[
            Route("/", index),
            Route("/quote/{item}", quoted),
            Route("/pricing", pricing, name="prices"),
        ]
    )


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, drive the requests,
    print the live stream and the tree, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.framework_starlette",
        description="Drive a Starlette application with the instrumentation"
        " applied, printing the live stream and the tree.",
    )
    parser.add_argument(
        "--otel",
        action="store_true",
        help="also export the events as OpenTelemetry spans over OTLP",
    )
    options = parser.parse_args(arguments)

    if options.otel:
        add_otel_sink()

    wrapture.add_sink(wrapture.Printer(stream=sys.stdout))

    print("== live stream ==")

    with wrapture.instrumentation("starlette"), wrapture.timeline() as tape:
        from tests.asgi import request

        app = make_app()

        for path, query in REQUESTS:
            try:
                response = request(app, "GET", path, query=query)
                print(f"{path}: {response.code} {response.text!r}")
            except KeyError as error:
                print(f"{path}: raised KeyError({error}) after the 500")

    print()
    print("== tree ==")
    print(tape.tree(times=True))

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print(f"spans flushed to {endpoint} as service wrapture-starlette-demo")


if __name__ == "__main__":
    main()
