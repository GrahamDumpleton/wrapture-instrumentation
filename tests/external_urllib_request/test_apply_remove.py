"""Applying and removing: the one patched name, and that removal
leaves urllib as it was whatever the settings."""

from __future__ import annotations

import urllib.request

import pytest
from wrapture import instrumentation

from wrapture_instrumentation.external_urllib_request import UrllibInstrumentation


def choke_point() -> object:
    """The callable currently at the patched name."""

    return urllib.request.OpenerDirector.open


def test_apply_then_remove_leaves_urllib_as_it_was() -> None:
    before = choke_point()

    with instrumentation(UrllibInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("urllib.request",)
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

    with instrumentation(UrllibInstrumentation, leaf=leaf, propagate=propagate):
        assert choke_point() is not before

    assert choke_point() is before
