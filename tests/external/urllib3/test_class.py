"""The class as wrapture reads it: its data, its settings, and the
installed urllib3 satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

# Imported for its side: the class's triggers fire on urllib3's
# import, so the applying test below works with this file run on its
# own.
import urllib3  # noqa: F401
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.external.urllib3 import Urllib3Instrumentation


def test_class_data() -> None:
    assert Urllib3Instrumentation.target == "urllib3"
    assert Urllib3Instrumentation.removable is True
    assert Urllib3Instrumentation.requires == ()
    assert Urllib3Instrumentation.supports == ">=1.26,<3"

    assert set(Urllib3Instrumentation.settings) == {"leaf", "propagate", "redact"}
    assert Urllib3Instrumentation.settings["leaf"].default is True
    assert Urllib3Instrumentation.settings["propagate"].default is True
    assert Urllib3Instrumentation.settings["redact"].default == []


def test_the_description_is_the_docstring_first_line() -> None:
    assert (Urllib3Instrumentation.__doc__ or "").splitlines()[0] == (
        "Outbound request tracing and trace propagation for urllib3."
    )


def test_constructing_without_settings_works() -> None:
    instance = Urllib3Instrumentation()

    assert instance.settings == {"leaf": True, "propagate": True, "redact": []}
    assert instance.applied == ()
    assert instance.pending == ("urllib3.poolmanager", "urllib3.connectionpool")


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="join"):
        Urllib3Instrumentation(join=True)


def test_the_installed_urllib3_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(Urllib3Instrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("urllib3")
            assert applied.applied == (
                "urllib3.poolmanager",
                "urllib3.connectionpool",
            )
            assert applied.pending == ()
