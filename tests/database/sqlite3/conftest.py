"""Fixtures for the sqlite3 suite: the instrumentation applied and a
scoped tape. Everything runs in process, so no installed sink is
needed."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation.database.sqlite3 import SQLite3Instrumentation


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(SQLite3Instrumentation), timeline() as recorded:
        yield recorded
