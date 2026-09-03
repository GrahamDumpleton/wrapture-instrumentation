"""
Instrumentation for common Python packages, applied through wrapture.

Each target package has its own subpackage here, named for its
category and the target (framework_flask, external_requests), holding
one wrapture.Instrumentation subclass registered in the
wrapture.instrumentation entry point group under the bare target name.
This module carries only the version: importing it loads no
instrumentation and no target.
"""


def _format_version(parts: tuple[str, ...]) -> str:
    base = ".".join(parts[:3])

    if len(parts) == 3:
        return base

    suffix = parts[3]
    return (
        f"{base}.{suffix}" if suffix.startswith(("dev", "post")) else f"{base}{suffix}"
    )


__version_info__ = ("1", "0", "0", "a1")
__version__ = _format_version(__version_info__)
