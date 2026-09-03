"""Drive an instrumented gRPC server with an instrumented gRPC
client, showing both sides of each RPC in one process.

The one instrumentation is resolved by its entry point name and
covers both halves. The server runs on a loopback socket handling
RPCs on its executor threads, so its boundaries record there while
the client's leaves record in this one: two trees per RPC, an
external leaf on the client side and a request boundary on the
server side, sharing one distributed trace id carried by nothing
but the metadata. The calls cover a plain unary call, a streamed
response consumed in full, a streamed request, an abort (its code
recorded, the boundary clean) and a handler failure (the boundary
carrying the exception beside its UNKNOWN).

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

import grpc
import wrapture


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-grpc --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-grpc-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, make the calls, print
    the live stream and the trees, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.rpc_grpc",
        description="Drive an instrumented gRPC server with an"
        " instrumented client, printing the live stream and the trees"
        " of both sides.",
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
    # scoped timeline: the server handles RPCs on its executor
    # threads, and only an installed sink hears every thread.

    tape = wrapture.Tape()
    wrapture.add_sink(tape)

    from tests.rpc.grpc.service import serve

    with wrapture.instrumentation("grpc"):
        serving = serve()
        service = next(serving)
        try:
            channel = grpc.insecure_channel(service.address)

            print(channel.unary_unary("/demo.Echo/Shout")(b"hello"))
            print(list(channel.unary_stream("/demo.Echo/Count")(b"chunk")))
            print(channel.stream_unary("/demo.Echo/Sum")(iter([b"1", b"2", b"3"])))

            try:
                channel.unary_unary("/demo.Echo/Fail")(b"hello")
            except grpc.RpcError as error:
                print(f"RpcError {error.code().name}")

            try:
                channel.unary_unary("/demo.Echo/Boom")(b"hello")
            except grpc.RpcError as error:
                print(f"RpcError {error.code().name}")

            channel.close()
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
        print(f"{side:>6}  {name:<40} {slot.trace_id if slot else '(none)'}")

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print("spans flushed to", endpoint, "as service wrapture-grpc-demo")


if __name__ == "__main__":
    main()
