# All supported Python versions, including free threaded (t) builds.
# 3.15 is in RC release phase but is expected to work.
python_versions := "3.12 3.13 3.13t 3.14 3.14t 3.15 3.15t"

# One representative release per supported minor of each target, for the
# per-target matrix recipes below. The instrumentation's `supports` range
# is kept honest by what these pass on.
flask_versions := "3.0.3 3.1.3"
httpx_versions := "0.27.2 0.28.1"
jinja2_versions := "3.0.3 3.1.6"
requests_versions := "2.31.0 2.32.5"
uvicorn_versions := "0.30.0 0.52.4"

# List available targets.
default:
    @just --list

# Run the test suite on the default Python version; extra args go to pytest.
test *ARGS:
    uv run pytest {{ARGS}}

# Run one target's test suite, e.g. `just test-target framework/flask`.
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
    uv run --with "flask=={{VERSION}}" pytest tests/framework/flask {{ARGS}}

# Run the Flask suite against every version in flask_versions.
test-flask-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{flask_versions}}; do
        echo "=== Flask ${version} ==="
        just test-flask "${version}" {{ARGS}}
    done

# Run the httpx suite against one httpx version, e.g. `just test-httpx 0.27.2`.
test-httpx VERSION *ARGS:
    uv run --with "httpx=={{VERSION}}" pytest tests/external/httpx {{ARGS}}

# Run the httpx suite against every version in httpx_versions.
test-httpx-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{httpx_versions}}; do
        echo "=== httpx ${version} ==="
        just test-httpx "${version}" {{ARGS}}
    done

# Run the Jinja2 suite against one Jinja2 version, e.g. `just test-jinja2 3.0.3`.
test-jinja2 VERSION *ARGS:
    uv run --with "jinja2=={{VERSION}}" pytest tests/template/jinja2 {{ARGS}}

# Run the Jinja2 suite against every version in jinja2_versions.
test-jinja2-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{jinja2_versions}}; do
        echo "=== Jinja2 ${version} ==="
        just test-jinja2 "${version}" {{ARGS}}
    done

# Run the requests suite against one requests version, e.g. `just test-requests 2.31.0`.
test-requests VERSION *ARGS:
    uv run --with "requests=={{VERSION}}" pytest tests/external/requests {{ARGS}}

# Run the requests suite against every version in requests_versions.
test-requests-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{requests_versions}}; do
        echo "=== requests ${version} ==="
        just test-requests "${version}" {{ARGS}}
    done

# Run the uvicorn suite against one uvicorn version, e.g. `just test-uvicorn 0.30.0`.
test-uvicorn VERSION *ARGS:
    uv run --with "uvicorn=={{VERSION}}" pytest tests/server/uvicorn {{ARGS}}

# Run the uvicorn suite against every version in uvicorn_versions.
test-uvicorn-all *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    for version in {{uvicorn_versions}}; do
        echo "=== uvicorn ${version} ==="
        just test-uvicorn "${version}" {{ARGS}}
    done

# Drive the shop application with the Flask and Jinja2
# instrumentations applied together, for verifying the results by
# eye and seeing separate instrumentations meet in one tree: the
# live event stream, then the reconstructed tree. The wrapture[otel] overlay carries the optional
# OpenTelemetry dependencies, so `just demo-flask --otel` also exports
# the events as spans to a local OTLP endpoint (localhost:4318 unless
# OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
demo-flask *ARGS:
    uv run --with "wrapture[otel]" python -m demo.framework_flask {{ARGS}}

# Drive a Jinja2 environment directly with the instrumentation applied;
# same shape as demo-flask, --otel exports to a local OTLP endpoint.
demo-jinja2 *ARGS:
    uv run --with "wrapture[otel]" python -m demo.template_jinja2 {{ARGS}}

# Drive urllib against a local server with the instrumentation applied;
# same shape as demo-flask, --otel exports to a local OTLP endpoint.
demo-urllib *ARGS:
    uv run --with "wrapture[otel]" python -m demo.external_urllib_request {{ARGS}}

# Show the http.client wire layer beneath urllib.request with its leaf
# switched off, then standalone; --otel exports to a local OTLP endpoint.
demo-http-client *ARGS:
    uv run --with "wrapture[otel]" python -m demo.external_http_client {{ARGS}}

# Drive requests against a local server with the instrumentation applied;
# same shape as demo-flask, --otel exports to a local OTLP endpoint.
demo-requests *ARGS:
    uv run --with "wrapture[otel]" python -m demo.external_requests {{ARGS}}

# Drive httpx against a local server with the instrumentation applied,
# sync client then async; same shape as demo-flask, --otel exports to a
# local OTLP endpoint.
demo-httpx *ARGS:
    uv run --with "wrapture[otel]" python -m demo.external_httpx {{ARGS}}

# Drive xmlrpc.client against a local server with the instrumentation
# applied; same shape as demo-flask, --otel exports to a local OTLP endpoint.
demo-xmlrpc *ARGS:
    uv run --with "wrapture[otel]" python -m demo.external_xmlrpc_client {{ARGS}}

# Drive an instrumented SimpleXMLRPCServer with an instrumented client,
# both sides of each call in one process sharing one trace id; same
# shape as demo-flask, --otel exports to a local OTLP endpoint.
demo-xmlrpc-server *ARGS:
    uv run --with "wrapture[otel]" python -m demo.server_xmlrpc {{ARGS}}

# Serve applications through an instrumented wsgiref.simple_server with
# an instrumented urllib client, a Flask app showing one boundary per
# request; same shape as demo-flask, --otel exports to a local endpoint.
demo-wsgiref *ARGS:
    uv run --with "wrapture[otel]" python -m demo.server_wsgiref {{ARGS}}

# Serve applications through an instrumented werkzeug development server
# with an instrumented urllib client, a Flask app showing one boundary
# per request; same shape as demo-flask, --otel exports to a local endpoint.
demo-werkzeug *ARGS:
    uv run --with "wrapture[otel]" python -m demo.server_werkzeug {{ARGS}}

# Serve an ASGI application through an instrumented uvicorn server
# with an instrumented httpx client, both sides of each request in one
# trace; same shape as demo-flask, --otel exports to a local endpoint.
demo-uvicorn *ARGS:
    uv run --with "wrapture[otel]" python -m demo.server_uvicorn {{ARGS}}

# Drive sqlite3 with the instrumentation applied, with and without SQL
# text recording; same shape as demo-flask, --otel exports to a local
# OTLP endpoint.
demo-sqlite3 *ARGS:
    uv run --with "wrapture[otel]" python -m demo.database_sqlite3 {{ARGS}}

# The package depends on a released wrapture. This overlays a checkout
# of wrapture from the sibling directory as an editable install for the
# run, for iterating against unreleased wrapture changes without
# touching pyproject.toml.
# Run the test suite against the wrapture checkout in ../wrapture.
test-dev *ARGS:
    uv run --with-editable ../wrapture pytest {{ARGS}}

# Check code with the ruff linter and formatter.
lint:
    uv run ruff check src tests demo
    uv run ruff format --check src tests demo

# Reformat code and fix lint issues that are auto-fixable.
format:
    uv run ruff format src tests demo
    uv run ruff check --fix src tests demo

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
