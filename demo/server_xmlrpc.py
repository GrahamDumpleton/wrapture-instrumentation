"""Drive an instrumented SimpleXMLRPCServer with an instrumented
xmlrpc.client, showing both sides of each call in one process.

Both instrumentations are resolved by their entry point names. The
server runs on a loopback socket in its own thread, so its events
record in that thread while the client's record in this one: two
trees per call, an external leaf on the client side and a request
boundary with its dispatch events on the server side, sharing one
distributed trace id carried by nothing but the traceparent header.
The calls cover a plain call, a dotted method name, a MultiCall
batch (one boundary, the sub-calls nested inside the batch's
dispatch), a Fault (a failed procedure inside a 200 response), and a
wrong handler path answered 404 with nothing dispatched.

The live stream prints as it happens, then the trees reconstructed
with timings, grouped by trace id to show the join. With --otel the
same events also export as OpenTelemetry spans to a local OTLP
endpoint (http://localhost:4318 unless OTEL_EXPORTER_OTLP_ENDPOINT
says otherwise).
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
            " demo through `just demo-xmlrpc-server --otel`, which"
            " overlays wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-xmlrpc-server-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply both instrumentations, make the calls, print
    the live stream and the trees, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.server_xmlrpc",
        description="Drive an instrumented SimpleXMLRPCServer with an"
        " instrumented xmlrpc.client, printing the live stream and the"
        " trees of both sides.",
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

    # The tape is added as a process-wide sink rather than opened as a
    # scoped timeline: the server handles requests in its own thread,
    # and only an installed sink hears every thread.

    tape = wrapture.Tape()
    wrapture.add_sink(tape)

    from tests.xmlrpcserver import serve

    with (
        wrapture.instrumentation("xmlrpc.server"),
        wrapture.instrumentation("xmlrpc.client"),
    ):
        serving = serve()
        server = next(serving)
        try:
            proxy = xmlrpc.client.ServerProxy(server.url)
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
        finally:
            next(serving, None)

    wrapture.remove_sink(tape)

    print("\n==== trees, grouped by trace id ====")
    print(tape.tree(times=True))

    print("==== the join: trace id per root ====")
    for root in tape.roots():
        slot = root.trace.slots["w3c"] if root.trace else None
        side = "client" if root.category == "external" else "server"
        name = root.label or root.path
        print(f"{side:>6}  {name:<50} {slot.trace_id if slot else '(none)'}")

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print("spans flushed to", endpoint, "as service wrapture-xmlrpc-server-demo")


if __name__ == "__main__":
    main()
