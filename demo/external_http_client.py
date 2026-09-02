"""Show the http.client wire layer: hidden beneath urllib.request's
leaf, revealed when that leaf is switched off, and standalone.

Three passes against a local server, each its own tree beneath an
observed root: the same redirect request with urllib.request at its
default (the wire layer silent beneath the leaf), again with
leaf = false (every phase of both exchanges visible), and a direct
http.client connection reused for two requests (the second exchange
shows no connect, the connection was kept alive).

Two views of the run always print: the live stream and the trees
reconstructed with timings. With --otel the same events also export
as OpenTelemetry spans to a local OTLP endpoint (http://localhost:4318
unless OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
import http.client
import os
import sys
import urllib.request

import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-http-client --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-http-client-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentations, drive the requests,
    print the live stream and the trees, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.external_http_client",
        description="Show the http.client wire layer hidden beneath a"
        " leaf, revealed with leaf = false, and standalone.",
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

    from tests.httpserver import serve

    serving = serve()
    server = next(serving)
    host = server.url.removeprefix("http://")

    trees: list[tuple[str, str]] = []

    def scenario(name: str, drive: object, leaf: bool | None) -> None:
        @wrapture.observed(label=name)
        def root() -> None:
            drive()  # type: ignore[operator]

        print(f"\n==== {name} ====")

        with wrapture.instrumentation("http.client"), wrapture.timeline() as tape:
            if leaf is None:
                root()
            else:
                with wrapture.instrumentation("urllib.request", leaf=leaf):
                    root()

        trees.append((name, tape.tree(times=True)))

    def via_urllib() -> None:
        urllib.request.urlopen(f"{server.url}/redirect").close()

    def direct_reused() -> None:
        connection = http.client.HTTPConnection(host)
        try:
            for path in ("/ok", "/ok"):
                connection.request("GET", path)
                connection.getresponse().read()
        finally:
            connection.close()

    try:
        scenario("beneath-the-leaf", via_urllib, leaf=True)
        scenario("leaf-switched-off", via_urllib, leaf=False)
        scenario("standalone-kept-alive", direct_reused, leaf=None)
    finally:
        next(serving, None)

    for name, tree in trees:
        print(f"\n==== tree: {name} ====")
        print(tree)

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print(f"spans flushed to {endpoint} as service wrapture-http-client-demo")


if __name__ == "__main__":
    main()
