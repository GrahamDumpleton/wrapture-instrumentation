"""The class as wrapture reads it: its data, its settings, and the
installed grpcio satisfying its supports range."""

from __future__ import annotations

import warnings
from importlib import metadata

import pytest

pytest.importorskip("grpc")

from wrapture import ConfigError, ConfigWarning, instrumentation

from wrapture_instrumentation.rpc.grpc import GRPCInstrumentation


def test_class_data() -> None:
    assert GRPCInstrumentation.target == "grpc"
    assert GRPCInstrumentation.removable is True
    assert GRPCInstrumentation.requires == ()
    assert GRPCInstrumentation.supports == ">=1.76,<2"

    assert set(GRPCInstrumentation.settings) == {
        "client",
        "server",
        "propagate",
        "join",
    }
    assert GRPCInstrumentation.settings["client"].default is True
    assert GRPCInstrumentation.settings["server"].default is True
    assert GRPCInstrumentation.settings["propagate"].default is True
    assert GRPCInstrumentation.settings["join"].default is True


def test_the_description_is_the_docstring_first_line() -> None:
    assert (GRPCInstrumentation.__doc__ or "").splitlines()[0] == (
        "Call and handler tracing for gRPC clients and servers."
    )


def test_constructing_without_settings_works() -> None:
    instance = GRPCInstrumentation()

    assert instance.settings == {
        "client": True,
        "server": True,
        "propagate": True,
        "join": True,
    }
    assert instance.applied == ()
    assert instance.pending == ("grpc",)


def test_an_undeclared_setting_is_refused() -> None:
    with pytest.raises(ConfigError, match="leaf"):
        GRPCInstrumentation(leaf=False)


def test_the_installed_grpcio_is_within_supports() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConfigWarning)

        with instrumentation(GRPCInstrumentation) as record:
            (applied,) = record.instrumentations

            assert applied.target_version == metadata.version("grpcio")
            assert applied.applied == ("grpc",)
            assert applied.pending == ()
