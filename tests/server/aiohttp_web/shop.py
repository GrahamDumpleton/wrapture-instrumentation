"""The shop application the aiohttp.web suite drives: a plain
handler, a named route, an HTTPException answer, a failing handler,
a class-based view and a sub-application."""

from __future__ import annotations

from aiohttp import web

PRICES = {"widget": 42, "gadget": 7}


async def index(request: web.Request) -> web.Response:
    return web.Response(text="shop open")


async def quoted(request: web.Request) -> web.Response:
    item = request.match_info["item"]

    return web.Response(text=f"{item}: {PRICES[item]}")


async def gone(request: web.Request) -> web.Response:
    raise web.HTTPNotFound(text="gone")


class Pages(web.View):
    async def get(self) -> web.Response:
        return web.Response(text="pages")


async def summary(request: web.Request) -> web.Response:
    return web.Response(text="summary")


def make_app() -> web.Application:
    """Build the shop; routes register at build time, so build it
    with the instrumentation already applied."""

    reports = web.Application()
    reports.router.add_get("/summary", summary)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/quote/{item}", quoted, name="quoted")
    app.router.add_get("/gone", gone)
    app.router.add_view("/pages", Pages)
    app.add_subapp("/reports", reports)

    return app
