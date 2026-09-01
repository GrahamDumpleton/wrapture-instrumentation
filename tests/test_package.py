"""Package-level tests: the version, and the rules every registered
instrumentation has to keep regardless of its target.

The import-light rule is checked the way wrapture itself checks it,
by watching what appears in sys.modules, but in a fresh interpreter
per class so that nothing the test process has already imported can
hide a violation.
"""

from __future__ import annotations

import ast
import re
from importlib import metadata
from pathlib import Path

import pytest
import wrapture

import wrapture_instrumentation
from tests.conftest import (
    DISTRIBUTION,
    registered_entry_points,
    run_snippet,
    run_tool,
)

ENTRY_POINTS = registered_entry_points()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def test_version_info_is_a_tuple_of_strings() -> None:
    assert isinstance(wrapture_instrumentation.__version_info__, tuple)
    assert all(
        isinstance(part, str) for part in wrapture_instrumentation.__version_info__
    )
    assert len(wrapture_instrumentation.__version_info__) in (3, 4)


def test_version_is_formatted_from_version_info() -> None:
    parts = wrapture_instrumentation.__version_info__
    base = ".".join(parts[:3])

    if len(parts) == 3:
        expected = base
    elif parts[3].startswith(("dev", "post")):
        expected = f"{base}.{parts[3]}"
    else:
        expected = f"{base}{parts[3]}"

    assert wrapture_instrumentation.__version__ == expected


def test_version_is_pep_440_compliant() -> None:
    # Enough of PEP 440 to cover the forms this project uses: a three-part
    # release number with an optional pre-release, dev or post suffix.

    pattern = r"^\d+\.\d+\.\d+((a|b|rc)\d+|\.dev\d+|\.post\d+)?$"
    assert re.match(pattern, wrapture_instrumentation.__version__)


def test_version_matches_the_installed_distribution() -> None:
    assert metadata.version(DISTRIBUTION) == wrapture_instrumentation.__version__


# ---------------------------------------------------------------------------
# import-light rules
# ---------------------------------------------------------------------------


def test_importing_the_package_imports_nothing_else() -> None:
    # The top-level package carries only the version: importing it
    # loads no class, no target, and not even wrapture.

    appeared = run_snippet(
        "import sys\n"
        "before = set(sys.modules)\n"
        "import wrapture_instrumentation\n"
        "print(sorted(set(sys.modules) - before))\n"
    )

    assert appeared.strip() == "['wrapture_instrumentation']"


@pytest.mark.parametrize("point", ENTRY_POINTS, ids=lambda point: str(point.name))
def test_each_entry_point_loads_an_instrumentation_named_for_its_target(
    point: metadata.EntryPoint,
) -> None:
    cls = point.load()

    assert isinstance(cls, type)
    assert issubclass(cls, wrapture.Instrumentation)
    assert cls is not wrapture.Instrumentation

    # Entry point names are the bare target, so the config's
    # `name = "flask"` and the class's `target` agree.

    assert point.name == cls.target
    assert cls.removable is True


@pytest.mark.parametrize("point", ENTRY_POINTS, ids=lambda point: str(point.name))
def test_loading_a_class_imports_no_target(point: metadata.EntryPoint) -> None:
    # Loading the class is what wrapture does when the config loads,
    # before the application imports anything; if that dragged a
    # target in, the hook meant to fire on the target's import would
    # land after it. Neither this class's own target nor any other
    # registered class's target may appear.

    targets = sorted({other.load().target for other in ENTRY_POINTS})

    # wrapture is always imported before any class loads, and its own
    # imports are not the class's doing: it pulls in urllib.parse,
    # which sits under the standard library target urllib. The
    # snapshot is taken after it, as wrapture's own check effectively
    # does.

    appeared = run_snippet(
        "import sys\n"
        "from importlib import metadata\n"
        "import wrapture\n"
        "before = set(sys.modules)\n"
        f"(point,) = [p for p in metadata.entry_points(group={point.group!r})"
        f" if p.name == {point.name!r} and p.value == {point.value!r}]\n"
        "point.load()\n"
        "print(sorted(set(sys.modules) - before))\n"
    )

    imported = set(ast.literal_eval(appeared))
    for target in targets:
        offenders = sorted(
            name for name in imported if name == target or name.startswith(f"{target}.")
        )
        assert offenders == [], f"loading {point.name} imported {offenders}"


def test_the_listing_tool_reports_every_entry_cleanly() -> None:
    # The listing reads the class data the way wrapture will, and
    # shows a load error or an import-safety warning in place; there
    # must be none, and every registered entry must be listed.

    output = run_tool("instrumentation", "--verbose")

    problems = [
        line
        for line in output.splitlines()
        if line.strip().startswith(("error:", "warning:"))
    ]
    assert problems == []

    version = wrapture_instrumentation.__version__
    for point in ENTRY_POINTS:
        assert f"{point.name}  ({DISTRIBUTION} {version})" in output


def test_the_readme_table_lists_every_target() -> None:
    # The top README's table is the catalogue: one row per registered
    # target, named by its entry point and linked by absolute URL to
    # the per-target README (relative links break on PyPI), which
    # must itself exist and ship in the package data.

    root = Path(__file__).parent.parent
    text = (root / "README.md").read_text()

    for point in ENTRY_POINTS:
        module = point.value.partition(":")[0]
        subpath = module.replace(".", "/")

        per_target = root / "src" / subpath / "README.md"
        assert per_target.is_file(), f"{point.name} has no per-target README"

        link = (
            "https://github.com/GrahamDumpleton/wrapture-instrumentation"
            f"/blob/develop/src/{subpath}/README.md"
        )
        assert f"[`{point.name}`]({link})" in text, (
            f"{point.name} is missing from the README table or its link"
            f" is not the absolute per-target URL"
        )
