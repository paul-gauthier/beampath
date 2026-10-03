from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

import pytest

from scripts import rebuild_docs


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checkout(tmp_path):
    project = tmp_path / "checkout"
    project.mkdir()
    for name in rebuild_docs.DOCUMENTS:
        destination = project / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Stale blocks make premature writes on a later failure observable.
        text = (PROJECT / name).read_text()
        text = re.sub(r"^(<!-- DOCS:BEGIN \w+ -->)$.*?^(<!-- DOCS:END \w+ -->)$",
                      r"\1\nstale snippet\n\2", text, flags=re.DOTALL | re.MULTILINE)
        destination.write_text(text)
    shutil.copytree(PROJECT / "examples", project / "examples",
                    ignore=shutil.ignore_patterns("images", "__pycache__"))
    images = project / "examples" / "images"
    images.mkdir()
    for name in rebuild_docs.EXAMPLES:
        (images / f"{name}.png").write_bytes(f"old {name}".encode())
    return project


def output_snapshot(project):
    paths = [*(project / name for name in rebuild_docs.DOCUMENTS),
             *sorted((project / "examples" / "images").glob("*.png"))]
    return {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}


def test_extract_multiple_regions_preserves_internal_indentation():
    source = '''ignored = True
# DOCS:BEGIN
def helper():
    return 1
# DOCS:END

def build():
    """Do not include this wrapper."""
    # DOCS:BEGIN
    values = (
        helper(),
        2,
    )
    # DOCS:END
    return values
'''
    assert rebuild_docs.extract_snippet(source, "example.py") == (
        "def helper():\n    return 1\n\nvalues = (\n    helper(),\n    2,\n)"
    )


@pytest.mark.parametrize("source", [
    "value = 1\n",
    "# DOCS:END\n",
    "# DOCS:BEGIN\nvalue = 1\n",
    "# DOCS:BEGIN\n# DOCS:BEGIN\n# DOCS:END\n",
    "# DOCS:BEGIN\n\n# DOCS:END\n",
    "# DOCS:START\nvalue = 1\n# DOCS:END\n",
])
def test_invalid_source_regions_report_filename(source):
    with pytest.raises(ValueError, match="example.py"):
        rebuild_docs.extract_snippet(source, "example.py")


def test_real_snippets_include_supporting_code_and_match_documents():
    assert set(rebuild_docs.SAVE_CALLS) < set(rebuild_docs.EXAMPLES)
    for name in rebuild_docs.DOCUMENTS:
        document = (PROJECT / name).read_text(encoding="utf-8")
        assert rebuild_docs.update_document(document, PROJECT, name) == document
    rendering = rebuild_docs.extract_snippet(
        (PROJECT / "examples" / "rendering.py").read_text(), "rendering.py")
    assert 'STYLE = Style(' in rendering
    assert 'layout = path.layout(style=STYLE)' in rendering
    assert 'def build' not in rendering
    custom = rebuild_docs.extract_snippet(
        (PROJECT / "examples" / "custom_component.py").read_text(), "custom_component.py")
    assert 'def fork_geometry' in custom
    assert 'register_component(ComponentDefinition(' in custom
    assert 'fork.out("down") >> QWP()' in custom
    assert 'run_example' not in custom


@pytest.mark.parametrize("filename,name", [
    ("README.md", "hello"), ("docs/guide.md", "mzi"),
    ("docs/reference.md", "custom_component"),
])
def test_update_preserves_prose_links_and_unmarked_code(checkout, filename, name):
    marker = f"<!-- DOCS:BEGIN {name} -->"
    end = f"<!-- DOCS:END {name} -->"
    original = (checkout / filename).read_text()
    before, rest = original.split(marker, 1)
    _, after = rest.split(end, 1)
    stale = before + marker + "\nobsolete snippet\n" + end + after
    updated = rebuild_docs.update_document(stale, checkout, filename)
    pattern = r"(<!-- DOCS:BEGIN \w+ -->).*?(<!-- DOCS:END \w+ -->)"
    assert re.sub(pattern, r"\1\2", updated, flags=re.DOTALL) == (
        re.sub(pattern, r"\1\2", stale, flags=re.DOTALL)
    )
    assert "obsolete snippet" not in updated


def test_documents_can_select_examples_independently_or_have_no_blocks(checkout):
    block = "<!-- DOCS:BEGIN hello -->\nold\n<!-- DOCS:END hello -->\n"
    for filename in ("README.md", "docs/guide.md"):
        updated = rebuild_docs.update_document(block, checkout, filename)
        assert 'setup.save("hello.svg")' in updated
        assert rebuild_docs.update_document(updated, checkout, filename) == updated
    prose = "# Notes\n\nA document without generated code.\n"
    assert rebuild_docs.update_document(prose, checkout, "notes.md") == prose


@pytest.mark.parametrize("replacement", [
    "<!-- DOCS:BEGIN unknown -->",
    "<!-- DOCS:BEGIN -->",
    "<!-- DOCS:END hello -->",
    "<!-- DOCS:BEGIN hello -->\n<!-- DOCS:BEGIN mzi -->",
    "",
])
@pytest.mark.parametrize("filename,name", [
    ("README.md", "hello"), ("docs/guide.md", "mzi"),
    ("docs/reference.md", "custom_component"),
])
def test_invalid_document_never_renders_or_replaces_outputs(checkout, monkeypatch, replacement, filename, name):
    document = checkout / filename
    document.write_text(document.read_text().replace(
        f"<!-- DOCS:BEGIN {name} -->", replacement.replace("hello", name), 1))
    before = output_snapshot(checkout)
    monkeypatch.setattr(rebuild_docs, "render_examples", lambda *args: pytest.fail("rendered invalid document"))
    with pytest.raises(ValueError, match=re.escape(filename)):
        rebuild_docs.rebuild_docs(checkout)
    assert output_snapshot(checkout) == before
    assert not (checkout / "build").exists()


@pytest.mark.parametrize("name", ["hello", "custom_component"])
def test_invalid_source_never_renders_or_replaces_outputs(checkout, monkeypatch, name):
    source = checkout / "examples" / f"{name}.py"
    source.write_text(source.read_text().replace("# DOCS:END", "# DOCS:BAD", 1))
    before = output_snapshot(checkout)
    monkeypatch.setattr(rebuild_docs, "render_examples", lambda *args: pytest.fail("rendered invalid source"))
    with pytest.raises(ValueError, match=f"{name}.py"):
        rebuild_docs.rebuild_docs(checkout)
    assert output_snapshot(checkout) == before


def test_invalid_extracted_python_never_replaces_outputs(checkout, monkeypatch):
    source = checkout / "examples" / "hello.py"
    source.write_text(source.read_text().replace('    setup = (', '    setup = )', 1))
    before = output_snapshot(checkout)
    monkeypatch.setattr(rebuild_docs, "render_examples", lambda *args: pytest.fail("rendered invalid snippet"))
    with pytest.raises(ValueError, match="invalid documentation snippet"):
        rebuild_docs.rebuild_docs(checkout)
    assert output_snapshot(checkout) == before


def test_render_failure_keeps_all_outputs_and_cleans_staging(checkout, monkeypatch):
    before = output_snapshot(checkout)

    def fail_after_one_image(project, output):
        (output / "hello.png").write_bytes(b"partial render")
        raise RuntimeError("Cairo unavailable")

    monkeypatch.setattr(rebuild_docs, "render_examples", fail_after_one_image)
    with pytest.raises(RuntimeError, match="Cairo unavailable"):
        rebuild_docs.rebuild_docs(checkout)
    assert output_snapshot(checkout) == before
    assert list((checkout / "build").iterdir()) == []


def test_incomplete_render_keeps_all_outputs(checkout, monkeypatch):
    before = output_snapshot(checkout)

    def incomplete_render(project, output):
        for name in rebuild_docs.EXAMPLES:
            if name != "cage":
                (output / f"{name}.png").write_bytes(b"new preview")

    monkeypatch.setattr(rebuild_docs, "render_examples", incomplete_render)
    with pytest.raises(FileNotFoundError, match="cage.png"):
        rebuild_docs.rebuild_docs(checkout)
    assert output_snapshot(checkout) == before


def test_success_updates_all_outputs_and_preserves_mtimes_on_second_run(checkout, monkeypatch):
    calls = []

    def render(project, output):
        calls.append(output)
        for name in rebuild_docs.EXAMPLES:
            (output / f"{name}.png").write_bytes(f"new {name}".encode())

    monkeypatch.setattr(rebuild_docs, "render_examples", render)
    rebuild_docs.rebuild_docs(checkout)
    snapshot = output_snapshot(checkout)
    for filename in rebuild_docs.DOCUMENTS:
        text = (checkout / filename).read_text()
        assert "stale snippet" not in text
        assert rebuild_docs.update_document(text, checkout, filename) == text
    for name in rebuild_docs.EXAMPLES:
        assert (checkout / "examples" / "images" / f"{name}.png").read_bytes() == f"new {name}".encode()
    rebuild_docs.rebuild_docs(checkout)
    assert output_snapshot(checkout) == snapshot
    assert len(calls) == 2


def test_renderer_reports_cause_without_child_traceback(monkeypatch, tmp_path):
    def fail(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=(
            "Traceback (most recent call last):\n"
            "RuntimeError: PNG export requires beampath[png] and native Cairo\n"
        ))

    monkeypatch.setattr(rebuild_docs.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="beampath\\[png\\]") as error:
        rebuild_docs.render_examples(tmp_path, tmp_path)
    assert "Traceback" not in str(error.value)
    assert "macOS library-path" in str(error.value)


def test_cli_rebuilds_all_previews_from_another_directory_and_is_idempotent(checkout, tmp_path):
    try:
        import cairosvg
    except (ImportError, OSError):
        pytest.skip("Optional PNG converter or native Cairo is unavailable")
    from PIL import Image

    scripts = checkout / "scripts"
    scripts.mkdir()
    helper = scripts / "rebuild_docs.py"
    shutil.copy(PROJECT / "scripts" / "rebuild_docs.py", helper)
    command = [sys.executable, str(helper)]
    first = subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
    assert f"{len(rebuild_docs.DOCUMENTS)} documentation pages" in first.stdout
    assert f"{len(rebuild_docs.EXAMPLES)} previews" in first.stdout
    snapshot = output_snapshot(checkout)
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
    assert output_snapshot(checkout) == snapshot
    assert list((checkout / "build").iterdir()) == []
    for name in rebuild_docs.EXAMPLES:
        with Image.open(checkout / "examples" / "images" / f"{name}.png") as image:
            assert image.width == 2400
            assert image.info["dpi"] == pytest.approx((600, 600), abs=.02)
            assert json.loads(image.info["beampath-attribution"])["assets"]
