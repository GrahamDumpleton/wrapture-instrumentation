"""The http.client patches: one event per phase of an exchange on
HTTPConnection.

An exchange at this level is not one call, so no single event here
carries the external contract, none is a leaf, and none is
categorised: the exchange belongs to whichever higher-level client
event sits above these. What records is the wire work itself:

- HTTPConnection.connect is the socket being established, annotated
  with the host and port. It records nested inside the phase that
  first wrote to the wire, endheaders on a cold connection, and not
  at all on a reused one, so cold and warm exchanges tell apart by
  shape alone. HTTPSConnection overrides connect but calls up to
  this one, so a TLS connection records the same event.

- HTTPConnection.putrequest is the request line. The method passes;
  the url is a path with, possibly, a query string, and the query is
  recorded through wrapture.capture_query(), the built-in sensitive
  names masked and the redact setting's names masked on top.

- HTTPConnection.endheaders is the headers and any body going out on
  the wire; the body reduces to its size.

- HTTPConnection.getresponse is the wait for the status line and
  headers, which is where the latency lives, annotated with the
  status.

request() is deliberately not bound: the convenience wrapper would
double with the phases beneath it, and clients like urllib3 override
it in subclasses, driving the phase methods themselves; those are
reached on the base class either way, so everything is still seen.
putheader is not bound either: header values are where credentials
travel.

There is no trace propagation here. Injecting the trace identity is
the higher-level client's job, and doing it at both layers would
send the headers twice.
"""

from __future__ import annotations

from typing import Any

import wrapture


def stamp_connect(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Annotate the connect event with where the socket goes."""

    wrapture.annotate(host=instance.host, port=instance.port)

    return wrapped(*args, **kwargs)


def stamp_response(
    wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Run getresponse and annotate the status it brought back."""

    response = wrapped(*args, **kwargs)

    status = getattr(response, "status", None)
    if status is not None:
        wrapture.annotate(status=status)

    return response


def instrument(module: Any, instrumentation: wrapture.Instrumentation) -> None:
    """Bind the four phases on HTTPConnection as one group; register
    the group's removal as this trigger's cleanup."""

    # The query policy for putrequest's url: redact() with the
    # setting's names, or the reference level, either way on top of
    # the built-in sensitive set.

    names = tuple(instrumentation.settings["redact"])
    policy: Any = wrapture.redact(*names) if names else "reference"

    def captured(name: str | None, value: Any) -> Any:
        """Bodies reduce to sizes, responses to types, and a url's
        query string is recorded through the query policy."""

        if name == "url" and isinstance(value, str):
            path, sep, query = value.partition("?")
            if not sep:
                return value
            return f"{path}?{wrapture.capture_query(query, policy)}"

        if isinstance(value, (bytes, bytearray, memoryview)):
            return f"<{len(value)} bytes>"

        if name is None and not isinstance(value, (str, int, float, type(None))):
            return f"<{type(value).__name__}>"

        return value

    connection = module.HTTPConnection

    connect = wrapture.binding(connection, "connect", capture_args=captured)
    connect.on_call.decorates(stamp_connect)

    putrequest = wrapture.binding(connection, "putrequest", capture_args=captured)

    endheaders = wrapture.binding(
        connection,
        "endheaders",
        capture_args=captured,
        capture_result=captured,
    )

    getresponse = wrapture.binding(connection, "getresponse", capture_result=captured)
    getresponse.on_call.decorates(stamp_response)

    group = wrapture.bindings(
        connect=connect,
        putrequest=putrequest,
        endheaders=endheaders,
        getresponse=getresponse,
    )
    group.apply()

    instrumentation.on_cleanup(group.remove)
