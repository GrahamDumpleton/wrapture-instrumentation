"""A local HTTP server for the urllib suite to make real requests
against, recording what each request arrived with.

Real requests over a loopback socket are the honest test of a client
instrumentation: what the opener does with a redirect, an error
status or a body only shows when a server answers. The server is the
standard library's own, threaded so a redirect's second request can
be served while the first is still in flight, and every request it
sees is kept as a Received record for the tests to read back.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(frozen=True)
class Received:
    """One request as the server saw it."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes


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


def _handler(server: Server) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _record(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""

            server.received.append(
                Received(
                    self.command,
                    self.path,
                    {name: value for name, value in self.headers.items()},
                    body,
                )
            )

        def _reply(self, status: int, body: bytes = b"", **headers: str) -> None:
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name.replace("_", "-"), value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _route(self) -> None:
            self._record()
            path = self.path.partition("?")[0]

            if path == "/ok":
                self._reply(200, b"ok")
            elif path == "/redirect":
                self._reply(302, Location="/ok")
            elif path == "/missing":
                self._reply(404, b"no such thing")
            elif path == "/broken":
                self._reply(500, b"boom")
            elif path == "/echo":
                self._reply(200, server.received[-1].body)
            else:
                self._reply(404)

        do_GET = _route
        do_POST = _route
        do_PUT = _route

    return Handler


def serve() -> Iterator[Server]:
    """Run the server on a loopback port for the duration of the
    iteration, yielding its record."""

    server = Server(url="")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(server))
    server.url = f"http://127.0.0.1:{httpd.server_address[1]}"

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield server
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()
