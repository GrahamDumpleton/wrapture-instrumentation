"""Fixtures for the urllib suite: the local server, and a tape hearing
the instrumentation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from tests.external_urllib.server import Server, serve
from wrapture_instrumentation.external_urllib import UrllibInstrumentation


@pytest.fixture
def server() -> Iterator[Server]:
    yield from serve()


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(UrllibInstrumentation), timeline() as recorded:
        yield recorded
