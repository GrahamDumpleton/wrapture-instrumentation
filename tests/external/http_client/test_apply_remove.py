"""Applying and removing: the patched names on HTTPConnection, and
that removal leaves http.client as it was."""

from __future__ import annotations

import http.client

from wrapture import instrumentation

from wrapture_instrumentation.external.http_client import HTTPClientInstrumentation

NAMES = ("connect", "putrequest", "endheaders", "getresponse")


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {name: getattr(http.client.HTTPConnection, name) for name in NAMES}


def test_apply_then_remove_leaves_http_client_as_it_was() -> None:
    before = choke_points()

    with instrumentation(HTTPClientInstrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("http.client",)

        current = choke_points()
        for name in NAMES:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in NAMES:
        assert current[name] is before[name], name

    assert not instance.applied


def test_request_and_putheader_are_deliberately_not_patched() -> None:
    # request() would double with the phases beneath it and is
    # overridden by urllib3-style subclasses; putheader carries
    # header values, which are never recorded.

    before_request = http.client.HTTPConnection.request
    before_putheader = http.client.HTTPConnection.putheader

    with instrumentation(HTTPClientInstrumentation):
        assert http.client.HTTPConnection.request is before_request
        assert http.client.HTTPConnection.putheader is before_putheader
