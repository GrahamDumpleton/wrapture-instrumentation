"""The pairing with a higher-level client: silent beneath its leaf,
the whole story when the leaf is switched off."""

from __future__ import annotations

import urllib.request

from wrapture import Tape, instrumentation, timeline

from tests.httpserver import Server
from wrapture_instrumentation.external.http_client import HTTPClientInstrumentation

OPEN = "urllib.request:OpenerDirector.open"


def recorded_with(server: Server, leaf: bool) -> Tape:
    """One redirect request with both instrumentations applied, the
    urllib.request one with the given leaf setting."""

    with (
        instrumentation(HTTPClientInstrumentation),
        instrumentation("urllib.request", leaf=leaf),
        timeline() as tape,
    ):
        urllib.request.urlopen(f"{server.url}/redirect").close()

    return tape


def test_beneath_the_default_leaf_the_wire_layer_is_silent(server: Server) -> None:
    tape = recorded_with(server, leaf=True)

    assert [event.path for event in tape.all] == [OPEN]


def test_leaf_off_shows_every_phase_of_both_exchanges(server: Server) -> None:
    tape = recorded_with(server, leaf=False)

    (outer,) = tape.roots()
    assert outer.path == OPEN

    # The redirect is a nested open, and each open shows its own
    # phases. urllib builds a fresh connection per open, so both
    # exchanges show a connect: exactly the kind of fact this layer
    # exists to make visible.

    paths = [event.path for event in tape.all]
    assert paths.count(OPEN) == 2
    assert paths.count("http.client:HTTPConnection.getresponse") == 2
    assert paths.count("http.client:HTTPConnection.connect") == 2
