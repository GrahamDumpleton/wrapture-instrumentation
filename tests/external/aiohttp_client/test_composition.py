"""Both sides of an aiohttp exchange in one process: the instrumented
client driving the instrumented aiohttp.web server on one event loop,
sharing one distributed trace."""

from __future__ import annotations

import asyncio

from aiohttp import ClientSession, web
from wrapture import instrumentation, timeline

from wrapture_instrumentation.external.aiohttp_client import (
    AiohttpClientInstrumentation,
)
from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation


def test_client_and_server_share_one_trace() -> None:
    # The client's external leaf propagates the identity in the
    # traceparent header, the server's boundary joins it: one trace
    # id across the two sides, carried by nothing but the header.

    with (
        instrumentation(AiohttpClientInstrumentation),
        instrumentation(AiohttpWebInstrumentation),
        timeline() as tape,
    ):

        async def quoted(request: web.Request) -> web.Response:
            return web.Response(text="widget: 42")

        app = web.Application()
        app.router.add_get("/quote/{item}", quoted, name="quoted")

        async def main() -> int:
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()

            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()

            ((host, port), *_) = runner.addresses

            try:
                async with ClientSession() as session:
                    async with session.get(
                        f"http://{host}:{port}/quote/widget"
                    ) as response:
                        await response.read()

                        return response.status
            finally:
                await runner.cleanup()

        assert asyncio.run(main()) == 200

    (call,) = [event for event in tape.all if event.category == "external"]
    (block,) = [event for event in tape.all if event.kind == "block"]

    assert call.trace is not None
    assert block.trace is not None
    assert block.trace.slots["w3c"].trace_id == call.trace.slots["w3c"].trace_id

    # The boundary saw the exchange the client made: same status on
    # both sides, and the route it matched.

    assert call.data["status"] == 200
    assert block.data["status"] == 200
    assert block.data["route"] == "/quote/{item}"
