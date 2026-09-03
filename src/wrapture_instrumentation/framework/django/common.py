"""Helpers shared by the patch modules; nothing here touches Django."""

from __future__ import annotations

from typing import Any

import wrapture


def request_options(instrumentation: wrapture.Instrumentation) -> tuple[Any, Any]:
    """The request filter and capture policy both boundaries share.

    ignore_paths becomes a filter_requests() filter for the
    middleware's when=, redact a capture policy on top of the built-in
    sensitive set. tree= is only valid alongside a when=, so the
    filter is left as None when there is nothing to ignore and the
    caller passes tree= only when a filter came back.
    """

    settings = instrumentation.settings

    request_filter = (
        wrapture.filter_requests(ignore={"path": list(settings["ignore_paths"])})
        if settings["ignore_paths"]
        else None
    )
    policy = wrapture.redact(*settings["redact"]) if settings["redact"] else None

    return request_filter, policy


def operation_of(sql: Any) -> str:
    """The SQL's leading keyword, uppercased: the low-cardinality
    operation name the database contract carries."""

    head = str(sql).split(None, 1)

    return head[0].upper() if head else "?"


def captured(name: str | None, value: Any) -> Any:
    """SQL text reduces to its length, parameters to a count, and the
    result side to its type: the query and its data never reach the
    record through argument capture."""

    if name == "sql":
        return f"<{len(str(value))} chars>"

    if name in ("params", "param_list"):
        if value is None:
            return None
        if isinstance(value, (list, tuple, dict)):
            return f"<{len(value)} values>"
        return f"<{type(value).__name__}>"

    if name is None:
        return f"<{type(value).__name__}>"

    return value
