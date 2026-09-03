"""Every view shape the instrumentation must handle: plain functions,
a class-based view, an async view, views that query and populate the
database, a rendering view, a streaming response, a raising view and
an Http404."""

from __future__ import annotations

from collections.abc import Iterator

from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views import View

from tests.framework.django.shop.models import Item

PRICES = {"widget": 42, "gadget": 7}


def index(request: HttpRequest) -> HttpResponse:
    return HttpResponse("shop")


def about(request: HttpRequest) -> HttpResponse:
    # Registered without a URL name: the observed view keeps its
    # derived path as its identity.

    return HttpResponse("about the shop")


def quoted(request: HttpRequest, item: str) -> HttpResponse:
    # An unknown item raises KeyError: the unhandled-exception case.

    return HttpResponse(f"{item}: {PRICES[item]} coins")


def year_archive(request: HttpRequest, year: int) -> HttpResponse:
    return HttpResponse(f"archive {year}")


class Catalog(View):
    """The class-based view: one call event for the whole view."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("catalog")


async def motd(request: HttpRequest) -> HttpResponse:
    return HttpResponse("welcome")


def stocked(request: HttpRequest) -> HttpResponse:
    count = Item.objects.count()

    return HttpResponse(f"{count} items stocked")


def restock(request: HttpRequest) -> HttpResponse:
    with transaction.atomic():
        Item.objects.create(name="widget", price=42)

    return HttpResponse("restocked")


def pricelist(request: HttpRequest) -> HttpResponse:
    person = request.GET.get("person", "pat")

    return render(request, "page.html", {"person": person})


def export(request: HttpRequest) -> StreamingHttpResponse:
    def rows() -> Iterator[bytes]:
        yield b"row1\n"
        yield b"row2\n"

    return StreamingHttpResponse(rows())


def missing(request: HttpRequest) -> HttpResponse:
    raise Http404("nothing here")
