"""Serve an ASGI application through an instrumented uvicorn server,
driven by an instrumented httpx client, in one process.

Both instrumentations are resolved by their entry point names. The
application is a small ASGI callable served by uvicorn on a loopback
socket, the server on its own thread with its own event loop, and
the client drives it twice: the sync httpx client, then the async
one, each request beneath an observed function. The client's
external leaf and the server's request tree share one distributed
trace id, carried by nothing but the traceparent header the client
added.

The live stream prints as it happens, then the trees reconstructed
with timings and the trace id per root, showing the joins. With
--otel the same events also export as OpenTelemetry spans to a local
OTLP endpoint (http://localhost:4318 unless
OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time
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
            " demo through `just demo-uvicorn --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-uvicorn-demo"))


async def shop_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """A small ASGI application: a quote on one path, 404 elsewhere."""

    if scope["type"] != "http":
        return

    if scope["path"] == "/quote":
        status, body = 200, b"widget: 42 coins"
    else:
        status, body = 404, b"no such thing"

    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def serving(app: Any) -> tuple[Any, str, threading.Thread]:
    """Start the application under uvicorn on a loopback port in its
    own thread."""

    import uvicorn

    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="critical", lifespan="off"
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    while not server.started:
        time.sleep(0.001)

    (listener,) = server.servers
    (sock,) = listener.sockets
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"

    return server, url, thread


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentations, serve and call the
    application, print the live stream and the trees, and flush any
    exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.server_uvicorn",
        description="Serve an ASGI application through an instrumented"
        " uvicorn server, driven by an instrumented httpx client,"
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
    # scoped timeline: the server handles requests on its own thread's
    # event loop, and only an installed sink hears every thread.

    tape = wrapture.Tape()
    wrapture.add_sink(tape)

    print("==== ASGI application, client and server joined ====")
    with (
        wrapture.instrumentation("uvicorn"),
        wrapture.instrumentation("httpx"),
    ):
        import httpx

        server, url, thread = serving(shop_app)
        try:

            @wrapture.observed
            def fetch(path: str) -> str:
                response = httpx.get(f"{url}{path}")
                return f"{response.status_code} {response.text!r}"

            @wrapture.observed
            def fetch_async(path: str) -> str:
                async def go() -> str:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f"{url}{path}")
                        return f"{response.status_code} {response.text!r}"

                return asyncio.run(go())

            print(fetch("/quote?item=widget&token=hunter2"))
            print(fetch("/missing"))
            print(fetch_async("/quote"))
        finally:
            server.should_exit = True
            thread.join(timeout=5)

    # The server closes its request events on its own loop; give the
    # last one a moment to land before the tape is read.

    time.sleep(0.2)
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
        print("spans flushed to", endpoint, "as service wrapture-uvicorn-demo")


if __name__ == "__main__":
    main()
