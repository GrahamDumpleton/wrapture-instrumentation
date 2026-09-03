"""Both sides of an instrumented exchange in one process: an
instrumented httpx client driving an instrumented aiohttp server on
one event loop, sharing one distributed trace."""

from __future__ import annotations

import asyncio

import httpx
from aiohttp import web
from wrapture import Tape, instrumentation

from tests.server.aiohttp_web.shop import make_app
from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation


def test_client_and_server_share_one_trace(tape: Tape) -> None:
    # The client's external leaf propagates the identity in the
    # traceparent header, the server's boundary joins it: one trace
    # id across the two sides, carried by nothing but the header.

    with instrumentation(AiohttpWebInstrumentation), instrumentation("httpx"):
        app = make_app()

        async def main() -> int:
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()

            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()

            ((host, port), *_) = runner.addresses

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"http://{host}:{port}/quote/widget")

                return response.status_code
            finally:
                await runner.cleanup()

        assert asyncio.run(main()) == 200

    (call,) = [event for event in tape.all if event.category == "external"]
    (block,) = [event for event in tape.all if event.kind == "block"]

    assert call.trace is not None
    assert block.trace is not None
    assert block.trace.slots["w3c"].trace_id == call.trace.slots["w3c"].trace_id

    # The boundary saw the exchange the client made: same status on
    # both sides.

    assert call.data["status"] == 200
    assert block.data["status"] == 200
