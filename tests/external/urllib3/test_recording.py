"""What the instrumentation records: one external leaf per request
in every entry style, a redirect and a retry folded into it, error
statuses as statuses, and what stays out of capture."""

from __future__ import annotations

from importlib import metadata

import pytest
import urllib3
from wrapture import Event, Tape

from tests.httpserver import Server

MANAGER = "urllib3.poolmanager:PoolManager.urlopen"
POOL = "urllib3.connectionpool:HTTPConnectionPool.urlopen"

# The module-level urllib3.request helper is a 2.x feature; on 1.26
# the name is a submodule that raises when called.
URLLIB3_2 = int(metadata.version("urllib3").split(".", 1)[0]) >= 2


def leaves(tape: Tape) -> list[Event]:
    return [event for event in tape.all if event.category == "external"]


def host_port(server: Server) -> tuple[str, int]:
    authority = server.url.rpartition("/")[2]
    host, _, port = authority.rpartition(":")

    return host, int(port)


def test_a_manager_request_records_one_leaf(server: Server, tape: Tape) -> None:
    host, port = host_port(server)

    with urllib3.PoolManager() as manager:
        response = manager.request("GET", f"{server.url}/ok")

    assert response.status == 200

    (event,) = leaves(tape)
    assert event.path == MANAGER
    assert event.category == "external"
    assert event.data == {
        "method": "GET",
        "url": f"{server.url}/ok",
        "host": host,
        "port": port,
        "path": "/ok",
        "status": 200,
    }
    assert tape.children_of(event) == []


def test_a_bare_pool_request_records_one_leaf(server: Server, tape: Tape) -> None:
    host, port = host_port(server)

    with urllib3.HTTPConnectionPool(host, port) as pool:
        response = pool.urlopen("GET", "/ok")

    assert response.status == 200

    # The pool door recorded it, the relative path joined to what the
    # pool knows into the same absolute URL a manager would show.

    (event,) = leaves(tape)
    assert event.path == POOL
    assert event.data["url"] == f"{server.url}/ok"
    assert event.data["host"] == host
    assert event.data["port"] == port
    assert event.data["status"] == 200


@pytest.mark.skipif(not URLLIB3_2, reason="urllib3.request is a 2.x feature")
def test_the_module_level_request_records_one_leaf(server: Server, tape: Tape) -> None:
    response = urllib3.request("GET", f"{server.url}/ok")

    assert response.status == 200

    (event,) = leaves(tape)
    assert event.path == MANAGER
    assert event.data["status"] == 200


def test_a_redirect_is_one_leaf_with_the_final_status(
    server: Server, tape: Tape
) -> None:
    with urllib3.PoolManager() as manager:
        response = manager.request("GET", f"{server.url}/redirect")

    assert response.status == 200

    # The manager followed the redirect by recursing and delegating to
    # the pool; all of that is under the one leaf, which carries where
    # the request was asked for and the status it ended at.

    (event,) = leaves(tape)
    assert event.data["path"] == "/redirect"
    assert event.data["status"] == 200
    assert tape.children_of(event) == []


def test_an_error_status_is_a_status_not_an_exception(
    server: Server, tape: Tape
) -> None:
    with urllib3.PoolManager() as manager:
        response = manager.request("GET", f"{server.url}/missing")

    assert response.status == 404

    (event,) = leaves(tape)
    assert event.data["status"] == 404
    assert event.exception is None


def test_a_refused_connection_records_its_exception(tape: Tape) -> None:
    with pytest.raises(urllib3.exceptions.HTTPError):
        with urllib3.PoolManager() as manager:
            manager.request("GET", "http://127.0.0.1:1/ok", retries=False)

    (event,) = leaves(tape)
    assert event.exception is not None
    assert "status" not in event.data


def test_a_query_string_is_recorded_with_secrets_masked(
    server: Server, tape: Tape
) -> None:
    with urllib3.PoolManager() as manager:
        manager.request("GET", f"{server.url}/ok?user=pat&token=hunter2")

    (event,) = leaves(tape)
    assert event.data["query"] == "user=pat&token=<redacted>"

    # The URL in the data and the captured argument both drop the
    # query, so the secret is in one masked place only.

    assert "hunter2" not in event.data["url"]
    assert "hunter2" not in repr(event.arguments)


def test_the_body_is_never_recorded(server: Server, tape: Tape) -> None:
    with urllib3.PoolManager() as manager:
        manager.request("POST", f"{server.url}/echo", body=b"name=a-secret-value")

    (event,) = leaves(tape)
    assert event.data["method"] == "POST"
    assert "a-secret-value" not in repr(event.arguments)
    assert "a-secret-value" not in repr(event.data)


def test_leaf_off_shows_the_manager_over_the_pool(
    server: Server,
) -> None:
    from wrapture import instrumentation, timeline

    from wrapture_instrumentation.external.urllib3 import Urllib3Instrumentation

    with (
        instrumentation(Urllib3Instrumentation, leaf=False),
        timeline() as tape,
    ):
        with urllib3.PoolManager() as manager:
            manager.request("GET", f"{server.url}/ok")

    # With the leaf off, the manager's delegation to the pool nests
    # rather than being silenced: the manager leaf over its pool call.

    (manager_event,) = [e for e in tape.all if e.path == MANAGER]
    pool_events = [e for e in tape.all if e.path == POOL]

    assert pool_events
    assert all(tape.parent_of(pool) is manager_event for pool in pool_events)
