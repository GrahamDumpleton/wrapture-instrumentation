"""An in-process WSGI driver: the server's side of PEP 3333, for tests.

Framework test clients drive an application in process too, but they
own the moment the response iterable is consumed and closed, and
that moment is what a request event's closing line is tied to. This
driver makes the moment explicit and plays the server's part exactly:
a complete environ, a `start_response` that honours the exc_info
re-invocation rule and returns a working `write` callable, iteration
of the result chunk by chunk, and a `close()` that is always called,
including when iteration raised or was abandoned early. It never
reads ahead of the caller and never buffers on the application's
behalf.

    response = request(app, "GET", "/quote/widget")
    assert response.status == "200 OK"
    assert response.body == b"..."

    response = request(app, "GET", "/export", consume=False)
    ...                      # the request is still in flight here
    response.read()
    response.close()
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

StartResponse = Callable[..., Callable[[bytes], object]]
WSGIApplication = Callable[[dict[str, Any], StartResponse], Iterable[bytes]]


class Response:
    """What the driver hands back: the status and headers as the
    application reported them, the body as consumed so far, and the
    controls for consuming the rest.

    `status` and `headers` are None until the application has called
    `start_response`, which a generator-style application may not do
    until its first chunk is pulled. `exc_info` is whatever the last
    `start_response` invocation passed. `body` is every byte so far,
    from `write()` and from iteration, and `chunks` the iterated
    pieces alone. `closed` says whether `close()` has run, and
    `errors` is the `wsgi.errors` stream the application wrote to.
    """

    def __init__(self, environ: dict[str, Any]) -> None:
        self.environ = environ
        self.status: str | None = None
        self.headers: list[tuple[str, str]] | None = None
        self.exc_info: Any = None
        self.chunks: list[bytes] = []
        self.closed = False
        self.errors: Any = environ.get("wsgi.errors")

        self._written: list[bytes] = []
        self._headers_sent = False
        self._result: Iterable[bytes] | None = None
        self._iterator: Iterator[bytes] | None = None

    @property
    def body(self) -> bytes:
        """Every byte delivered so far, written or iterated."""

        return b"".join(self._written) + b"".join(self.chunks)

    @property
    def text(self) -> str:
        """The body decoded as UTF-8."""

        return self.body.decode("utf-8")

    @property
    def code(self) -> int | None:
        """The numeric status, or None before `start_response`."""

        if self.status is None:
            return None

        return int(self.status.split(" ", 1)[0])

    def header(self, name: str) -> str | None:
        """The value of the named response header, matched without
        regard to case, or None."""

        if self.headers is None:
            return None

        wanted = name.lower()
        for key, value in self.headers:
            if key.lower() == wanted:
                return value

        return None

    def read(self, count: int | None = None) -> bytes:
        """Pull chunks from the application's iterable, all of them by
        default or at most `count`, and return the body so far.

        An exception the iterable raises propagates; the caller (or
        `request()` on the default path) still owes a `close()`.
        """

        if self._result is None:
            raise RuntimeError("the application has not been called")

        if self._iterator is None:
            self._iterator = iter(self._result)

        pulled = 0
        for chunk in self._iterator:
            # The application must have called start_response before
            # its first chunk; the first chunk commits the headers.

            if self.status is None:
                raise AssertionError(
                    "the application yielded a body chunk before start_response"
                )

            self._headers_sent = True
            self.chunks.append(chunk)

            pulled += 1
            if count is not None and pulled >= count:
                break

        return self.body

    def close(self) -> None:
        """Call the iterable's `close()` if it has one, once, as the
        server must whether iteration finished, failed or was
        abandoned."""

        if self.closed:
            return

        self.closed = True

        result = self._result
        if result is not None and hasattr(result, "close"):
            result.close()

    def _start_response(
        self,
        status: str,
        headers: Iterable[tuple[str, str]],
        exc_info: Any = None,
    ) -> Callable[[bytes], object]:
        # The re-invocation rule: a second call must carry exc_info,
        # and once headers have been sent it can only re-raise.

        if exc_info is not None:
            if self._headers_sent:
                raise exc_info[1].with_traceback(exc_info[2])
        elif self.status is not None:
            raise AssertionError("start_response called twice without exc_info")

        self.status = status
        self.headers = list(headers)
        self.exc_info = exc_info

        return self._write

    def _write(self, data: bytes) -> None:
        # The deprecated imperative body: bytes delivered ahead of the
        # iterable, which commit the headers as a chunk would.

        if self.status is None:
            raise AssertionError("write() called before start_response")

        self._headers_sent = True
        self._written.append(data)


def environ_for(
    method: str = "GET",
    path: str = "/",
    *,
    query: str = "",
    headers: Iterable[tuple[str, str]] = (),
    body: bytes = b"",
) -> dict[str, Any]:
    """Build a complete PEP 3333 environ for one request.

    The CGI variables and the wsgi.* keys are all present; request
    headers become `HTTP_*` keys except Content-Type and
    Content-Length, which become `CONTENT_TYPE` and `CONTENT_LENGTH`,
    and a body sets `CONTENT_LENGTH` when no header did.
    """

    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "localhost",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }

    for name, value in headers:
        key = name.upper().replace("-", "_")
        if key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            environ[key] = value
        else:
            environ[f"HTTP_{key}"] = value

    if body and "CONTENT_LENGTH" not in environ:
        environ["CONTENT_LENGTH"] = str(len(body))

    return environ


def request(
    app: WSGIApplication,
    method: str = "GET",
    path: str = "/",
    *,
    query: str = "",
    headers: Iterable[tuple[str, str]] = (),
    body: bytes = b"",
    environ: Mapping[str, Any] | None = None,
    consume: bool = True,
) -> Response:
    """Call the application once, as a server would, and return the
    `Response`.

    By default the body is read in full and the iterable closed
    before returning, the `close()` happening even if reading raised.
    With `consume=False` the application has been called but nothing
    has been pulled from its iterable: the caller reads and closes.
    `environ` supplies extra or overriding keys, applied last.
    """

    built = environ_for(method, path, query=query, headers=headers, body=body)
    if environ:
        built.update(environ)

    response = Response(built)
    response._result = app(built, response._start_response)

    if consume:
        try:
            response.read()
        finally:
            response.close()

    return response
