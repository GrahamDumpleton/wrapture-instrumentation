"""Fixtures for the sqlalchemy suite: the instrumentation applied and
a scoped tape. Everything runs in process against in-memory SQLite,
so no installed sink or server is needed.

SQLAlchemy itself is imported only inside the test modules, each of
which skips itself when it is not installed (the free threaded 3.13
build cannot install greenlet, which sqlalchemy pulls in).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation.database.sqlalchemy import SQLAlchemyInstrumentation


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(SQLAlchemyInstrumentation), timeline() as recorded:
        yield recorded
