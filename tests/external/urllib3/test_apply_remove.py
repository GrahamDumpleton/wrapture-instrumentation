"""Applying and removing: the patched urlopen on both doors, and
removal leaving them as they were whatever the settings."""

from __future__ import annotations

import urllib3
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.poolmanager import PoolManager
from wrapture import instrumentation, timeline

from tests.httpserver import Server
from wrapture_instrumentation.external.urllib3 import Urllib3Instrumentation


def choke_points() -> dict[str, object]:
    return {
        "manager": PoolManager.urlopen,
        "pool": HTTPConnectionPool.urlopen,
    }


def test_apply_then_remove_leaves_both_doors_as_they_were() -> None:
    before = choke_points()

    with instrumentation(Urllib3Instrumentation) as record:
        (instance,) = record.instrumentations

        assert instance.applied == (
            "urllib3.poolmanager",
            "urllib3.connectionpool",
        )

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name


def test_after_removal_requests_record_nothing(server: Server) -> None:
    with instrumentation(Urllib3Instrumentation):
        with urllib3.PoolManager() as manager:
            manager.request("GET", f"{server.url}/ok")

    with timeline() as tape:
        with urllib3.PoolManager() as manager:
            manager.request("GET", f"{server.url}/ok")

    assert tape.all == []
    assert server.header(1, "traceparent") is None
