"""The class as wrapture reads it: its data, its settings, and that
its standard library target's version is the interpreter's."""

from __future__ import annotations

import platform
import warnings

# xmlrpc.client is imported for its side: the class's trigger fires on
# its import, so the applying test below works with this file run on
# its own.
import xmlrpc.client  # noqa: F401

import pytest
from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.external.xmlrpc_client import XMLRPCClientInstrumentation


def test_class_data() -> None:
    assert XMLRPCClientInstrumentation.target == "xmlrpc.client"
    assert XMLRPCClientInstrumentation.removable is True
    assert XMLRPCClientInstrumentation.requires == ()
    assert XMLRPCClientInstrumentation.supports == ">=3.12"

    assert set(XMLRPCClientInstrumentation.settings) == {"leaf", "propagate"}
    assert XMLRPCClientInstrumentation.settings["leaf"].default is True
    assert XMLRPCClientInstrumentation.settings["propagate"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    assert (XMLRPCClientInstrumentation.__doc__ or "").splitlines()[0] == (
        "Remote call tracing and trace propagation for xmlrpc.client."
    )


def test_constructing_without_settings_works() -> None:
    instance = XMLRPCClientInstrumentation()

    assert instance.settings == {"leaf": True, "propagate": True}
    assert instance.applied == ()
    assert instance.pending == ("xmlrpc.client",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="redact"):
        XMLRPCClientInstrumentation(redact=["voucher"])


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(XMLRPCClientInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("xmlrpc.client",)
            assert applied.pending == ()
