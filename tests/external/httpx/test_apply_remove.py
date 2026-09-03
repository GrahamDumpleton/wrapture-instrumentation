"""Applying and removing: the two patched names, sync and async, and
that removal leaves httpx as it was whatever the settings."""

from __future__ import annotations

import httpx
import pytest
from wrapture import instrumentation

from wrapture_instrumentation.external.httpx import HTTPXInstrumentation


def choke_points() -> tuple[object, object]:
    """The callables currently at the two patched names."""

    return (httpx.Client.send, httpx.AsyncClient.send)


def test_apply_then_remove_leaves_httpx_as_it_was() -> None:
    before = choke_points()

    with instrumentation(HTTPXInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("httpx",)
        assert choke_points()[0] is not before[0]
        assert choke_points()[1] is not before[1]

    assert choke_points() == before
    assert not instance.applied


@pytest.mark.parametrize("leaf", [True, False])
@pytest.mark.parametrize("propagate", [True, False])
def test_every_setting_combination_patches_the_same_names(
    leaf: bool, propagate: bool
) -> None:
    # The settings shape what the bindings do, never which names are
    # patched: there are two choke points whatever they say.

    before = choke_points()

    with instrumentation(HTTPXInstrumentation, leaf=leaf, propagate=propagate):
        assert choke_points()[0] is not before[0]
        assert choke_points()[1] is not before[1]

    assert choke_points() == before
