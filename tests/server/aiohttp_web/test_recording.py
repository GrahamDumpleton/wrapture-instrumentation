"""What the instrumentation records: one request boundary per
request with the route and status annotated, the observed handler
beneath it, statuses for HTTPExceptions, failures, redaction, and
what a class-based view leaves out."""

from __future__ import annotations

from wrapture import Event, Tape, instrumentation

from tests.server.aiohttp_web.conftest import drive
from tests.server.aiohttp_web.shop import make_app
from wrapture_instrumentation.server.aiohttp_web import AiohttpWebInstrumentation

SHOP = "tests.server.aiohttp_web.shop"


def boundary(events: list[Event]) -> Event:
    """The one request boundary among the events."""

    (event,) = [event for event in events if event.kind == "block"]

    return event


def test_a_request_records_one_boundary_with_the_handler_beneath(
    instrumented: None, tape: Tape
) -> None:
    (fetched,) = drive(make_app(), "/quote/widget")

    assert fetched.status == 200
    assert fetched.text == "widget: 42"

    block = boundary(tape.all)
    assert block.label == "aiohttp.web"
    assert block.category == "server"
    assert block.exception is None
    assert block.data["method"] == "GET"
    assert block.data["path"] == "/quote/widget"
    assert block.data["scheme"] == "http"
    assert block.data["remote"] == "127.0.0.1"
    assert block.data["route"] == "/quote/{item}"
    assert block.data["endpoint"] == "quoted"
    assert block.data["status"] == 200

    # The handler, observed as its route was registered, records
    # beneath the boundary, labelled by the route's name.

    (handler,) = tape.children_of(block)
    assert handler.kind == "call"
    assert handler.label == "quoted"
    assert handler.path == f"{SHOP}:quoted"
    assert tape.parent_of(handler) is block


def test_the_query_is_recorded_with_secrets_masked(
    instrumented: None, tape: Tape
) -> None:
    drive(make_app(), "/?token=hunter2&item=widget")

    block = boundary(tape.all)
    assert "item=widget" in block.data["query"]
    assert "hunter2" not in repr(block.data)


def test_redact_masks_named_parameters(tape: Tape) -> None:
    with instrumentation(AiohttpWebInstrumentation, redact=["voucher"]):
        drive(make_app(), "/?voucher=SECRET99")

    block = boundary(tape.all)
    assert "voucher" in block.data["query"]
    assert "SECRET99" not in repr(block.data)


def test_ignore_paths_records_nothing_at_all(tape: Tape) -> None:
    # An ignored request is declined at the boundary with its whole
    # extent silenced, so the observed handler vanishes with it
    # rather than surfacing as a root of its own.

    with instrumentation(AiohttpWebInstrumentation, ignore_paths=["/quote/*"]):
        drive(make_app(), "/quote/widget", "/")

    assert [event.kind for event in tape.all] == ["block", "call"]

    block = boundary(tape.all)
    assert block.data["path"] == "/"

    (handler,) = tape.children_of(block)
    assert handler.path == f"{SHOP}:index"


def test_an_http_exception_is_a_status_not_a_failure(
    instrumented: None, tape: Tape
) -> None:
    # Raising HTTPNotFound is aiohttp's way of answering 404: control
    # flow that carries a status, so the boundary records the status
    # and no exception. The handler's own event carries what the
    # handler did, which was raise.

    (fetched,) = drive(make_app(), "/gone")

    assert fetched.status == 404

    block = boundary(tape.all)
    assert block.exception is None
    assert block.data["status"] == 404
    assert block.data["route"] == "/gone"

    (handler,) = tape.children_of(block)
    assert type(handler.exception).__name__ == "HTTPNotFound"


def test_a_failing_handler_records_the_exception(
    instrumented: None, tape: Tape
) -> None:
    # The handler raised something that is not an HTTPException; the
    # protocol answers 500 on its own, and the boundary records the
    # failure and no status, since the response was never its to see.

    (fetched,) = drive(make_app(), "/quote/nothing")

    assert fetched.status == 500

    block = boundary(tape.all)
    assert isinstance(block.exception, KeyError)
    assert "status" not in block.data
    assert block.data["route"] == "/quote/{item}"

    (handler,) = tape.children_of(block)
    assert isinstance(handler.exception, KeyError)


def test_an_unmatched_path_has_no_route_keys(instrumented: None, tape: Tape) -> None:
    (fetched,) = drive(make_app(), "/nowhere")

    assert fetched.status == 404

    block = boundary(tape.all)
    assert block.exception is None
    assert block.data["status"] == 404
    assert block.data["path"] == "/nowhere"
    assert "route" not in block.data
    assert "endpoint" not in block.data
    assert tape.children_of(block) == []


def test_a_sub_application_route_carries_the_full_pattern(
    instrumented: None, tape: Tape
) -> None:
    # A sub-application's request is resolved through the root's
    # dispatch: one boundary, the canonical pattern with the prefix
    # folded in, and the handler beneath it.

    (fetched,) = drive(make_app(), "/reports/summary")

    assert fetched.status == 200

    block = boundary(tape.all)
    assert block.data["route"] == "/reports/summary"
    assert block.data["endpoint"] == "summary"

    (handler,) = tape.children_of(block)
    assert handler.path == f"{SHOP}:summary"


def test_a_class_based_view_annotates_without_an_observation(
    instrumented: None, tape: Tape
) -> None:
    # A web.View registers as the class itself, which the observation
    # leaves alone: the boundary still annotates the route and the
    # class's name, with nothing recorded beneath it.

    (fetched,) = drive(make_app(), "/pages")

    assert fetched.status == 200

    block = boundary(tape.all)
    assert block.data["route"] == "/pages"
    assert block.data["endpoint"] == "Pages"
    assert block.data["status"] == 200
    assert tape.children_of(block) == []
