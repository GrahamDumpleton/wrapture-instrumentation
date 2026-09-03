"""The suite's Starlette application: every endpoint shape the
instrumentation must handle, built only when asked so the tests
control whether construction happens under instrumentation."""

from __future__ import annotations

from typing import Any

PRICES = {"widget": 42, "gadget": 7}


def make_app() -> Any:
    """Build the shop: async and sync endpoints, a path parameter, a
    named route, a partial, a failing endpoint, and a mounted
    sub-application."""

    import functools

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount, Route

    async def index(request: Any) -> PlainTextResponse:
        return PlainTextResponse("shop")

    async def quoted(request: Any) -> PlainTextResponse:
        item = request.path_params["item"]

        return PlainTextResponse(f"{item}: {PRICES[item]} coins")

    def pricing(request: Any) -> PlainTextResponse:
        # A sync endpoint: starlette runs it in a threadpool.

        return PlainTextResponse("all prices on request")

    async def announce(request: Any, banner: str) -> PlainTextResponse:
        return PlainTextResponse(banner)

    async def summary(request: Any) -> PlainTextResponse:
        return PlainTextResponse("summary")

    return Starlette(
        routes=[
            Route("/", index),
            Route("/quote/{item}", quoted),
            Route("/pricing", pricing, name="prices"),
            Route("/motd", functools.partial(announce, banner="welcome")),
            Mount("/reports", routes=[Route("/summary", summary)]),
        ]
    )
