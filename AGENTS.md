# Agent guidance for wrapture-instrumentation

## Project

wrapture-instrumentation is the collection of packaged instrumentation
for common Python packages, applied through wrapture. Each target
package (Flask, requests, ...) gets one `wrapture.Instrumentation`
subclass, registered in the `wrapture.instrumentation` entry point
group under the bare target name, so that a config's `[[instrument]]`
entry switches it on by name. See README.md for what the project
provides and how it is used, and the "Instrumentation packages" page
of the wrapture documentation for the contract every class here
honours.

The package uses a src layout: the code lives in
src/wrapture_instrumentation/, one subpackage per target.

Tests live in the tests/ directory, one subdirectory per target. See
TESTING.md for where tests are, how to run them, and the conventions
for adding new ones.

The scratch/ directory is ignored by git. It holds temporary working
files; never reference scratch/ files by name from code or
documentation that will be committed.

## Rules specific to instrumentation

- The module that defines an `Instrumentation` subclass (the target
  subpackage's `__init__.py`) imports wrapture and nothing else.
  Everything that touches the target, the hook code and the target's
  own classes, lives in the subpackage's `hooks.py` behind an import
  inside `apply()` (`from . import hooks`). wrapture loads the class
  when the config loads, before the application imports anything, and
  a class whose module imported its target would drag the target in
  ahead of the hook meant to fire on its import.
- No target is ever a dependency in pyproject.toml. The only runtime
  dependency is wrapture. Targets the tests need go in the `test`
  dependency group.
- Target subpackages are named `<category>_<target>`, never the bare
  target name: `framework_flask`, not `flask`. The categories are
  listed in README.md under "Adding a target"; add a category only
  when a target fits none of them. Entry point names are always the
  bare target (`flask`), never prefixed.
- Every target has its own test suite under
  `tests/<category>_<target>/`, runnable alone, and a Justfile recipe
  to run it against several versions of the target. The class's
  `supports` range is set by what those runs pass on.
- Tests validate behaviour with wrapture's own unit testing layer
  (timeline tapes and their queries, bindings with `when=` and
  behaviours as stand-ins, `wrapture.instrumentation()` for scoping).
  Never use `unittest.mock`. When a test wants something that layer
  cannot express, write it the plain way with a comment naming the
  gap and call the gap out in the summary of the work, so that
  adding the capability to wrapture can be weighed.
- Docs for each target's instrumentation live in the wrapture
  repository's docs/. This repository has README.md and CHANGES.md
  only.

## Tooling: always use uv

All Python environment and package management in this project is done
with [uv](https://docs.astral.sh/uv/). Never use the Python venv
module, bare pip, or python -m build directly.

- Run commands in the project environment: `uv run <command>`
  (e.g. `uv run pytest`)
- Run a Python interpreter: `uv run python`
- Build sdist and wheel: `uv build`
- Add or remove dependencies (updates pyproject.toml): `uv add <package>`,
  `uv remove <package>`
- Sync the environment from pyproject.toml: `uv sync`

## Common tasks: use the Justfile

The Justfile defines targets for the common development tasks,
wrapping the correct uv invocations. Prefer these targets over
synthesizing the underlying commands yourself; run `just --list` to
see everything.

- `just test` runs the whole test suite on the default Python
  version. Extra arguments pass through to pytest, so a specific file
  or test is `just test tests/test_wsgi.py` or `just test -k pattern`.
- `just test-target framework_flask` runs one target's suite.
- `just test-python 3.13t` runs the suite on one nominated Python
  version; `just test-all` runs it on every supported version. Both
  pass extra arguments through to pytest.
- `just test-dev` runs the suite against an editable checkout of
  wrapture in the sibling directory ../wrapture, for iterating
  against unreleased wrapture changes without editing pyproject.toml.
- `just lint` checks with the ruff linter and formatter; `just format`
  reformats and applies auto-fixes.
- `just typecheck` runs mypy.

## Style

- Do not use emdashes in any files in this project. Rephrase with
  commas, parentheses, colons, or separate sentences instead.
- Project code must always use Python type hints. Add them to all
  function and method signatures (parameters and return types), and
  to attributes and variables where the type is not obvious from the
  assignment. When adding or modifying code that lacks type hints,
  add them.
- Use vertical white space liberally inside function and method
  bodies. Write code in paragraphs: group the statements that
  together perform one step, and separate each group from the next
  with a blank line. Natural paragraph boundaries include setup
  versus the main work versus the result, before and after a
  conditional or loop, and around a with or try block. Do not cram a
  body into one contiguous blob, and equally do not put a blank line
  between every single statement; the blank lines should mark where
  one thought ends and the next begins.
- Where it helps the reader, start a paragraph of code with a short
  comment saying what that step does or why it is needed. Prefer one
  comment per logical block over line-by-line commentary, and skip
  the comment entirely when the code already says it plainly.
- Put a blank line between such a block comment and the code below
  it: the comment introduces the paragraph rather than sitting flush
  against its first line.
- Put a blank line between a function or method docstring and the
  first line of code in the body.
- Every function, method or property that is part of the public API
  must have a docstring saying what it does. The exceptions are cases
  that are truly trivial and obvious, such as an accessor property
  named for the attribute it returns, and dunder methods implementing
  standard protocols.

## Git

- The repository follows a main/develop split: develop is the
  working and default branch, main holds releases, and feature
  branches merge to develop.
- Git commit messages must never include a co-authored-by agent
  message or any similar agent attribution trailer.
- An AI agent must never commit changes on its own initiative. Finish
  the piece of work, summarize it, and wait to be told to commit.
  Permission to commit applies only to the work it was given for; it
  does not carry forward to later steps of a multi-step plan, each of
  which needs its own review and its own instruction to commit.
  Uncommitted changes are how the review happens: once work is
  committed it can no longer be reviewed as the pending diff, so
  committing early makes review harder, not easier.
