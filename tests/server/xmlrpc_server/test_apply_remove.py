"""Applying and removing: the patched names, and that removal leaves
xmlrpc.server as it was whatever the settings."""

from __future__ import annotations

import xmlrpc.server

import pytest
from wrapture import instrumentation

from wrapture_instrumentation.server.xmlrpc_server import XMLRPCServerInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "post": xmlrpc.server.SimpleXMLRPCRequestHandler.do_POST,
        "dispatch": xmlrpc.server.SimpleXMLRPCDispatcher._dispatch,
        "status": xmlrpc.server.SimpleXMLRPCRequestHandler.send_response,
    }


@pytest.mark.parametrize("join", [True, False])
def test_apply_then_remove_leaves_xmlrpc_server_as_it_was(join: bool) -> None:
    # The join setting is consulted per request, so the patched set is
    # the same either way.

    before = choke_points()

    with instrumentation(XMLRPCServerInstrumentation, join=join) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("xmlrpc.server",)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied
