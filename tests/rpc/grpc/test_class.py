"""The class as wrapture reads it: its data, its settings, and the
installed grpcio satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

pytest.importorskip("grpc")

from wrapture import Aspect, ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.rpc.grpc import GRPCInstrumentation


def test_class_data() -> None:
    assert GRPCInstrumentation.target == "grpc"
    assert GRPCInstrumentation.removable is True
    assert GRPCInstrumentation.requires == ()
    assert GRPCInstrumentation.supports == ">=1.76,<2"

    settings = GRPCInstrumentation.settings
    assert list(settings) == ["client", "server"]

    client = settings["client"]
    assert isinstance(client, Aspect)
    assert client.primary is False
    assert client.defaults == {}
    assert set(client.settings) == {"propagate"}
    assert client.settings["propagate"].default is True

    server = settings["server"]
    assert isinstance(server, Aspect)
    assert server.primary is False
    assert server.defaults == {}
    assert set(server.settings) == {"join"}
    assert server.settings["join"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    assert (GRPCInstrumentation.__doc__ or "").splitlines()[0] == (
        "Call and handler tracing for gRPC clients and servers."
    )


def test_constructing_without_settings_works() -> None:
    instance = GRPCInstrumentation()

    client = instance.settings["client"]
    assert client.enabled is True
    assert client.options == {}
    assert client.settings == {"propagate": True}

    server = instance.settings["server"]
    assert server.enabled is True
    assert server.options == {}
    assert server.settings == {"join": True}
    assert instance.applied == ()
    assert instance.pending == ("grpc",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="verbosity"):
        GRPCInstrumentation(verbosity=2)


def test_a_recording_key_under_a_part_is_checked() -> None:
    with pytest.raises(ConfigError, match="aspect 'client': capture_result"):
        GRPCInstrumentation(client={"capture_result": "sumary"})


def test_an_unknown_key_under_a_part_is_refused() -> None:
    with pytest.raises(ConfigError, match="aspect 'client': unknown keys"):
        GRPCInstrumentation(client={"verbosity": 2})


def test_a_capture_key_under_the_server_part_is_refused_when_applied() -> None:
    # The server boundary is a block, which records no values, so a
    # capture key under the aspect can never act and is refused as the
    # instrumentation applies; a stack is honoured.

    with pytest.raises(ConfigError, match="aspect 'server' cannot apply"):
        with instrumentation(GRPCInstrumentation, server={"capture_args": "types"}):
            pass

    with instrumentation(GRPCInstrumentation, server={"stack": "caller"}):
        pass


def test_the_installed_grpcio_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(GRPCInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("grpcio")
            assert applied.applied == ("grpc",)
            assert applied.pending == ()
