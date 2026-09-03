"""Serve applications through an instrumented werkzeug development
server, driven by an instrumented urllib client, in one process.

Both instrumentations are resolved by their entry point names. Two
scenarios run over a loopback socket, the server in its own thread:

- A plain WSGI application: the client's external leaf and the
  server's request tree share one distributed trace id, carried by
  nothing but the traceparent header the client added.

- A Flask application, with the flask instrumentation applied as
  well, served by the same server class app.run() would start: the
  framework's own recording middleware sits inside the one the
  server interposes, and each request still records as one tree,
  annotated with the matched route, the view observed beneath it.

The live stream prints as it happens, then the trees reconstructed
with timings and the trace id per root, showing the joins. With
--otel the same events also export as OpenTelemetry spans to a local
OTLP endpoint (http://localhost:4318 unless
OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import urllib.request
from collections.abc import Iterable
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
            " demo through `just demo-werkzeug --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-werkzeug-demo"))


def quote_app(environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
    """A plain WSGI application: one path, one body."""

    start_response("200 OK", [("Content-Type", "text/plain")])

    return [b"widget: 42 coins"]


def serving(app: Any) -> tuple[Any, str, threading.Thread]:
    """Start the application on a loopback port in its own thread."""

    from werkzeug.serving import WSGIRequestHandler, make_server

    class Quiet(WSGIRequestHandler):
        def log(self, type: str, message: str, *args: Any) -> None:
            pass

    server = make_server("127.0.0.1", 0, app, request_handler=Quiet)
    url = f"http://127.0.0.1:{server.server_port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    return server, url, thread


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentations, serve and call the
    applications, print the live stream and the trees, and flush any
    exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.server_werkzeug",
        description="Serve applications through an instrumented werkzeug"
        " development server, driven by an instrumented urllib client,"
        " printing the live stream and the trees.",
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

    import flask

    print("==== plain WSGI application, client and server joined ====")
    with (
        wrapture.instrumentation("werkzeug.serving"),
        wrapture.instrumentation("urllib.request"),
    ):
        server, url, thread = serving(quote_app)
        try:
            with urllib.request.urlopen(f"{url}/quote?item=widget") as response:
                print(response.read().decode())
        finally:
            # werkzeug's serve_forever closes the server itself on
            # the serving thread; joining waits for that close.

            server.shutdown()
            thread.join()

    print("\n==== Flask application, one boundary per request ====")
    with (
        wrapture.instrumentation("werkzeug.serving"),
        wrapture.instrumentation("flask"),
    ):
        app = flask.Flask("shopfront")

        @app.route("/hello/<name>")
        def hello(name: str) -> str:
            return f"hi {name}"

        server, url, thread = serving(app)
        try:
            with urllib.request.urlopen(f"{url}/hello/pat") as response:
                print(response.read().decode())
        finally:
            # werkzeug's serve_forever closes the server itself on
            # the serving thread; joining waits for that close.

            server.shutdown()
            thread.join()

    wrapture.remove_sink(tape)

    print("\n==== trees ====")
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
        print("spans flushed to", endpoint, "as service wrapture-werkzeug-demo")


if __name__ == "__main__":
    main()
