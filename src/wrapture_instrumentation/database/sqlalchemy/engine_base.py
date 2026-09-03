"""The transaction boundaries: Connection's commit and rollback
implementations, recorded as database events.

`Connection._commit_impl` and `Connection._rollback_impl` are the
one door every real transaction end passes through: an explicit
`commit()` or `rollback()`, `engine.begin()` closing its block, an
ORM session's commit, and the rollback that ends 2.0's autobegun
transaction when a connection closes without committing. What they
deliberately exclude is the pool's own housekeeping: the
reset-on-return rollback issued as a connection goes back to the
pool happens below this seam, straight against the dialect, so
pooled checkins do not spray rollback events through the timeline.
"""

from __future__ import annotations

from typing import Any

import wrapture

from .engine_default import captured


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the commit and rollback implementations on Connection;
    register their removal as this trigger's cleanup."""

    settings = instrumentation.settings

    def performs(operation: str) -> Any:
        def record(
            wrapped: Any,
            instance: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:
            # The connection knows its engine, whose URL names the
            # backend and the database the transaction ends on.

            url = instance.engine.url
            data: dict[str, Any] = {
                "system": url.get_backend_name(),
                "operation": operation,
            }
            if url.database:
                data["database"] = url.database

            wrapture.annotate(**data)

            return wrapped(*args, **kwargs)

        return record

    def boundary(name: str, operation: str) -> wrapture.Binding:
        binding = wrapture.binding(
            module.Connection,
            name,
            category="database",
            leaf=bool(settings["leaf"]),
            capture_args=captured,
            capture_result=captured,
        )
        binding.on_call.decorates(performs(operation))

        return binding

    group = wrapture.bindings(
        commit=boundary("_commit_impl", "COMMIT"),
        rollback=boundary("_rollback_impl", "ROLLBACK"),
    )
    group.apply()

    instrumentation.on_cleanup(group.remove)
