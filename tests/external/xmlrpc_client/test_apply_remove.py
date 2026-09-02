"""Applying and removing: the patched names, and that removal leaves
xmlrpc.client as it was whatever the settings."""

from __future__ import annotations

import xmlrpc.client

import pytest
from wrapture import instrumentation

from wrapture_instrumentation.external.xmlrpc_client import XMLRPCClientInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    # The mangled name is spelled out, as the instrumentation spells
    # it; mypy does not model private-name access from outside.

    return {
        "call": xmlrpc.client.ServerProxy._ServerProxy__request,  # type: ignore[attr-defined]
        "transport": xmlrpc.client.Transport.request,
        "headers": xmlrpc.client.Transport.send_headers,
    }


def test_apply_then_remove_leaves_xmlrpc_client_as_it_was() -> None:
    before = choke_points()

    with instrumentation(XMLRPCClientInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("xmlrpc.client",)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied


@pytest.mark.parametrize("leaf", [True, False])
def test_propagate_off_leaves_send_headers_alone(leaf: bool) -> None:
    before = choke_points()

    with instrumentation(XMLRPCClientInstrumentation, leaf=leaf, propagate=False):
        current = choke_points()

        assert current["call"] is not before["call"]
        assert current["transport"] is not before["transport"]
        assert current["headers"] is before["headers"]

    assert choke_points() == before
