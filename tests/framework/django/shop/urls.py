"""The urlconf: named patterns (one with an int converter, proving
the route annotation carries the pattern rather than the path), an
unnamed pattern, and every view shape."""

from __future__ import annotations

from django.urls import path

from tests.framework.django.shop import views

urlpatterns = [
    path("", views.index, name="index"),
    path("about/", views.about),
    path("quote/<str:item>/", views.quoted, name="quoted"),
    path("archive/<int:year>/", views.year_archive, name="year_archive"),
    path("catalog/", views.Catalog.as_view(), name="catalog"),
    path("motd/", views.motd, name="motd"),
    path("stocked/", views.stocked, name="stocked"),
    path("restock/", views.restock, name="restock"),
    path("pricelist/", views.pricelist, name="pricelist"),
    path("export/", views.export, name="export"),
    path("missing/", views.missing, name="missing"),
]
