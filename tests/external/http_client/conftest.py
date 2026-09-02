"""Fixtures for the http.client suite: the local server, and a tape
hearing the instrumentation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from tests.httpserver import Server, serve
from wrapture_instrumentation.external.http_client import HTTPClientInstrumentation


@pytest.fixture
def server() -> Iterator[Server]:
    yield from serve()


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(HTTPClientInstrumentation), timeline() as recorded:
        yield recorded


def host_of(server: Server) -> str:
    """The host:port a connection is opened to."""

    return server.url.removeprefix("http://")
