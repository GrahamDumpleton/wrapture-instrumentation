"""Lifecycle callbacks and error handlers: what the portal records
beneath its requests, and how handled and unhandled failures differ.

The live instance is reached through wrapture.instrumentation(), with
a timeline tape hearing what the bindings observe; requests are
driven through the WSGI test driver.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from wrapture import Config, InstrumentEntry, Tape, instrumentation, timeline

from tests.framework_flask.portal import make_portal
from tests.wsgi import request
from wrapture_instrumentation.framework_flask import FlaskInstrumentation

PORTAL = "tests.framework_flask.portal"


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(FlaskInstrumentation), timeline() as recorded:
        yield recorded


def labels(tape: Tape) -> list[str]:
    """The recorded call events' labels or paths, in order."""

    return [event.label or event.path for event in tape.all if event.kind == "call"]


def test_lifecycle_callbacks_record_in_request_order(tape: Tape) -> None:
    response = request(make_portal(), "GET", "/")

    assert response.status == "200 OK"
    assert ("X-Portal", "stamped") in (response.headers or [])

    # The whole request lifecycle, in the order Flask runs it: the
    # app-level and blueprint app-level before functions, the view,
    # the after function, then the two teardowns as the request and
    # application contexts unwind, every one nested under the request.

    assert labels(tape) == [
        f"{PORTAL}.audit_request",
        f"{PORTAL}.every_request",
        "index",
        f"{PORTAL}.stamp_response",
        f"{PORTAL}.request_done",
        f"{PORTAL}.context_done",
    ]

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert all(
        tape.parent_of(event) is seen for event in tape.all if event.kind == "call"
    )


def test_blueprint_local_callbacks_run_only_for_their_routes(tape: Tape) -> None:
    app = make_portal()

    request(app, "GET", "/admin/panel")
    admin_calls = labels(tape)

    # The blueprint-local before_request records for the admin route,
    # between the app-level befores and the view.

    assert f"{PORTAL}.only_admin_routes" in admin_calls
    assert admin_calls.index(f"{PORTAL}.only_admin_routes") < admin_calls.index(
        "admin.panel"
    )


def test_a_handled_exception_is_noted_and_its_handler_observed(tape: Tape) -> None:
    response = request(make_portal(), "GET", "/shaky")

    # The registered ValueError handler absorbed the failure and
    # answered 422: the request completes, the handler's run records
    # as a call, and the exception is noted against the request so
    # the absorbed failure still leaves its mark.

    assert response.status == "422 UNPROCESSABLE ENTITY"

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert [type(caught.exception) for caught in seen.caught] == [ValueError]

    assert f"{PORTAL}.shaky_handler" in labels(tape)


def test_an_http_exception_is_control_flow_and_not_noted(tape: Tape) -> None:
    response = request(make_portal(), "GET", "/nowhere")

    # The 404 handler runs and is observed, but an HTTPException is
    # the response taking shape, not a failure: nothing is noted.

    assert response.status == "404 NOT FOUND"

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert seen.caught == ()

    assert f"{PORTAL}.missing_handler" in labels(tape)


def test_an_unhandled_exception_is_noted_exactly_once(tape: Tape) -> None:
    response = request(make_portal(), "GET", "/broken")

    # No handler claims the KeyError: handle_user_exception re-raises
    # it, handle_exception answers 500 and notes it. One note, not
    # one per handler the exception passed through.

    assert response.status == "500 INTERNAL SERVER ERROR"

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert [type(caught.exception) for caught in seen.caught] == [KeyError]


def test_registrations_after_removal_are_plain() -> None:
    from wrapture import ObservedCallable

    with instrumentation(FlaskInstrumentation):
        during = make_portal()

    after = make_portal()

    # Callbacks registered while applied stay observed on the
    # application that holds them; an application built after removal
    # registers plain functions.

    assert isinstance(during.before_request_funcs[None][0], ObservedCallable)
    assert not any(
        isinstance(f, ObservedCallable) for f in after.before_request_funcs[None]
    )


def test_lifecycle_off_quietens_the_callbacks() -> None:
    # With the lifecycle switch off only the core layers record: the
    # request and its view, no before/after/teardown events, however
    # many callbacks the application registered.

    with instrumentation(FlaskInstrumentation, lifecycle=False), timeline() as tape:
        response = request(make_portal(), "GET", "/")

        assert response.status == "200 OK"
        assert labels(tape) == ["index"]

        # The response still passed through the registered callbacks;
        # they ran unobserved rather than not at all.

        assert ("X-Portal", "stamped") in (response.headers or [])


def test_lifecycle_off_keeps_error_handler_observation() -> None:
    # Error handler observation is core, not lifecycle: a handled
    # failure still shows its handler and its note with the switch
    # off.

    with instrumentation(FlaskInstrumentation, lifecycle=False), timeline() as tape:
        response = request(make_portal(), "GET", "/shaky")

        assert response.status == "422 UNPROCESSABLE ENTITY"
        assert labels(tape) == ["shaky", f"{PORTAL}.shaky_handler"]

        (seen,) = [event for event in tape.all if event.kind == "request"]
        assert [type(caught.exception) for caught in seen.caught] == [ValueError]


def test_handled_errors_off_skips_the_note_but_not_the_handler() -> None:
    # With handled_errors off an absorbed exception leaves no note on
    # the request; the handler itself is still observed, and an
    # unhandled exception is still noted by the 500 path.

    with (
        instrumentation(FlaskInstrumentation, handled_errors=False),
        timeline() as tape,
    ):
        app = make_portal()

        response = request(app, "GET", "/shaky")
        assert response.status == "422 UNPROCESSABLE ENTITY"

        (seen, *_) = [event for event in tape.all if event.kind == "request"]
        assert seen.caught == ()
        assert f"{PORTAL}.shaky_handler" in labels(tape)

        response = request(app, "GET", "/broken")
        assert response.status == "500 INTERNAL SERVER ERROR"

        (_, broken) = [event for event in tape.all if event.kind == "request"]
        assert [type(caught.exception) for caught in broken.caught] == [KeyError]


def test_a_config_entry_carries_the_settings() -> None:
    # The TOML route: an [[instrument]] entry's extra keys are the
    # settings, so `lifecycle = false` in a config file quietens the
    # callbacks exactly as the keyword form does.

    applied = Config(
        instrument=[InstrumentEntry("flask", settings={"lifecycle": False})]
    ).apply()
    try:
        with timeline() as tape:
            response = request(make_portal(), "GET", "/")

        assert response.status == "200 OK"
        assert labels(tape) == ["index"]
    finally:
        applied.revert()
