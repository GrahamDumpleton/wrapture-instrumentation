"""The request-shaping settings: ignore_paths silencing a request's
whole extent, and redact masking further query parameters."""

from __future__ import annotations

from wrapture import instrumentation, timeline

from tests.asgi import request
from tests.framework.starlette.shop import make_app
from wrapture_instrumentation.framework.starlette import StarletteInstrumentation


def test_ignore_paths_records_nothing_at_all() -> None:
    # tree=True on the middleware's filter: the ignored request
    # silences everything beneath it, the endpoint included, not just
    # its own event.

    with (
        instrumentation(StarletteInstrumentation, ignore_paths=["/pricing"]),
        timeline() as tape,
    ):
        app = make_app()
        request(app, "GET", "/pricing")
        request(app, "GET", "/quote/widget")

    requests = [event for event in tape.all if event.kind == "request"]
    assert [event.data["path"] for event in requests] == ["/quote/widget"]

    calls = [event for event in tape.all if event.kind == "call"]
    assert [event.label for event in calls] == ["quoted"]


def test_redact_masks_named_parameters() -> None:
    with (
        instrumentation(StarletteInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        request(make_app(), "GET", "/", query="voucher=SECRET99&page=3")

    (seen,) = [event for event in tape.all if event.kind == "request"]
    assert "voucher" in seen.data["query"]
    assert "page=3" in seen.data["query"]
    assert "SECRET99" not in repr(seen.data)
