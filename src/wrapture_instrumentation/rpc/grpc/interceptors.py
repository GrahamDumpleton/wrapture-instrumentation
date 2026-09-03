"""The grpc patches: interceptors injected at the public factories,
the client's calls recorded as external leaves and the server's
handling as request boundaries.

gRPC's own interceptor machinery is the supported extension point
for exactly this, so rather than binding private internals the
instrumentation patches the three public factories, behaviour only,
and injects interceptor objects built here:

`grpc.insecure_channel` and `grpc.secure_channel` hand their channel
back wrapped by `grpc.intercept_channel` with a client interceptor
covering all four call shapes. Each RPC records as one external
leaf, labelled by the channel method that shaped it
(`grpc:Channel.unary_unary` and its siblings), carrying `system`
(`grpc`), the `service` and `operation` split out of the method path
(which wrapture's OpenTelemetry export maps to `rpc.system`,
`rpc.service` and `rpc.method`), and the channel's `host` and
`port`. The trace identity is added to the call's metadata, a key
the application set itself left alone. A failed RPC is a status,
not an exception: gRPC hands the interceptor a completed call
object either way, and the event carries its code (`OK`,
`NOT_FOUND`) whenever the call has already reached terminal state,
which a blocking unary-response call always has. A streamed
response or a `future()` call returns before the RPC completes, so
its event covers the call being made and carries no code: response
consumption is deliberately not tracked, exactly as the database
targets do not track fetching.

`grpc.server` has a server interceptor prepended to its
`interceptors`. It wraps each method handler the server resolves,
opening a `wrapture.block()` around the handler's run: entered when
the handler is invoked and, for a response-streaming handler,
spanning the generator body to exhaustion, since that body is the
server's own work inside the RPC. The block carries `system`,
`service` and `operation` plus the calling `client` address, joins
the distributed trace the invocation metadata carries, and records
the RPC's code: `OK` on success, the code `abort()` set (an abort
is control flow, recorded as its code with the block clean, the
exception re-raised outside it for grpc to answer), and `UNKNOWN`
for an exception the handler let escape, which is recorded on the
block as the failure it is. An RPC no handler matches is answered
UNIMPLEMENTED by grpc before any handler exists to wrap, so nothing
records for it.

Removal restores the factories and stops the recording: channels
and servers built while instrumented keep their interceptor
objects, which then pass everything through untouched.

The request and response payloads are never captured, on either
side, and metadata values are never recorded; the method path, the
code and the addresses are the whole of what an event carries.

grpc.aio is not yet covered: its factories and interceptor
interfaces are a separate async surface, left to a follow-up.
"""

from __future__ import annotations

from collections import namedtuple
from typing import Any

import wrapture


def describe(method: Any) -> dict[str, Any]:
    """The rpc contract keys a method path carries: system always,
    service and operation split out of `/package.Service/Method`."""

    if isinstance(method, bytes):
        method = method.decode("ascii", "replace")

    data: dict[str, Any] = {"system": "grpc"}

    if isinstance(method, str):
        service, _, operation = method.lstrip("/").rpartition("/")
        if service:
            data["service"] = service
        data["operation"] = operation or method

    return data


def endpoint(target: Any) -> dict[str, Any]:
    """The host and port a channel target names, the scheme prefix
    (`dns:///`, `unix:`) stripped; empty when the target does not
    parse as host:port."""

    if not isinstance(target, str):
        return {}

    _, _, rest = target.rpartition("://")
    rest = rest.lstrip("/")

    host, separator, port = rest.rpartition(":")
    if separator and host and port.isdigit():
        return {"host": host, "port": int(port)}

    return {}


def merged_metadata(existing: Any, headers: dict[str, str]) -> list[tuple[str, Any]]:
    """The call's metadata with the trace identity added: existing
    pairs first, then each header whose key the application did not
    set itself."""

    pairs: list[tuple[str, Any]] = [(key, value) for key, value in (existing or ())]
    present = {str(key).lower() for key, _ in pairs}

    for key, value in headers.items():
        if key.lower() not in present:
            pairs.append((key, value))

    return pairs


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the channel and server factories, behaviour only, and
    build the interceptor classes against the grpc module handed in;
    register removal as this trigger's cleanup."""

    settings = instrumentation.settings

    # Removal restores the factories but cannot reach interceptors
    # already riding on live channels and servers; this flag is how
    # those go quiet, checked on every call.

    active = [True]

    # The fields of grpc's ClientCallDetails, rebuilt when metadata
    # is injected; the trailing ones are read with defaults so an
    # older grpc handing a shorter details object still works.

    class _CallDetails(
        namedtuple(  # noqa: PYI024
            "_CallDetails",
            [
                "method",
                "timeout",
                "metadata",
                "credentials",
                "wait_for_ready",
                "compression",
            ],
        ),
        module.ClientCallDetails,
    ):
        pass

    def with_trace_metadata(details: Any) -> Any:
        headers = wrapture.trace_headers()

        if not headers:
            return details

        return _CallDetails(
            details.method,
            getattr(details, "timeout", None),
            merged_metadata(getattr(details, "metadata", None), headers),
            getattr(details, "credentials", None),
            getattr(details, "wait_for_ready", None),
            getattr(details, "compression", None),
        )

    class ClientTracer(
        module.UnaryUnaryClientInterceptor,
        module.UnaryStreamClientInterceptor,
        module.StreamUnaryClientInterceptor,
        module.StreamStreamClientInterceptor,
    ):
        """One interceptor for all four call shapes: propagation in
        the details, the recording on the bound methods below."""

        def __init__(self, target: Any) -> None:
            self.endpoint = endpoint(target)

        def _pass(self, continuation: Any, details: Any, argument: Any) -> Any:
            if active[0] and settings["propagate"]:
                details = with_trace_metadata(details)

            return continuation(details, argument)

        def intercept_unary_unary(
            self, continuation: Any, details: Any, request: Any
        ) -> Any:
            return self._pass(continuation, details, request)

        def intercept_unary_stream(
            self, continuation: Any, details: Any, request: Any
        ) -> Any:
            return self._pass(continuation, details, request)

        def intercept_stream_unary(
            self, continuation: Any, details: Any, request_iterator: Any
        ) -> Any:
            return self._pass(continuation, details, request_iterator)

        def intercept_stream_stream(
            self, continuation: Any, details: Any, request_iterator: Any
        ) -> Any:
            return self._pass(continuation, details, request_iterator)

    def calls(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        details = args[1] if len(args) > 1 else kwargs.get("details")

        data = describe(getattr(details, "method", None))
        data.update(instance.endpoint)
        wrapture.annotate(**data)

        # The continuation hands back a call object rather than
        # raising: a blocking unary-response call comes back already
        # terminal, successful or not, and its code is the status; a
        # streamed response or a future is still in flight, and its
        # consumption is deliberately not tracked.

        outcome = wrapped(*args, **kwargs)

        try:
            if outcome.done():
                wrapture.annotate(code=outcome.code().name)
        except Exception:
            pass

        return outcome

    def call_binding(door: str) -> wrapture.Binding:
        binding = wrapture.binding(
            ClientTracer,
            f"intercept_{door}",
            label=f"grpc:Channel.{door}",
            category="external",
            leaf=True,
            capture_args="none",
            capture_result="types",
        )
        binding.on_call.decorates(calls)

        return binding

    class ServerTracer(module.ServerInterceptor):
        """The server interceptor: each resolved handler wrapped so
        its run records as a request boundary."""

        def intercept_service(self, continuation: Any, details: Any) -> Any:
            handler = continuation(details)

            if handler is None or not active[0]:
                return handler

            joins = None
            if settings["join"]:
                joins = {
                    str(key): value
                    for key, value in details.invocation_metadata
                    if isinstance(value, str)
                }

            data = describe(details.method)

            return wrap_handler(handler, data, joins)

    def wrap_handler(handler: Any, data: dict[str, Any], joins: Any) -> Any:
        arity, factory = handler_shape(handler)
        inner = getattr(handler, arity)

        def described(context: Any) -> dict[str, Any]:
            seen = dict(data)

            # The peer string is "ipv4:addr:port" or "ipv6:[..]:port";
            # the client address is what the middle carries.

            try:
                peer = context.peer()
                kind, _, address = peer.partition(":")
                if kind in ("ipv4", "ipv6") and address:
                    seen["client"] = address.rpartition(":")[0].strip("[]")
            except Exception:
                pass

            return seen

        if handler.response_streaming:

            def streamed(argument: Any, context: Any) -> Any:
                if not active[0]:
                    yield from inner(argument, context)
                    return

                aborted = None
                with wrapture.block(
                    "grpc", category="server", data=described(context), joins=joins
                ):
                    try:
                        yield from inner(argument, context)
                    except Exception as error:
                        code = code_of(context)
                        if code is None:
                            wrapture.annotate(code="UNKNOWN")
                            raise
                        aborted = error
                        wrapture.annotate(code=code)
                    else:
                        wrapture.annotate(code=code_of(context) or "OK")

                if aborted is not None:
                    raise aborted

            return factory(
                streamed, handler.request_deserializer, handler.response_serializer
            )

        def unary(argument: Any, context: Any) -> Any:
            if not active[0]:
                return inner(argument, context)

            aborted = None
            with wrapture.block(
                "grpc", category="server", data=described(context), joins=joins
            ):
                try:
                    response = inner(argument, context)
                except Exception as error:
                    # An abort set its code on the context and is
                    # control flow: the block records the code and
                    # stays clean, the exception re-raised outside it
                    # for grpc to answer. A code-less exception is a
                    # real failure, recorded on the block beside the
                    # UNKNOWN grpc will answer with.

                    code = code_of(context)
                    if code is None:
                        wrapture.annotate(code="UNKNOWN")
                        raise
                    aborted = error
                    wrapture.annotate(code=code)
                else:
                    wrapture.annotate(code=code_of(context) or "OK")
                    return response

            raise aborted

        return factory(unary, handler.request_deserializer, handler.response_serializer)

    def handler_shape(handler: Any) -> tuple[str, Any]:
        if handler.request_streaming and handler.response_streaming:
            return "stream_stream", module.stream_stream_rpc_method_handler
        if handler.request_streaming:
            return "stream_unary", module.stream_unary_rpc_method_handler
        if handler.response_streaming:
            return "unary_stream", module.unary_stream_rpc_method_handler
        return "unary_unary", module.unary_unary_rpc_method_handler

    def code_of(context: Any) -> Any:
        try:
            code = context.code()
        except Exception:
            return None

        return code.name if code is not None else None

    # The factory patches, behaviour only: each channel comes back
    # wrapped with the client tracer, each server is built with the
    # server tracer prepended to its interceptors.

    def opens_channel(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        channel = wrapped(*args, **kwargs)

        if not active[0]:
            return channel

        target = args[0] if args else kwargs.get("target")

        return module.intercept_channel(channel, ClientTracer(target))

    def builds_server(
        wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        if active[0]:
            if len(args) > 2:
                args = args[:2] + ([ServerTracer(), *args[2]],) + args[3:]
            else:
                existing = kwargs.get("interceptors") or ()
                kwargs["interceptors"] = [ServerTracer(), *existing]

        return wrapped(*args, **kwargs)

    named: dict[str, wrapture.Binding] = {}

    if settings["client"]:
        for name in ("insecure_channel", "secure_channel"):
            factory = wrapture.binding(module, name, when=False)
            factory.on_call.decorates(opens_channel)
            named[name] = factory

        for door in ("unary_unary", "unary_stream", "stream_unary", "stream_stream"):
            named[door] = call_binding(door)

    if settings["server"]:
        factory = wrapture.binding(module, "server", when=False)
        factory.on_call.decorates(builds_server)
        named["server"] = factory

    if not named:
        return

    group = wrapture.bindings(**named)
    group.apply()

    def cleanup() -> None:
        active[0] = False
        group.remove()

    instrumentation.on_cleanup(cleanup)
