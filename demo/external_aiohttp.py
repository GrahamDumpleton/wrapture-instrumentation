"""Drive aiohttp's client against a local server with the
instrumentation applied.

The instrumentation is resolved by its entry point name, and the
requests go over a loopback socket to the suite's own server,
started after the instrumentation applies. One async pass covers the
shapes that matter: a plain GET, a POST with a body (never
recorded), a request with a query string (recorded with its secrets
masked), a followed redirect (one event, the hops resolved inside
it), and a 404 (a status like any other: aiohttp raises nothing for
it). Each request is made beneath an observed function, so the leaf
sits in a tree whose identity travels to the server in the request
headers.

Two views of the run always print: the live stream and the tree
reconstructed with timings, then the trace headers the server
received. With --otel the same events also export as OpenTelemetry
spans to a local OTLP endpoint (http://localhost:4318 unless
OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-aiohttp-client --otel`, which"
            " overlays wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-aiohttp-client-demo"))


async def drive(base: str) -> list[str]:
    """Make the requests through one ClientSession, returning a line
    per request for the live view."""

    from aiohttp import ClientSession

    lines: list[str] = []

    @wrapture.observed
    async def fetch(session: ClientSession, path: str, post: bool) -> str:
        if post:
            request = session.post(f"{base}{path}", data={"name": "pat"})
        else:
            request = session.get(f"{base}{path}")

        async with request as response:
            body = await response.text()
            return f"{response.status} {body!r}"

    async with ClientSession() as session:
        for path, post in (
            ("/ok", False),
            ("/echo", True),
            ("/ok?token=hunter2", False),
            ("/redirect", False),
            ("/missing", False),
        ):
            lines.append(f"{path}: {await fetch(session, path, post)}")

    return lines


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, make the requests,
    print the live stream and the tree, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.external_aiohttp",
        description="Drive aiohttp's client against a local server with"
        " the instrumentation applied, printing the live stream and the"
        " tree.",
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

    server: Any = None

    with wrapture.instrumentation("aiohttp.client"), wrapture.timeline() as tape:
        from tests.httpserver import serve

        serving = serve()
        server = next(serving)

        try:
            for line in asyncio.run(drive(server.url)):
                print(line)
        finally:
            next(serving, None)

    print()
    print("== tree ==")
    print(tape.tree(times=True))

    print()
    print("== headers the server received ==")
    for seen in server.received:
        headers = {name.lower(): value for name, value in seen.headers.items()}
        traceparent = headers.get("traceparent", "(none)")
        print(f"{seen.method} {seen.path}  traceparent: {traceparent}")

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print(f"spans flushed to {endpoint} as service wrapture-aiohttp-client-demo")


if __name__ == "__main__":
    main()
