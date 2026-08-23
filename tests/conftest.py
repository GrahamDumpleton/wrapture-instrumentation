"""Helpers shared by every suite."""

from __future__ import annotations

import subprocess
import sys
from importlib import metadata

DISTRIBUTION = "wrapture-instrumentation"


def run_python(*arguments: str) -> str:
    """Run a fresh interpreter with the given arguments and return its
    stdout, failing the test with its stderr if it did not exit 0.

    For the properties that are about a fresh interpreter's state,
    what `import` pulls in and what the listing tool prints; the
    environment is the test environment's own, so the package and
    its entry points are installed.
    """

    completed = subprocess.run(
        [sys.executable, *arguments],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def run_snippet(code: str) -> str:
    """Run a snippet of Python in a fresh interpreter; see run_python."""

    return run_python("-c", code)


def run_tool(*arguments: str) -> str:
    """Run `python -m wrapture.tools` with the given arguments in a
    fresh interpreter; see run_python."""

    return run_python("-m", "wrapture.tools", *arguments)


def registered_entry_points() -> list[metadata.EntryPoint]:
    """The `wrapture.instrumentation` entry points this distribution
    registers, in entry point order."""

    points = metadata.entry_points(group="wrapture.instrumentation")

    return [
        point
        for point in points
        if point.dist is not None
        and point.dist.name.replace("_", "-").lower() == DISTRIBUTION
    ]
