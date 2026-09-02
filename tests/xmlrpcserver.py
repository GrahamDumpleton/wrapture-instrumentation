"""A local XML-RPC server for the xmlrpc suites to make real calls
against, recording what each request arrived with.

The standard library's own SimpleXMLRPCServer, threaded, with a
handler that keeps every request's method, path and headers as a
Received record for the tests to read back. Three procedures:
echo returns its argument, inventory.count returns an int through a
dotted name, and boom raises, which the server answers as a Fault.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer


@dataclass(frozen=True)
class Received:
    """One request as the server saw it."""

    method: str
    path: str
    headers: dict[str, str]


@dataclass
class Server:
    """The server's address and the requests it has received."""

    url: str
    received: list[Received] = field(default_factory=list)

    def header(self, index: int, name: str) -> str | None:
        """A header of the index-th request received, case
        insensitively, or None when it was not sent."""

        wanted = name.casefold()
        headers = self.received[index].headers

        for key, value in headers.items():
            if key.casefold() == wanted:
                return value

        return None


def _handler(server: Server) -> type[SimpleXMLRPCRequestHandler]:
    class Handler(SimpleXMLRPCRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            server.received.append(
                Received(
                    self.command,
                    self.path,
                    {name: value for name, value in self.headers.items()},
                )
            )
            super().do_POST()

    return Handler


def echo(value: Any) -> Any:
    return value


def count(item: str, factor: int) -> int:
    return len(item) * factor


def boom() -> None:
    raise ValueError("the server side broke")


def serve() -> Iterator[Server]:
    """Run the server on a loopback port for the duration of the
    iteration, yielding its record."""

    server = Server(url="")
    httpd = SimpleXMLRPCServer(
        ("127.0.0.1", 0), requestHandler=_handler(server), allow_none=True
    )
    server.url = f"http://127.0.0.1:{httpd.server_address[1]}"

    httpd.register_function(echo, "echo")
    # typeshed's overloads do not model a two-argument procedure
    # registered under a custom name.
    httpd.register_function(count, "inventory.count")  # type: ignore[arg-type]
    httpd.register_function(boom, "boom")
    httpd.register_multicall_functions()

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield server
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()
