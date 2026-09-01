"""Drive urllib against a local server with the instrumentation
applied.

The instrumentation is resolved by its entry point name, and the
requests go over a loopback socket to the suite's own server, started
after the instrumentation applies. The requests cover the shapes
that matter: a plain GET, a POST with a body (recorded by size), a
request with a query string (never recorded), a redirect (one leaf,
the nested open hidden beneath it), and a 404 (the raised error and
the status, the failing request last so the stream ends on it). Each
request is made beneath an observed function, so the leaf sits in a
tree whose identity travels to the server in the request headers.

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

import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-urllib --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-urllib-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, make the requests,
    print the live stream and the tree, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.external_urllib_request",
        description="Drive urllib against a local server with the"
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

    with wrapture.instrumentation("urllib.request"), wrapture.timeline() as tape:
        import urllib.error
        import urllib.request

        from tests.external_urllib_request.server import serve

        serving = serve()
        server = next(serving)

        @wrapture.observed
        def fetch(path: str, data: bytes | None = None) -> str:
            try:
                with urllib.request.urlopen(f"{server.url}{path}", data) as response:
                    return f"{response.status} {response.read()!r}"
            except urllib.error.HTTPError as error:
                return f"{error.code} {error.reason}"

        try:
            for path, data in (
                ("/ok", None),
                ("/echo", b"name=pat"),
                ("/ok?token=hunter2", None),
                ("/redirect", None),
                ("/missing", None),
            ):
                print(fetch(path, data))
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
        print(f"spans flushed to {endpoint} as service wrapture-urllib-demo")


if __name__ == "__main__":
    main()
