"""Applying and removing: the patched name, removal leaving
werkzeug.serving as it was, and the construction-time wrap's
documented lifetime either side of removal."""

from __future__ import annotations

import time
import urllib.request

import pytest
import werkzeug.serving
from wrapture import Tape, instrumentation

from tests.server.werkzeug_serving.conftest import hello_app, serve, settled
from wrapture_instrumentation.server.werkzeug_serving import (
    WerkzeugServingInstrumentation,
)


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {"init": werkzeug.serving.BaseWSGIServer.__init__}


@pytest.mark.parametrize("ignore_paths", [[], ["/health"]])
def test_apply_then_remove_leaves_the_module_as_it_was(
    ignore_paths: list[str],
) -> None:
    # The settings shape the middleware, not the patch, so the
    # patched set is the same either way.

    before = choke_points()

    with instrumentation(
        WerkzeugServingInstrumentation, ignore_paths=ignore_paths
    ) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("werkzeug.serving",)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied


def test_the_wrap_is_fixed_at_construction(tape: Tape) -> None:
    # The interposition happens as the server is built: a server built
    # while instrumented keeps its wrapper after removal, and one
    # built after removal was never wrapped at all.

    with instrumentation(WerkzeugServingInstrumentation):
        serving = serve(hello_app)
        url = next(serving)

    try:
        urllib.request.urlopen(url).close()
        settled(tape)
    finally:
        next(serving, None)

    serving = serve(hello_app)
    url = next(serving)
    try:
        urllib.request.urlopen(url).close()
        time.sleep(0.05)
    finally:
        next(serving, None)

    assert len([event for event in tape.all if event.kind == "request"]) == 1
