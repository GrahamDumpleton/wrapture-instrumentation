"""Fixtures for the httpx suite: the local server, and a tape hearing
the instrumentation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from tests.httpserver import Server, serve
from wrapture_instrumentation.external.httpx import HTTPXInstrumentation


@pytest.fixture
def server() -> Iterator[Server]:
    yield from serve()


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(HTTPXInstrumentation), timeline() as recorded:
        yield recorded
