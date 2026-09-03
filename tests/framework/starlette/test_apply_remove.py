"""Applying and removing: the patched names, and that removal leaves
starlette as it was whatever the settings."""

from __future__ import annotations

import pytest
import starlette.applications
import starlette.routing
from wrapture import instrumentation

from wrapture_instrumentation.framework.starlette import StarletteInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "call": starlette.applications.Starlette.__call__,
        "init": starlette.routing.Route.__init__,
        "handle": starlette.routing.Route.handle,
    }


@pytest.mark.parametrize("ignore_paths", [[], ["/health"]])
def test_apply_then_remove_leaves_the_modules_as_they_were(
    ignore_paths: list[str],
) -> None:
    # The settings shape the middleware, not the patch, so the
    # patched set is the same either way.

    before = choke_points()

    with instrumentation(StarletteInstrumentation, ignore_paths=ignore_paths) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("starlette.applications", "starlette.routing")

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied
