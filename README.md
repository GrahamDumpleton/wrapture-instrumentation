# wrapture-instrumentation

Instrumentation for common Python packages, applied through
[wrapture](https://github.com/GrahamDumpleton/wrapture).

wrapture attaches bindings to arbitrary Python call sites without
modifying the code being observed, and its config layer can switch on
packaged instrumentation for a third-party package by name. This
project is the collection of that packaged instrumentation: one
`wrapture.Instrumentation` class per target package (Flask first,
more to follow), each registered under the bare target name, so that
tracing a framework is one config entry and no code.

> **Status: pre-alpha.** The package is being built target by target
> against wrapture's alpha series; nothing is published to PyPI yet.
> Flask is the first target and covers its basics; see the table below.

## Installation

```console
$ pip install wrapture-instrumentation
```

Installing it brings wrapture and nothing else. No target package is
a dependency: the instrumentation for a package you do not have is
inert, and wrapture checks the installed version of each target
against the range the instrumentation supports at apply time.

## Using it

An `[[instrument]]` entry in `wrapture.toml` names a target:

```toml
[[instrument]]
name = "flask"

[[sink]]
type = "printer"
```

and the runner applies it before the application starts, so the
patches are in place before the framework is imported:

```console
$ python -m wrapture -m myapp
```

The same config works through
[autowrapt](https://github.com/GrahamDumpleton/autowrapt) injection
(`AUTOWRAPT_BOOTSTRAP=wrapture python myapp.py`) and, in a test,
through `wrapture.instrumentation("flask")` scoping the
instrumentation to a block. The
[ad-hoc tracing guide](https://wrapture.readthedocs.io/en/latest/ad-hoc-tracing.html)
covers the config file itself.

To see what is installed, what each instrumentation supports in the
current environment, and what settings it takes:

```console
$ python -m wrapture.tools instrumentation --verbose
```

and to generate the `[[instrument]]` entries to paste into a config,
every one disabled and every setting commented out at its default:

```console
$ python -m wrapture.tools instrumentation --toml
```

## Provided instrumentation

| Target | Supported versions | Records | Settings |
| ------ | ------------------ | ------- | -------- |
| `flask` | Flask 3.x | Every request as one tree (the recording WSGI middleware installed on each application at construction), every view function beneath its request (observed as routes register, blueprints and `MethodView`s included), and the exception Flask catches on its way to a 500 noted on the request. | none yet |

The entry point name is the config's `name`; the table says what each
instrumentation does in the current cut. Settings, further choke
points and wider version ranges are being added target by target.

## Adding a target

Each target lives in its own subpackage under
`src/wrapture_instrumentation/`, named `<category>_<target>`:
`framework_flask`, `external_requests`, `database_sqlite3`. The
category says what kind of thing the target is and, with it, which
part of wrapture the instrumentation mostly uses:

- `framework_`: web frameworks, and their extensions as compound
  names (`framework_flask_restful`).
- `external_`: outbound HTTP and RPC clients and service SDKs.
- `database_`: DB-API drivers and SQL toolkits.
- `datastore_`: other stores and caches.
- `task_`: task queues. `messaging_`: brokers and their clients.
- `server_`: WSGI and ASGI servers. `template_`: template engines.

A new category is added when a target fits none of these. The
directory name is internal; the entry point name, and so the name a
config uses, is always the bare target.

The subpackage's `__init__.py` holds one `wrapture.Instrumentation`
subclass and imports only wrapture; everything that touches the
target lives in `hooks.py`, reached by an import inside `apply()`.
The class is registered in `pyproject.toml` under
`[project.entry-points."wrapture.instrumentation"]`, and gets its own
test suite under `tests/<category>_<target>/`. The
[instrumentation packages](https://wrapture.readthedocs.io/en/latest/instrumentation-packages.html)
page of the wrapture documentation is the full contract; TESTING.md
here covers the tests.

## License

BSD-2-Clause, as wrapture.
