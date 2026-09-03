"""Fixtures for the starlette suite: a tape hearing the
instrumentation, requests driven in process through the ASGI test
driver."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation.framework.starlette import StarletteInstrumentation


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(StarletteInstrumentation), timeline() as recorded:
        yield recorded
