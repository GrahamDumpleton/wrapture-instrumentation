"""Fixtures for the xmlrpc.client suite: the local server, and a tape
hearing the instrumentation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from tests.xmlrpcserver import Server, serve
from wrapture_instrumentation.external.xmlrpc_client import XMLRPCClientInstrumentation


@pytest.fixture
def server() -> Iterator[Server]:
    yield from serve()


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(XMLRPCClientInstrumentation), timeline() as recorded:
        yield recorded
