"""Drive a FastAPI application with the instrumentation applied.

The instrumentation is resolved by its entry point name, and the
application is built only after it applies, the order the runner
guarantees in real use, so its routes register observed endpoints.
The requests are driven in process through the ASGI test driver and
cover the shapes that matter: a typed async endpoint with a path
parameter and response model, a sync endpoint run in the threadpool,
a dependency resolved around its endpoint, a query string with its
secrets masked, a validation failure answered 422 without reaching
the endpoint, a 404 that matched no route, and an endpoint that
raises (the stack answers 500 and re-raises, the failure landing on
the request event and the endpoint's own, last so the stream ends on
it).

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
    ("/basket", ""),
    ("/count/plenty", ""),
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
            " demo through `just demo-fastapi --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-fastapi-demo"))


def make_app() -> Any:
    """Build the shop application: typed, sync, dependency-using and
    failing endpoints."""

    from fastapi import Depends, FastAPI
    from pydantic import BaseModel

    class Quote(BaseModel):
        item: str
        price: int

    prices = {"widget": 42, "gadget": 7}

    app = FastAPI()

    @app.get("/")
    async def index() -> dict[str, str]:
        return {"shop": "open"}

    @app.get("/quote/{item}", response_model=Quote)
    async def quoted(item: str) -> Any:
        return {"item": item, "price": prices[item]}

    @app.get("/pricing", name="prices")
    def pricing() -> dict[str, str]:
        return {"pricing": "on request"}

    def current_shopper() -> str:
        return "pat"

    @app.get("/basket")
    async def basket(shopper: str = Depends(current_shopper)) -> dict[str, str]:
        return {"shopper": shopper}

    @app.get("/count/{amount}")
    async def counted(amount: int) -> dict[str, int]:
        return {"amount": amount}

    return app


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, drive the requests,
    print the live stream and the tree, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.framework_fastapi",
        description="Drive a FastAPI application with the instrumentation"
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

    with wrapture.instrumentation("fastapi"), wrapture.timeline() as tape:
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
        print(f"spans flushed to {endpoint} as service wrapture-fastapi-demo")


if __name__ == "__main__":
    main()
