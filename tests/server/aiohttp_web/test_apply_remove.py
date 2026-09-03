"""Applying and removing: the patched names, that removal leaves
aiohttp as it was whatever the settings, where the observation lands
at registration, and what removal does and does not restore."""

from __future__ import annotations

import aiohttp.web_app
import aiohttp.web_urldispatcher
import pytest
import wrapture
from aiohttp import web
from wrapture import Tape, instrumentation

from tests.server.aiohttp_web import shop
from tests.server.aiohttp_web.conftest import drive
from tests.server.aiohttp_web.shop import make_app
from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation


def choke_points() -> dict[str, object]:
    """The callables currently at every patched name."""

    return {
        "handle": aiohttp.web_app.Application._handle,
        "route": aiohttp.web_urldispatcher.ResourceRoute.__init__,
    }


def index_route(app: web.Application) -> object:
    """The registered handler standing at the shop's index route."""

    for resource in app.router.resources():
        for route in resource:
            if route.method == "GET" and resource.canonical == "/":
                return route.handler

    raise AssertionError("the index route is not registered")


@pytest.mark.parametrize("redact", [[], ["voucher"]])
def test_apply_then_remove_leaves_the_module_as_it_was(redact: list[str]) -> None:
    # The settings shape the boundary, not the patch, so the patched
    # set is the same either way.

    before = choke_points()

    with instrumentation(AiohttpWebInstrumentation, redact=redact) as record:
        (instance,) = record.instrumentations

        assert instance.applied == ("aiohttp.web",)

        current = choke_points()
        for name in before:
            assert current[name] is not before[name], name

    current = choke_points()
    for name in before:
        assert current[name] is before[name], name

    assert not instance.applied


def test_the_observation_lands_on_the_registered_handler(
    instrumented: None,
) -> None:
    # Registration stores the observed proxy in the route, so every
    # dispatch calls it; the class-based view is left as the class.

    app = make_app()

    observed = index_route(app)
    assert isinstance(observed, wrapture.ObservedCallable)
    assert observed.__wrapped__ is shop.index

    for resource in app.router.resources():
        for route in resource:
            if resource.canonical == "/pages":
                assert route.handler is shop.Pages


def test_a_route_registered_after_removal_is_untouched() -> None:
    with instrumentation(AiohttpWebInstrumentation):
        pass

    app = make_app()

    assert index_route(app) is shop.index


def test_an_application_built_during_instrumentation_keeps_its_observations(
    tape: Tape,
) -> None:
    # Removal restores registration for routes added afterwards; a
    # route already registered keeps its observed handler, recording
    # only while sinks are active, and with the boundary gone the
    # handler records as a root of its own.

    with instrumentation(AiohttpWebInstrumentation):
        app = make_app()

    drive(app, "/")

    assert [event.kind for event in tape.all] == ["call"]
    (event,) = tape.all
    assert event.path == f"{shop.index.__module__}:index"
