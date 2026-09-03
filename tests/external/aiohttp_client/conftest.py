"""Fixtures for the aiohttp client suite: the local server, a tape
hearing the instrumentation, and a helper driving the async client
against the server on the test's own event loop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from wrapture import Tape, instrumentation, timeline

from tests.httpserver import Server, serve
from wrapture_instrumentation.external.aiohttp_client import (
    AiohttpClientInstrumentation,
)


@pytest.fixture
def server() -> Iterator[Server]:
    yield from serve()


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(AiohttpClientInstrumentation), timeline() as recorded:
        yield recorded


def run[T](coroutine: Callable[[Any], Awaitable[T]]) -> T:
    """Run one coroutine factory under asyncio, opening a ClientSession
    and handing it in, so a test reads as one request against the
    server.

    The client runs on the current thread's event loop, inside the
    active recording scope, so what it records lands on the tape and
    every request has closed by the time this returns.
    """

    import asyncio

    from aiohttp import ClientSession

    async def main() -> T:
        async with ClientSession() as session:
            return await coroutine(session)

    return asyncio.run(main())
