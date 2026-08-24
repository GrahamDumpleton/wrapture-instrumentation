# Testing

## Where the tests are

Tests live in the [tests/](tests/) directory at the top of the
repository, separate from the package code in
src/wrapture_instrumentation/. Test files are named `test_*.py` and
are discovered by pytest, which is configured via the
`[tool.pytest.ini_options]` section of [pyproject.toml](pyproject.toml).

The directory has two levels:

- Package-level tests directly under tests/: the version, the rule
  that importing the package or loading any registered class never
  imports a target, the listing tool reporting every entry cleanly,
  and the test-side WSGI driver's own tests.
- One subdirectory per target, `tests/<category>_<target>/`
  (`tests/framework_flask/`), holding that instrumentation's suite:
  settings validation, applying and removing the class directly, the
  whole path through `wrapture.instrumentation()` with a timeline
  recording what the bindings observe, resolving the entry point by
  name, and a check that the installed target satisfies the class's
  `supports` range.

Shared helpers live in [tests/conftest.py](tests/conftest.py) and
[tests/wsgi.py](tests/wsgi.py).

## The WSGI driver

WSGI applications are driven in process by `tests/wsgi.py`, which
plays the server's side of PEP 3333 exactly: it builds a complete
environ, supplies a `start_response` that honours the `exc_info`
re-invocation rule and returns a working `write` callable, iterates
the application's result, and always calls its `close()`, including
when iteration raises or is abandoned. It is used instead of a
framework's test client because a request event's closing line is
tied to the moment the response iterable is consumed and closed, and
the driver makes that moment explicit: `request(app, "GET", "/path")`
reads and closes for the common case, and `consume=False` hands back
the response with its body unconsumed so a test can check the
request is still open, then `read()` and `close()` it. The same
driver serves every WSGI target.

## Running the tests

All tooling in this project goes through [uv](https://docs.astral.sh/uv/),
which manages the project environment and installs the package, its
development dependencies (including pytest) and the target packages
the tests need.

The simplest way to run the test suite is via the Justfile target:

```console
just test
```

Extra arguments are passed through to pytest, for example:

```console
just test -v
just test tests/test_wsgi.py
just test -k version
```

One target's suite alone:

```console
just test-target framework_flask
```

Equivalently, run pytest directly with uv:

```console
uv run pytest
```

## Watching what the tests record

The suites assert on tapes rather than printing anything, but the
recorded events can be watched live for visual verification. Setting
WRAPTURE_PRINTER in the environment installs a process-wide
wrapture.Printer sink for the session, streaming one line to stderr
as each operation begins and a closing line with its outcome and
timing; pytest captures stderr, so add -s to see it:

```console
WRAPTURE_PRINTER=1 just test tests/framework_flask -s
```

The sink is consulted alongside the tests' own scoped tapes, so the
stream shows exactly what each tape hears without disturbing any
assertion.

For a purpose-built run rather than the tests' traffic, each target
also has a demo module under demo/ that applies its instrumentation,
drives the test application through the WSGI driver, and prints both
the live stream and the reconstructed tree with timings:

```console
just demo-flask
```

With --otel the same events also export as OpenTelemetry spans over
OTLP (to http://localhost:4318, or wherever
OTEL_EXPORTER_OTLP_ENDPOINT points), for verifying the spans in a
local backend such as Jaeger; the Justfile target overlays the
wrapture[otel] dependencies for the run:

```console
just demo-flask --otel
```

## Testing across Python versions

The project supports multiple Python versions, including the free
threaded builds of 3.13, 3.14 and 3.15. The supported list is defined
at the top of the [Justfile](Justfile). The default version used by
plain `just test` is pinned in [.python-version](.python-version).

Run the test suite on every supported version:

```console
just test-all
```

Run the test suite on one nominated version:

```console
just test-python 3.12
just test-python 3.14t
```

Extra arguments are passed through to pytest for these targets too.
uv downloads any Python version it does not already have, and each
version gets its own environment (.venv-VERSION) so the default .venv
is left untouched.

## Testing across target versions

The `test` dependency group installs each target at whatever version
the lock resolves. An instrumentation's `supports` range is kept
honest by running its suite against other versions of the target,
overlaid on the project environment for that run. Each target has a
recipe for it in the Justfile (`just test-flask 3.0.3`) and a list of
versions that `just test-flask-all` loops over; the CI workflow runs
the same matrix. A test in each target's suite asserts the installed
target satisfies `supports`, so a matrix entry outside the range
fails loudly rather than passing vacuously.

## Testing against unreleased wrapture

The package depends on a released wrapture. To run the tests against
a checkout of wrapture in the sibling directory ../wrapture, without
editing pyproject.toml:

```console
just test-dev
```

which overlays that checkout as an editable install for the run.

## Writing tests

- Put new test files in tests/ (package level) or
  tests/<category>_<target>/ (for one instrumentation) and name them
  `test_*.py`.
- Import the package under test as `wrapture_instrumentation`, and
  the instrumentation classes from their subpackages. The project is
  installed into the uv-managed environment, so no path manipulation
  is needed.
- Validate behaviour with wrapture's own unit testing layer:
  `wrapture.timeline()` to record what the instrumentation's bindings
  observe and the tape's tree and queries to assert on it, bindings
  with `when=` and behaviours where a test needs to see a target
  internal being called or control what it does, and
  `wrapture.instrumentation()` to scope an application of a class to
  a block. Do not use `unittest.mock`. If something cannot be
  expressed that way, write it plainly with a comment naming the gap,
  and say so when summarising the work.
- Drive WSGI applications through `tests/wsgi.py`, not a framework's
  test client.
- Tests should not depend on anything in the scratch/ directory,
  which is not part of the repository.
