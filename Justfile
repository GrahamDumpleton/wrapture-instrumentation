# All supported Python versions, including free threaded (t) builds.
# 3.15 is in RC release phase but is expected to work.
python_versions := "3.12 3.13 3.13t 3.14 3.14t 3.15 3.15t"

# One representative release per supported minor of each target, for the
# per-target matrix recipes below. The instrumentation's `supports` range
# is kept honest by what these pass on.
flask_versions := "3.0.3 3.1.3"

# List available targets.
default:
    @just --list

# Run the test suite on the default Python version; extra args go to pytest.
test *ARGS:
    uv run pytest {{ARGS}}

# Run one target's test suite, e.g. `just test-target framework_flask`.
test-target TARGET *ARGS:
    uv run pytest tests/{{TARGET}} {{ARGS}}

# Extra arguments are passed through to pytest. Each version gets its own
# environment so the default .venv is untouched, and only the test
# dependency group is installed: dev tools such as mypy do not build on
# the free threaded versions and are not needed to run tests.
# Run the test suite on one nominated version, e.g. `just test-python 3.13t`.
test-python VERSION *ARGS:
    UV_PROJECT_ENVIRONMENT=.venv-{{VERSION}} uv run --python {{VERSION}} --no-default-groups --group test pytest {{ARGS}}

# Run the test suite on every supported Python version.
test-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{python_versions}}; do
        echo "=== Python ${version} ==="
        just test-python "${version}" {{ARGS}}
    done

# Each target's suite can run against a nominated version of the target,
# overlaid on the project environment for that run, so the lock's version
# stays the default and older versions need no environment of their own.
# Run the Flask suite against one Flask version, e.g. `just test-flask 3.0.3`.
test-flask VERSION *ARGS:
    uv run --with "flask=={{VERSION}}" pytest tests/framework_flask {{ARGS}}

# Run the Flask suite against every version in flask_versions.
test-flask-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{flask_versions}}; do
        echo "=== Flask ${version} ==="
        just test-flask "${version}" {{ARGS}}
    done

# The package depends on a released wrapture. This overlays a checkout
# of wrapture from the sibling directory as an editable install for the
# run, for iterating against unreleased wrapture changes without
# touching pyproject.toml.
# Run the test suite against the wrapture checkout in ../wrapture.
test-dev *ARGS:
    uv run --with-editable ../wrapture pytest {{ARGS}}

# Check code with the ruff linter and formatter.
lint:
    uv run ruff check src tests
    uv run ruff format --check src tests

# Reformat code and fix lint issues that are auto-fixable.
format:
    uv run ruff format src tests
    uv run ruff check --fix src tests

# Type check the project with mypy.
typecheck:
    uv run mypy

# Build the source distribution and wheel into dist/.
build:
    uv build

# Remove temporary files: caches, virtual environments and build artifacts.
clean:
    rm -rf .venv .venv-*
    rm -rf build dist src/*.egg-info *.egg-info
    rm -rf .pytest_cache .mypy_cache .ruff_cache
    find . -type d -name __pycache__ -not -path "./scratch/*" -exec rm -rf {} +
