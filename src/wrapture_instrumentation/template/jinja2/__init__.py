"""Instrumentation for Jinja2: template rendering traced wherever the
engine is driven, in an application or standalone.

This module imports only wrapture. Everything that touches Jinja2
lives in the sibling environment module, named for the jinja2 module
it patches, importing only wrapture at top level, so loading this
class when a config loads never imports Jinja2 ahead of the hook
meant to fire on its import.
"""

from __future__ import annotations

from typing import Any

import wrapture
from wrapture import Aspect

from . import environment


class Jinja2Instrumentation(wrapture.Instrumentation):
    """Template rendering tracing for Jinja2."""

    description = "Template rendering tracing for Jinja2."

    target = "jinja2"
    supports = ">=3.0,<4"
    removable = True

    # The aspects: the renders (sync, async, streamed) are the primary
    # aspect, and loading is the machinery of getting a template ready.

    settings = {
        "renders": Aspect(
            "template rendering: render, generate and their async forms",
            primary=True,
        ),
        "loading": Aspect(
            "template loading and compilation"
            " (Environment._load_template and Environment.compile)",
        ),
    }

    @wrapture.instrumentation_hook("jinja2.environment")
    def jinja2_environment(self, name: str, module: Any) -> None:
        """Bind Template and Environment once jinja2.environment
        exists."""

        environment.instrument(module, self)
