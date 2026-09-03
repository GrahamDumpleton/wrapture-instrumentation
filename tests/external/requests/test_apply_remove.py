"""Applying and removing: the one patched name, and that removal
leaves requests as it was whatever the settings."""

from __future__ import annotations

import pytest
import requests.sessions
from wrapture import instrumentation

from wrapture_instrumentation.external.requests import RequestsInstrumentation


def choke_point() -> object:
    """The callable currently at the patched name."""

    return requests.sessions.Session.send


def test_apply_then_remove_leaves_requests_as_it_was() -> None:
    before = choke_point()

    with instrumentation(RequestsInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("requests.sessions",)
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

    with instrumentation(RequestsInstrumentation, leaf=leaf, propagate=propagate):
        assert choke_point() is not before

    assert choke_point() is before
