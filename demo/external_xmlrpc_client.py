"""Drive xmlrpc.client against a local XML-RPC server with the
instrumentation applied.

The instrumentation is resolved by its entry point name, and the
calls go over a loopback socket to a SimpleXMLRPCServer started
after it applies. The calls cover the shapes that matter: a plain
call, a dotted method name, a MultiCall batch, a Fault (the failing
call recorded with status 200, since the fault came back in a parsed
response), and a ProtocolError from a wrong handler path. A second
pass switches leaf = false and enables the http.client
instrumentation, showing the transport and the wire phases beneath
one call.

Two views of the run always print: the live stream and the trees
reconstructed with timings, then the trace headers the server
received. With --otel the same events also export as OpenTelemetry
spans to a local OTLP endpoint (http://localhost:4318 unless
OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client

import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-xmlrpc --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-xmlrpc-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, make the calls, print
    the live stream and the trees, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.external_xmlrpc_client",
        description="Drive xmlrpc.client against a local server with the"
        " instrumentation applied, printing the live stream and the trees.",
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

    from tests.external_xmlrpc_client.server import serve

    serving = serve()
    server = next(serving)

    trees: list[tuple[str, str]] = []

    def calls(proxy: xmlrpc.client.ServerProxy) -> None:
        print(proxy.echo("hello"))
        print(proxy.inventory.count("widget", 3))

        batch = xmlrpc.client.MultiCall(proxy)
        batch.echo("first")
        batch.echo("second")
        results = batch()
        print([results[0], results[1]])

        try:
            proxy.boom()
        except xmlrpc.client.Fault as fault:
            print(f"Fault {fault.faultCode}")

        broken = xmlrpc.client.ServerProxy(f"{server.url}/nope")
        try:
            broken.echo("lost")
        except xmlrpc.client.ProtocolError as error:
            print(f"ProtocolError {error.errcode}")

    try:
        print("==== default: one leaf per call ====")
        with wrapture.instrumentation("xmlrpc.client"), wrapture.timeline() as tape:
            calls(xmlrpc.client.ServerProxy(server.url))
        trees.append(("one leaf per call", tape.tree(times=True)))

        print("\n==== leaf = false, with http.client beneath ====")
        with (
            wrapture.instrumentation("xmlrpc.client", leaf=False),
            wrapture.instrumentation("http.client"),
            wrapture.timeline() as tape,
        ):
            proxy = xmlrpc.client.ServerProxy(server.url)
            print(proxy.echo("beneath"))
        trees.append(("leaf = false, with http.client", tape.tree(times=True)))
    finally:
        next(serving, None)

    for name, tree in trees:
        print(f"\n==== tree: {name} ====")
        print(tree)

    print("\n==== headers the server received ====")
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
        print(f"spans flushed to {endpoint} as service wrapture-xmlrpc-demo")


if __name__ == "__main__":
    main()
