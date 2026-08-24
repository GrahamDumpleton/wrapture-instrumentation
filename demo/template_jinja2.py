"""Drive a Jinja2 environment with the instrumentation applied.

The instrumentation is resolved by its entry point name, and the
environment is built after it applies. The renders cover every form:
a cold render (the load and compile pipeline beneath it), a warm
render (cache hit, load only), a string template, a streamed render,
and the async pair; the render context is masked and outputs report
only their sizes.

Two views of the run always print: the live stream and the tree
reconstructed with timings. With --otel the same events also export
as OpenTelemetry spans to a local OTLP endpoint (http://localhost:4318
unless OTEL_EXPORTER_OTLP_ENDPOINT says otherwise).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import wrapture

TEMPLATES = {
    "page.html": "<p>Hello {{ person }}</p>",
    "rows.csv": "{% for item, price in rows %}{{ item }},{{ price }}\n{% endfor %}",
}


def add_otel_sink() -> None:
    """Register the OpenTelemetry sink; exits with guidance when the
    optional dependencies are missing."""

    try:
        import wrapture.otel
    except ImportError as error:
        raise SystemExit(
            "the OpenTelemetry dependencies are not installed; run the"
            " demo through `just demo-jinja2 --otel`, which overlays"
            " wrapture[otel] for the run"
        ) from error

    wrapture.add_sink(wrapture.otel.sink(service_name="wrapture-jinja2-demo"))


def main(arguments: list[str] | None = None) -> None:
    """Run the demo: apply the instrumentation, drive the renders,
    print the live stream and the tree, and flush any exporters."""

    parser = argparse.ArgumentParser(
        prog="demo.template_jinja2",
        description="Drive a Jinja2 environment with the instrumentation"
        " applied, printing the live stream and the tree.",
    )
    parser.add_argument(
        "--otel",
        action="store_true",
        help="also export the events as OpenTelemetry spans over OTLP",
    )
    options = parser.parse_args(arguments)

    if options.otel:
        add_otel_sink()

    wrapture.add_sink(wrapture.Printer(stream=sys.stdout))

    print("== live stream ==")

    with wrapture.instrumentation("jinja2"), wrapture.timeline() as tape:
        import jinja2

        env = jinja2.Environment(loader=jinja2.DictLoader(TEMPLATES), enable_async=True)

        env.get_template("page.html").render(person="pat")
        env.get_template("page.html").render(person="quinn")
        env.from_string("<em>{{ count }} items</em>").render(count=2)

        for _ in env.get_template("rows.csv").generate(
            rows=[("widget", 25), ("gadget", 120)]
        ):
            pass

        async def drive() -> None:
            await env.get_template("page.html").render_async(person="ari")

        asyncio.run(drive())

    print()
    print("== tree ==")
    print(tape.tree(times=True))

    wrapture.shutdown()

    if options.otel:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        print()
        print("== otel ==")
        print(f"spans flushed to {endpoint} as service wrapture-jinja2-demo")


if __name__ == "__main__":
    main()
