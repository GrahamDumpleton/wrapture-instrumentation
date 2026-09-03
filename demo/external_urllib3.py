"""Drive urllib3 against a local server with the instrumentation
applied.

The instrumentation is resolved by its entry point name, and the
requests go over a loopback socket to the suite's own server, started
after the instrumentation applies. The requests cover the shapes that
matter: a manager request, a bare connection pool request (the lower
door), the module-level helper, a request with a query string
(recorded with its secrets masked), a redirect (one leaf, the nested
calls folded in) and a 404 (a status like any other). Each is made
beneath an observed function, so the leaf sits in a tree whose
identity travels to the server in the request headers.

Two views of the run always print: the live stream and the tree
reconstructed with timings, then the trace headers the server
received. With --otel the same events also export as OpenTelemetry
spans to a local OTLP endpoint (http://localhost:4318 unless
OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
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
            " demo through `just demo-urllib3 --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-urllib3-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, make the requests,
    print the live stream and the tree, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.external_urllib3",
        description="Drive urllib3 against a local server with the"
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

    with wrapture.instrumentation("urllib3"), wrapture.timeline() as tape:
        import urllib3

        from tests.httpserver import serve

        serving = serve()
        server = next(serving)
        authority = server.url.rpartition("/")[2]
        host, _, port = authority.rpartition(":")

        @wrapture.observed
        def fetch(description: str, make: Any) -> str:
            response = make()
            return f"{description}: {response.status}"

        try:
            with urllib3.PoolManager() as manager:
                print(
                    fetch("manager", lambda: manager.request("GET", f"{server.url}/ok"))
                )
                print(
                    fetch(
                        "query",
                        lambda: manager.request(
                            "GET", f"{server.url}/ok?token=hunter2"
                        ),
                    )
                )
                print(
                    fetch(
                        "redirect",
                        lambda: manager.request("GET", f"{server.url}/redirect"),
                    )
                )
                print(
                    fetch(
                        "missing",
                        lambda: manager.request("GET", f"{server.url}/missing"),
                    )
                )

            with urllib3.HTTPConnectionPool(host, int(port)) as pool:
                print(fetch("bare pool", lambda: pool.urlopen("GET", "/ok")))

            print(
                fetch(
                    "module helper", lambda: urllib3.request("GET", f"{server.url}/ok")
                )
            )
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
        print(f"spans flushed to {endpoint} as service wrapture-urllib3-demo")


if __name__ == "__main__":
    main()
