"""The class as wrapture reads it: its data, its settings, and that
its standard library target's version is the interpreter's."""

from __future__ import annotations

import platform
import warnings

# xmlrpc.server is imported for its side: the class's trigger fires on
# its import, so the applying test below works with this file run on
# its own.
import xmlrpc.server  # noqa: F401

import pytest
from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.server.xmlrpc_server import XMLRPCServerInstrumentation


def test_class_data() -> None:
    assert XMLRPCServerInstrumentation.target == "xmlrpc.server"
    assert XMLRPCServerInstrumentation.removable is True
    assert XMLRPCServerInstrumentation.requires == ()
    assert XMLRPCServerInstrumentation.supports == ">=3.12"

    settings = XMLRPCServerInstrumentation.settings
    assert list(settings) == ["requests", "methods"]

    requests = settings["requests"]
    assert isinstance(requests, Aspect)
    assert requests.primary is True
    assert requests.defaults == {}
    assert set(requests.settings) == {"join"}
    assert requests.settings["join"].default is True

    methods = settings["methods"]
    assert isinstance(methods, Aspect)
    assert methods.primary is False
    assert callable(methods.defaults["capture_args"])
    assert methods.defaults["capture_result"] == "shape"
    assert set(methods.settings) == set()


def test_the_description_is_the_docstring_first_line() -> None:
    assert (XMLRPCServerInstrumentation.__doc__ or "").splitlines()[0] == (
        "Request and dispatch tracing for xmlrpc.server."
    )


def test_constructing_without_settings_works() -> None:
    instance = XMLRPCServerInstrumentation()

    requests = instance.settings["requests"]
    assert requests.enabled is True
    assert requests.options == {}
    assert requests.settings == {"join": True}

    methods = instance.settings["methods"]
    assert methods.enabled is True
    assert callable(methods.options["capture_args"])
    assert methods.options["capture_result"] == "shape"
    assert methods.settings == {}
    assert instance.applied == ()
    assert instance.pending == ("xmlrpc.server",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        XMLRPCServerInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': capture_result"):
        XMLRPCServerInstrumentation(requests={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'requests': unknown keys"):
        XMLRPCServerInstrumentation(requests={"verbosity": 2})


def test_the_running_python_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(XMLRPCServerInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == platform.python_version()
            assert applied.applied == ("xmlrpc.server",)
            assert applied.pending == ()
