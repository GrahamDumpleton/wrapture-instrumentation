"""Fixtures for the fastapi suite: a tape hearing the
instrumentation, requests driven in process through the ASGI test
driver."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation.framework.fastapi import FastAPIInstrumentation


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(FastAPIInstrumentation), timeline() as recorded:
        yield recorded
