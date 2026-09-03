"""Serve an aiohttp.web application with the instrumentation
applied, driven by an instrumented httpx client, in one process.

Both instrumentations are resolved by their entry point names, and
the application is built only after they apply, so its routes
register observed handlers. Server and client share one event loop:
the application is served on a loopback socket and the async httpx
client drives it through the requests that matter, a plain page, a
named route with a query string whose secrets are masked, an
HTTPException answered as its status, a handler that really fails
(the server answers 500 and the boundary records the exception), and
a path that matches no route. The client's external leaf and the
server's request boundary share one distributed trace id, carried by
nothing but the traceparent header the client added.

The live stream prints as it happens, then the trees reconstructed
with timings and the trace id per root, showing the joins. With
--otel the same events also export as OpenTelemetry spans to a local
OTLP endpoint (http://localhost:4318 unless
OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

import wrapture

REQUESTS: tuple[str, ...] = (
    "/",
    "/quote/widget?item=widget&token=hunter2",
    "/gone",
    "/quote/missing",
    "/nowhere",
)


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-aiohttp --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-aiohttp-demo"))


def make_app() -> Any:
    """Build the shop application: a plain page, a named route, an
    HTTPException answer and a handler that really fails."""

    from aiohttp import web

    prices = {"widget": 42, "gadget": 7}

    async def index(request: web.Request) -> web.Response:
        return web.Response(text="shop open")

    async def quoted(request: web.Request) -> web.Response:
        item = request.match_info["item"]

        return web.Response(text=f"{item}: {prices[item]}")

    async def gone(request: web.Request) -> web.Response:
        raise web.HTTPNotFound(text="no longer stocked")

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/quote/{item}", quoted, name="quoted")
    app.router.add_get("/gone", gone)

    return app


async def serve_and_fetch() -> None:
    """Serve the application on a loopback port and drive it with the
    async httpx client, both on this one event loop."""

    import httpx
    from aiohttp import web

    app = make_app()

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    ((host, port), *_) = runner.addresses

    try:
        async with httpx.AsyncClient() as client:
            for path in REQUESTS:
                response = await client.get(f"http://{host}:{port}{path}")
                print(f"{path}: {response.status_code} {response.text[:40]!r}")
    finally:
        await runner.cleanup()


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentations, serve and call the
    application, print the live stream and the trees, and flush any
    exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.server_aiohttp",
        description="Serve an aiohttp.web application with the"
        " instrumentation applied, driven by an instrumented httpx"
        " client, printing the live stream and the trees.",
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

    # The failing handler makes aiohttp log its traceback; the demo
    # narrates that failure itself, so the log noise is turned off.

    logging.getLogger("aiohttp.server").setLevel(logging.CRITICAL)

    print("==== aiohttp.web application, client and server joined ====")

    with (
        wrapture.instrumentation("aiohttp.web"),
        wrapture.instrumentation("httpx"),
        wrapture.timeline() as tape,
    ):
        asyncio.run(serve_and_fetch())

    print()
    print("==== trees ====")
    print(tape.tree(times=True))

    print("==== trace id per root ====")
    for root in tape.roots():
        slot = root.trace.slots["w3c"] if root.trace else None
        name = root.label or root.path
        print(f"{root.kind:>8}  {name:<55} {slot.trace_id if slot else '(none)'}")

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print("spans flushed to", endpoint, "as service wrapture-aiohttp-demo")


if __name__ == "__main__":
    main()
