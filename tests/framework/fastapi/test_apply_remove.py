"""Applying and removing: the patched names, and that removal leaves
fastapi as it was whatever the settings."""

from __future__ import annotations

import fastapi.applications
import fastapi.routing
import pytest
from wrapture import instrumentation

from wrapture_instrumentation.framework.fastapi import FastAPIInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "call": fastapi.applications.FastAPI.__call__,
        "init": fastapi.routing.APIRoute.__init__,
        "handle": fastapi.routing.APIRoute.handle,
    }


@pytest.mark.parametrize("ignore_paths", [[], ["/health"]])
def test_apply_then_remove_leaves_the_modules_as_they_were(
    ignore_paths: list[str],
) -> None:
    # The settings shape the middleware, not the patch, so the
    # patched set is the same either way.

    before = choke_points()

    with instrumentation(FastAPIInstrumentation, ignore_paths=ignore_paths) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("fastapi.applications", "fastapi.routing")

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied
