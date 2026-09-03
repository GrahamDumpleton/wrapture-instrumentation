"""The suite's FastAPI application: every endpoint shape the
instrumentation must handle, built only when asked so the tests
control whether construction happens under instrumentation."""

from __future__ import annotations

from typing import Any

PRICES = {"widget": 42, "gadget": 7}


def make_app() -> Any:
    """Build the shop: typed async and sync endpoints, a path
    parameter with a response model, a named route, a dependency, a
    failing endpoint, and a prefixed router included after the
    fact."""

    from fastapi import APIRouter, Depends, FastAPI
    from pydantic import BaseModel

    class Quote(BaseModel):
        item: str
        price: int

    app = FastAPI()

    @app.get("/")
    async def index() -> dict[str, str]:
        return {"shop": "open"}

    @app.get("/quote/{item}", response_model=Quote)
    async def quoted(item: str) -> Any:
        return {"item": item, "price": PRICES[item]}

    @app.get("/pricing", name="prices")
    def pricing() -> dict[str, str]:
        # A sync endpoint: FastAPI runs it in a threadpool.

        return {"pricing": "on request"}

    def current_shopper() -> str:
        return "pat"

    @app.get("/basket")
    async def basket(shopper: str = Depends(current_shopper)) -> dict[str, str]:
        return {"shopper": shopper}

    router = APIRouter(prefix="/reports")

    @router.get("/summary")
    async def summary() -> dict[str, str]:
        return {"report": "summary"}

    app.include_router(router)

    return app
