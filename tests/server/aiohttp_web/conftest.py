"""Fixtures and helpers for the aiohttp.web suite: the
instrumentation applied, a scoped tape, and requests driven against
a real aiohttp server on a loopback port, everything on one event
loop so the scoped timeline hears the server's side too."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import NamedTuple

import pytest
from aiohttp import ClientSession, web
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation


@pytest.fixture
def instrumented() -> Iterator[None]:
    with instrumentation(AiohttpWebInstrumentation):
        yield


@pytest.fixture
def tape() -> Iterator[Tape]:
    with timeline() as recorded:
        yield recorded


class Fetched(NamedTuple):
    """One driven request's outcome as the client saw it."""

    status: int
    text: str


def drive(
    app: web.Application,
    *requests: str | tuple[str, dict[str, str]],
) -> list[Fetched]:
    """Serve the application on a loopback port and make the given
    GET requests in order, each a path or a (path, headers) pair,
    returning what the client saw.

    Server and client share the test's one event loop, so everything
    the server records lands in the caller's recording scope, and
    every boundary has closed by the time this returns.
    """

    async def main() -> list[Fetched]:
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()

        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()

        ((host, port), *_) = runner.addresses
        base = f"http://{host}:{port}"

        try:
            results: list[Fetched] = []

            async with ClientSession() as session:
                for entry in requests:
                    path, headers = entry if isinstance(entry, tuple) else (entry, None)

                    async with session.get(base + path, headers=headers) as response:
                        results.append(Fetched(response.status, await response.text()))

            return results
        finally:
            await runner.cleanup()

    return asyncio.run(main())
