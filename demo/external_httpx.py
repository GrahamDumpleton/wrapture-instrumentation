"""Drive httpx against a local server with the instrumentation
applied, through the sync client and then the async one.

The instrumentation is resolved by its entry point name, and the
requests go over a loopback socket to the suite's own server, started
after the instrumentation applies. The sync pass covers the shapes
that matter: a plain GET, a POST with a body (never recorded), a
request with a query string (recorded with its secrets masked), a
followed redirect (one event, the hops resolved inside it), and a
404 (a status like any other: httpx raises nothing for it). The
async pass then repeats a GET and the redirect through AsyncClient,
whose events record around the await. Each request is made beneath
an observed function, so the leaf sits in a tree whose identity
travels to the server in the request headers.

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

import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-httpx --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-httpx-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, make the requests
    sync then async, print the live stream and the tree, and flush
    any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.external_httpx",
        description="Drive httpx against a local server with the"
        " instrumentation applied, printing the live stream and the tree.",
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

    with wrapture.instrumentation("httpx"), wrapture.timeline() as tape:
        import httpx

        from tests.httpserver import serve

        serving = serve()
        server = next(serving)

        @wrapture.observed
        def fetch(path: str, data: dict[str, str] | None = None) -> str:
            if data is not None:
                response = httpx.post(f"{server.url}{path}", data=data)
            else:
                response = httpx.get(f"{server.url}{path}", follow_redirects=True)
            return f"{response.status_code} {response.text!r}"

        @wrapture.observed
        def fetch_async(path: str) -> str:
            async def go() -> str:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    response = await client.get(f"{server.url}{path}")
                    return f"{response.status_code} {response.text!r}"

            return asyncio.run(go())

        try:
            for path, data in (
                ("/ok", None),
                ("/echo", {"name": "pat"}),
                ("/ok?token=hunter2", None),
                ("/redirect", None),
                ("/missing", None),
            ):
                print(fetch(path, data))

            for path in ("/ok", "/redirect"):
                print(fetch_async(path))
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
        print(f"spans flushed to {endpoint} as service wrapture-httpx-demo")


if __name__ == "__main__":
    main()
