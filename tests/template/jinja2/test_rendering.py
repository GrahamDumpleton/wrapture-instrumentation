"""What the instrumentation records: renders in every form, the
loading pipeline beneath get_template, and what the events capture
and deliberately do not."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import jinja2
import pytest
from wrapture import Tape, instrumentation, timeline

from wrapture_instrumentation.template.jinja2 import Jinja2Instrumentation

TEMPLATES = {
    "page.html": "<p>Hello {{ person }}</p>",
    "rows.html": "{% for row in rows %}{{ row }}\n{% endfor %}",
}


def make_env(enable_async: bool = False) -> jinja2.Environment:
    """A fresh environment over the in-memory templates, so each test
    gets its own template cache."""

    return jinja2.Environment(
        loader=jinja2.DictLoader(TEMPLATES), enable_async=enable_async
    )


@pytest.fixture
def tape() -> Iterator[Tape]:
    with instrumentation(Jinja2Instrumentation), timeline() as recorded:
        yield recorded


def test_a_cold_render_shows_the_whole_pipeline(tape: Tape) -> None:
    env = make_env()
    text = env.get_template("page.html").render(person="pat")

    assert text == "<p>Hello pat</p>"

    (load, compiled, render) = tape.all
    assert load.path == "jinja2.environment:Environment._load_template"
    assert compiled.path == "jinja2.environment:Environment.compile"
    assert render.path == "jinja2.environment:Template.render"
    assert render.label is None

    # The compile happens inside the cold load; the render follows as
    # its own root once the template is in hand.

    assert tape.parent_of(compiled) is load
    assert tape.parent_of(render) is None


def test_a_warm_load_skips_the_compile(tape: Tape) -> None:
    env = make_env()
    env.get_template("page.html")
    env.get_template("page.html")

    paths = [event.path for event in tape.all]
    assert paths == [
        "jinja2.environment:Environment._load_template",
        "jinja2.environment:Environment.compile",
        "jinja2.environment:Environment._load_template",
    ]


def test_the_render_is_annotated_and_the_context_is_not_captured(
    tape: Tape,
) -> None:
    env = make_env()
    env.get_template("page.html").render(person="secret-person")

    (*_, render) = tape.all
    assert render.data["template"] == "page.html"
    assert render.result == "<26 chars>"
    assert "secret-person" not in repr(render.arguments)
    assert "secret-person" not in repr(render.data)


def test_a_string_template_compiles_without_a_load(tape: Tape) -> None:
    env = make_env()
    text = env.from_string("{{ x }}!").render(x=9)

    assert text == "9!"

    (compiled, render) = tape.all
    assert compiled.path == "jinja2.environment:Environment.compile"
    assert render.path == "jinja2.environment:Template.render"
    assert render.data["template"] == "<template>"


def test_the_compile_source_is_truncated(tape: Tape) -> None:
    env = make_env()
    env.from_string("{{ x }}" + "y" * 100)

    (compiled,) = tape.all
    assert compiled.arguments is not None

    captured = compiled.arguments["source"]
    assert len(captured) == 60
    assert captured.endswith("...")


def test_a_generate_records_around_the_iteration(tape: Tape) -> None:
    env = make_env()
    chunks = list(env.get_template("rows.html").generate(rows=[1, 2, 3]))

    assert "".join(chunks) == "1\n2\n3\n"

    (*_, render) = tape.all
    assert render.path == "jinja2.environment:Template.generate"

    # The chunk count is the template's output nodes (each value and
    # each newline yields), not the loop count.

    assert render.items == 6
    assert render.duration is not None


def test_the_async_forms_record(tape: Tape) -> None:
    env = make_env(enable_async=True)

    async def drive() -> tuple[str, list[str]]:
        text = await env.get_template("page.html").render_async(person="pat")
        chunks = [
            chunk
            async for chunk in env.get_template("rows.html").generate_async(rows=[1, 2])
        ]
        return text, chunks

    text, chunks = asyncio.run(drive())

    assert text == "<p>Hello pat</p>"
    assert "".join(chunks) == "1\n2\n"

    renders = [
        event
        for event in tape.all
        if event.path
        in (
            "jinja2.environment:Template.render_async",
            "jinja2.environment:Template.generate_async",
        )
    ]
    assert [event.path.rpartition(".")[2] for event in renders] == [
        "render_async",
        "generate_async",
    ]
    assert renders[0].result == "<16 chars>"
    assert renders[1].items == 4


def test_a_file_loaded_template_annotates_its_path(tape: Tape, tmp_path: Path) -> None:
    (tmp_path / "disk.html").write_text("from disk")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(tmp_path))

    env.get_template("disk.html").render()

    (load, *_) = tape.all
    assert load.path == "jinja2.environment:Environment._load_template"
    assert load.data["template"] == "disk.html"
    assert load.data["path"] == str(tmp_path / "disk.html")


def test_loading_off_leaves_only_the_renders() -> None:
    with (
        instrumentation(Jinja2Instrumentation, loading=False),
        timeline() as tape,
    ):
        env = make_env()
        env.get_template("page.html").render(person="pat")

    assert [event.path for event in tape.all] == ["jinja2.environment:Template.render"]
