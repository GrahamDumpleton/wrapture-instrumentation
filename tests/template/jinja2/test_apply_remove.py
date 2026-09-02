"""Applying and removing: the patched names across the two classes,
and that removal leaves Jinja2 as it was."""

from __future__ import annotations

import jinja2.environment
from wrapture import instrumentation

from wrapture_instrumentation.template.jinja2 import Jinja2Instrumentation

CHOKE_POINTS: tuple[tuple[type, str], ...] = (
    (jinja2.environment.Template, "render"),
    (jinja2.environment.Template, "render_async"),
    (jinja2.environment.Template, "generate"),
    (jinja2.environment.Template, "generate_async"),
    (jinja2.environment.Environment, "compile"),
    (jinja2.environment.Environment, "_load_template"),
)


def choke_points() -> dict[tuple[type, str], object]:
    """The callables currently at every patched name."""

    return {(cls, name): getattr(cls, name) for cls, name in CHOKE_POINTS}


def same(
    first: dict[tuple[type, str], object], second: dict[tuple[type, str], object]
) -> bool:
    # wrapt's wrappers compare equal to what they wrap, so restoration
    # is a question of identity, name by name.

    return all(first[key] is second[key] for key in first)


def test_apply_then_remove_leaves_jinja2_as_it_was() -> None:
    before = choke_points()

    with instrumentation(Jinja2Instrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("jinja2.environment",)
        assert not same(choke_points(), before)

    assert same(choke_points(), before)
    assert not instance.applied


def test_loading_off_patches_the_renders_alone() -> None:
    before = choke_points()

    with instrumentation(Jinja2Instrumentation, loading=False):
        current = choke_points()

        # The four renders are wrapped; the loading pipeline is not.

        for cls, name in CHOKE_POINTS:
            changed = current[(cls, name)] is not before[(cls, name)]
            assert changed == (cls is jinja2.environment.Template), name

    assert same(choke_points(), before)
