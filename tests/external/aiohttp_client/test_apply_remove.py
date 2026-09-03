"""Applying and removing: the one patched name, and that removal
leaves aiohttp as it was whatever the settings."""

from __future__ import annotations

import aiohttp.client
import pytest
from wrapture import instrumentation

from wrapture_instrumentation.external.aiohttp_client import (
    AiohttpClientInstrumentation,
)


def choke_point() -> object:
    """The callable currently at the patched name."""

    return aiohttp.client.ClientSession._request


def test_apply_then_remove_leaves_aiohttp_as_it_was() -> None:
    before = choke_point()

    with instrumentation(AiohttpClientInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("aiohttp.client",)
        assert choke_point() is not before

    assert choke_point() is before
    assert not instance.applied


@pytest.mark.parametrize("leaf", [True, False])
@pytest.mark.parametrize("propagate", [True, False])
def test_every_setting_combination_patches_the_same_name(
    leaf: bool, propagate: bool
) -> None:
    # The settings shape what the binding does, never which name is
    # patched: there is one choke point whatever they say.

    before = choke_point()

    with instrumentation(AiohttpClientInstrumentation, leaf=leaf, propagate=propagate):
        assert choke_point() is not before

    assert choke_point() is before
