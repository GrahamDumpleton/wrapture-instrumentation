"""Demonstration scripts, one per instrumented target.

Each module drives a small application with its target's
instrumentation applied, streaming every recorded event live and
printing the reconstructed tree at the end, so the instrumentation
can be verified by eye rather than by assertion. Run from the
repository root as a module, so the tests package (whose application
and WSGI driver the demos reuse) imports cleanly:

    uv run python -m demo.framework_flask

or through the Justfile target, which also carries the OpenTelemetry
dependencies for the --otel flag:

    just demo-flask
    just demo-flask --otel
"""
