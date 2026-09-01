"""The class as wrapture reads it: its data, its settings, and that a
standard library target's version is the interpreter's."""

from __future__ import annotations

# urllib.request is imported for its side: the class's trigger fires on
# its import, so the applying test below works with this file run on
# its own.
import platform
import urllib.request  # noqa: F401
import warnings

import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.external_urllib import UrllibInstrumentation


def test_class_data() -> None:
    assert UrllibInstrumentation.target == "urllib"
    assert UrllibInstrumentation.removable is True
    assert UrllibInstrumentation.requires == ()

    # A standard library target's version is the interpreter's, so
    # supports is a Python version range.

    assert UrllibInstrumentation.supports == ">=3.12"

    assert set(UrllibInstrumentation.settings) == {"leaf", "propagate", "redact"}
    assert UrllibInstrumentation.settings["leaf"].default is True
    assert UrllibInstrumentation.settings["propagate"].default is True
    assert UrllibInstrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (UrllibInstrumentation.__doc__ or "").splitlines()[0] == (
        "Outbound request tracing and trace propagation for urllib."
    )


def test_constructing_without_settings_works() -> None:
    instance = UrllibInstrumentation()

    assert instance.settings == {"leaf": True, "propagate": True, "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("urllib.request",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="ignore_hosts"):
        UrllibInstrumentation(ignore_hosts=["localhost"])


def test_a_setting_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        UrllibInstrumentation(leaf="no")


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(UrllibInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("urllib.request",)
            assert applied.pending == ()
