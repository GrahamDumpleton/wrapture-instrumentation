"""A local gRPC service for the suite to make real calls against:
generic handlers over raw bytes, no protobuf involved, every call
shape covered.

The methods, all under the `demo.Echo` service: `Shout` (unary-unary,
uppercases), `Fail` (unary-unary, aborts NOT_FOUND), `Boom`
(unary-unary, raises), `Count` (unary-stream, yields three chunks),
`Sum` (stream-unary, adds integer chunks), `Chat` (stream-stream,
uppercases each chunk). The handler lookup records each request's
invocation metadata for the propagation tests to read back.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import grpc


@dataclass
class Service:
    """The service's address and the metadata each RPC arrived with."""

    address: str
    metadata: list[dict[str, str]] = field(default_factory=list)

    def header(self, index: int, name: str) -> str | None:
        """A metadata value of the index-th RPC received, case
        insensitively, or None when it was not sent."""

        wanted = name.casefold()

        for key, value in self.metadata[index].items():
            if key.casefold() == wanted:
                return value

        return None


def _handlers(service: Service) -> grpc.GenericRpcHandler:
    def shout(request: bytes, context: Any) -> bytes:
        return request.upper()

    def fail(request: bytes, context: Any) -> bytes:
        context.abort(grpc.StatusCode.NOT_FOUND, "gone")
        raise AssertionError("abort returns by raising")

    def boom(request: bytes, context: Any) -> bytes:
        raise RuntimeError("handler blew up")

    def count(request: bytes, context: Any) -> Iterator[bytes]:
        for index in range(3):
            yield request + b"-" + str(index).encode()

    def summed(request_iterator: Iterator[bytes], context: Any) -> bytes:
        total = sum(int(chunk) for chunk in request_iterator)

        return str(total).encode()

    def chat(request_iterator: Iterator[bytes], context: Any) -> Iterator[bytes]:
        for chunk in request_iterator:
            yield chunk.upper()

    table = {
        "/demo.Echo/Shout": grpc.unary_unary_rpc_method_handler(shout),
        "/demo.Echo/Fail": grpc.unary_unary_rpc_method_handler(fail),
        "/demo.Echo/Boom": grpc.unary_unary_rpc_method_handler(boom),
        "/demo.Echo/Count": grpc.unary_stream_rpc_method_handler(count),
        "/demo.Echo/Sum": grpc.stream_unary_rpc_method_handler(summed),
        "/demo.Echo/Chat": grpc.stream_stream_rpc_method_handler(chat),
    }

    class Handler(grpc.GenericRpcHandler):
        def service(self, handler_call_details: Any) -> Any:
            service.metadata.append(
                {
                    str(key): value
                    for key, value in handler_call_details.invocation_metadata
                    if isinstance(value, str)
                }
            )

            return table.get(handler_call_details.method)

    return Handler()


def serve() -> Iterator[Service]:
    """Start the service on a loopback port, yield it, stop it after.

    The caller decides when this runs: a server built while the
    instrumentation is applied carries the injected interceptor, one
    built outside does not.
    """

    server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=4))
    port = server.add_insecure_port("127.0.0.1:0")

    record = Service(f"127.0.0.1:{port}")
    server.add_generic_rpc_handlers((_handlers(record),))
    server.start()

    try:
        yield record
    finally:
        server.stop(None)
