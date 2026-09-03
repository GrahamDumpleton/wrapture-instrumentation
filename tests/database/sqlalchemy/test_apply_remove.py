"""Applying and removing: the patched names on the dialect and
connection classes, the overriding driver dialect covered once its
module is imported, and removal leaving everything as it was
whatever the settings."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy.engine.base import Connection
from sqlalchemy.engine.default import DefaultDialect
from wrapture import instrumentation, timeline

from wrapture_instrumentation.database.sqlalchemy import SQLAlchemyInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "do_execute": DefaultDialect.do_execute,
        "do_executemany": DefaultDialect.do_executemany,
        "do_execute_no_params": DefaultDialect.do_execute_no_params,
        "connect": DefaultDialect.connect,
        "commit": Connection._commit_impl,
        "rollback": Connection._rollback_impl,
        "psycopg2_executemany": PGDialect_psycopg2.do_executemany,
    }


@pytest.mark.parametrize(("leaf", "statement"), [(True, False), (False, True)])
def test_apply_then_remove_leaves_everything_as_it_was(
    leaf: bool, statement: bool
) -> None:
    # The settings shape the recorded data, not the patch, so the
    # patched set is the same either way. The psycopg2 dialect module
    # is imported by this file, so its hook fires alongside the
    # engine hooks.

    before = choke_points()

    with instrumentation(
        SQLAlchemyInstrumentation, leaf=leaf, statement=statement
    ) as record:
        (instance,) = record.instrumentations

        assert {
            "sqlalchemy.engine.default",
            "sqlalchemy.engine.base",
            "sqlalchemy.dialects.postgresql.psycopg2",
        } <= set(instance.applied)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied


def test_after_removal_an_existing_engine_runs_unrecorded() -> None:
    with instrumentation(SQLAlchemyInstrumentation):
        engine = create_engine("sqlite:///:memory:")

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    # The engine outlives the instrumentation: the class attributes
    # are restored, so it keeps working and records nothing.

    with timeline() as tape:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    engine.dispose()

    assert tape.all == []
