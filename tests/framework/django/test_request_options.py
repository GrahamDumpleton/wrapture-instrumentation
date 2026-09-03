"""The request-shaping settings: ignore_paths silencing whole trees,
and redact masking named query parameters."""

from __future__ import annotations

from wrapture import instrumentation, timeline

from tests.framework.django.shop import make_wsgi_app
from tests.wsgi import request
from wrapture_instrumentation.framework.django import DjangoInstrumentation


def test_an_ignored_path_records_nothing_at_all() -> None:
    # tree=True on the middleware: the ignored request's view and its
    # template render are silenced with it, not recorded as orphans.

    with (
        instrumentation(DjangoInstrumentation, ignore_paths=["/pricelist/"]),
        timeline() as tape,
    ):
        response = request(make_wsgi_app(), "GET", "/pricelist/")

        assert response.status == "200 OK"
        assert tape.all == []

        # A request outside the ignore list still records.

        request(make_wsgi_app(), "GET", "/")

    assert [event.kind for event in tape.all] == ["request", "call"]


def test_redact_masks_the_named_parameters() -> None:
    with (
        instrumentation(DjangoInstrumentation, redact=["voucher"]),
        timeline() as tape,
    ):
        request(make_wsgi_app(), "GET", "/", query="voucher=abc123&limit=5")

    (seen, _) = tape.all
    assert seen.data["query"] == "voucher=<redacted>&limit=5"
