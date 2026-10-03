from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

import pytest

from scripts import rebuild_readme


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checkout(tmp_path):
    project = tmp_path / "checkout"
    project.mkdir()
    shutil.copy(PROJECT / "README.md", project / "README.md")
    shutil.copytree(PROJECT / "examples", project / "examples",
                    ignore=shutil.ignore_patterns("images", "__pycache__"))
    images = project / "examples" / "images"
    images.mkdir()
    for name in rebuild_readme.SAVE_CALLS:
        (images / f"{name}.png").write_bytes(f"old {name}".encode())
    return project


def output_snapshot(project):
    paths = [project / "README.md", *sorted((project / "examples" / "images").glob("*.png"))]
    return {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}


def test_extract_multiple_regions_preserves_internal_indentation():
    source = '''ignored = True
# README:BEGIN
def helper():
    return 1
# README:END

def build():
    """Do not include this wrapper."""
    # README:BEGIN
    values = (
        helper(),
        2,
    )
    # README:END
    return values
'''
    assert rebuild_readme.extract_snippet(source, "example.py") == (
        "def helper():\n    return 1\n\nvalues = (\n    helper(),\n    2,\n)"
    )


@pytest.mark.parametrize("source", [
    "value = 1\n",
    "# README:END\n",
    "# README:BEGIN\nvalue = 1\n",
    "# README:BEGIN\n# README:BEGIN\n# README:END\n",
    "# README:BEGIN\n\n# README:END\n",
    "# README:START\nvalue = 1\n# README:END\n",
])
def test_invalid_source_regions_report_filename(source):
    with pytest.raises(ValueError, match="example.py"):
        rebuild_readme.extract_snippet(source, "example.py")


def test_real_snippets_include_supporting_code_and_match_readme():
    from beampath.examples.__main__ import EXAMPLES

    assert set(rebuild_readme.SAVE_CALLS) == set(EXAMPLES)
    readme = (PROJECT / "README.md").read_text(encoding="utf-8")
    assert rebuild_readme.update_readme(readme, PROJECT) == readme
    rendering = rebuild_readme.extract_snippet(
        (PROJECT / "examples" / "rendering.py").read_text(), "rendering.py")
    assert 'STYLE = Style(' in rendering
    assert 'layout = path.layout(style=STYLE)' in rendering
    assert 'def build' not in rendering
    custom = rebuild_readme.extract_snippet(
        (PROJECT / "examples" / "custom_component.py").read_text(), "custom_component.py")
    assert 'def fork_geometry' in custom
    assert 'register_component(ComponentDefinition(' in custom
    assert 'fork.out("down") >> QWP()' in custom
    assert 'run_example' not in custom


def test_update_preserves_prose_links_and_unmarked_code(checkout):
    marker = "<!-- README:BEGIN hello -->"
    end = "<!-- README:END hello -->"
    original = (checkout / "README.md").read_text()
    before, rest = original.split(marker, 1)
    _, after = rest.split(end, 1)
    stale = before + marker + "\nobsolete snippet\n" + end + after
    updated = rebuild_readme.update_readme(stale, checkout)
    pattern = r"(<!-- README:BEGIN \w+ -->).*?(<!-- README:END \w+ -->)"
    assert re.sub(pattern, r"\1\2", updated, flags=re.DOTALL) == (
        re.sub(pattern, r"\1\2", stale, flags=re.DOTALL)
    )
    assert "obsolete snippet" not in updated


@pytest.mark.parametrize("replacement", [
    "<!-- README:BEGIN unknown -->",
    "<!-- README:BEGIN -->",
    "<!-- README:END hello -->",
    "<!-- README:BEGIN hello -->\n<!-- README:BEGIN cage -->",
    "",
])
def test_invalid_readme_never_renders_or_replaces_outputs(checkout, monkeypatch, replacement):
    readme = checkout / "README.md"
    readme.write_text(readme.read_text().replace("<!-- README:BEGIN hello -->", replacement, 1))
    before = output_snapshot(checkout)
    monkeypatch.setattr(rebuild_readme, "render_examples", lambda *args: pytest.fail("rendered invalid README"))
    with pytest.raises(ValueError, match="README.md"):
        rebuild_readme.rebuild_readme(checkout)
    assert output_snapshot(checkout) == before
    assert not (checkout / "build").exists()


def test_invalid_source_never_renders_or_replaces_outputs(checkout, monkeypatch):
    source = checkout / "examples" / "hello.py"
    source.write_text(source.read_text().replace("# README:END", "# README:BAD", 1))
    before = output_snapshot(checkout)
    monkeypatch.setattr(rebuild_readme, "render_examples", lambda *args: pytest.fail("rendered invalid source"))
    with pytest.raises(ValueError, match="hello.py"):
        rebuild_readme.rebuild_readme(checkout)
    assert output_snapshot(checkout) == before


def test_invalid_extracted_python_never_replaces_outputs(checkout, monkeypatch):
    source = checkout / "examples" / "hello.py"
    source.write_text(source.read_text().replace('    setup = (', '    setup = )', 1))
    before = output_snapshot(checkout)
    monkeypatch.setattr(rebuild_readme, "render_examples", lambda *args: pytest.fail("rendered invalid snippet"))
    with pytest.raises(ValueError, match="invalid README snippet"):
        rebuild_readme.rebuild_readme(checkout)
    assert output_snapshot(checkout) == before


def test_render_failure_keeps_all_outputs_and_cleans_staging(checkout, monkeypatch):
    before = output_snapshot(checkout)

    def fail_after_one_image(project, output):
        (output / "hello.png").write_bytes(b"partial render")
        raise RuntimeError("Cairo unavailable")

    monkeypatch.setattr(rebuild_readme, "render_examples", fail_after_one_image)
    with pytest.raises(RuntimeError, match="Cairo unavailable"):
        rebuild_readme.rebuild_readme(checkout)
    assert output_snapshot(checkout) == before
    assert list((checkout / "build").iterdir()) == []


def test_incomplete_render_keeps_all_outputs(checkout, monkeypatch):
    before = output_snapshot(checkout)

    def incomplete_render(project, output):
        for name in rebuild_readme.SAVE_CALLS:
            if name != "custom_component":
                (output / f"{name}.png").write_bytes(b"new preview")

    monkeypatch.setattr(rebuild_readme, "render_examples", incomplete_render)
    with pytest.raises(FileNotFoundError, match="custom_component.png"):
        rebuild_readme.rebuild_readme(checkout)
    assert output_snapshot(checkout) == before


def test_success_updates_all_outputs_and_preserves_mtimes_on_second_run(checkout, monkeypatch):
    calls = []

    def render(project, output):
        calls.append(output)
        for name in rebuild_readme.SAVE_CALLS:
            (output / f"{name}.png").write_bytes(f"new {name}".encode())

    monkeypatch.setattr(rebuild_readme, "render_examples", render)
    rebuild_readme.rebuild_readme(checkout)
    snapshot = output_snapshot(checkout)
    for name in rebuild_readme.SAVE_CALLS:
        assert (checkout / "examples" / "images" / f"{name}.png").read_bytes() == f"new {name}".encode()
    rebuild_readme.rebuild_readme(checkout)
    assert output_snapshot(checkout) == snapshot
    assert len(calls) == 2


def test_renderer_reports_cause_without_child_traceback(monkeypatch, tmp_path):
    def fail(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=(
            "Traceback (most recent call last):\n"
            "RuntimeError: PNG export requires beampath[png] and native Cairo\n"
        ))

    monkeypatch.setattr(rebuild_readme.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="beampath\\[png\\]") as error:
        rebuild_readme.render_examples(tmp_path, tmp_path)
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
    helper = scripts / "rebuild_readme.py"
    shutil.copy(PROJECT / "scripts" / "rebuild_readme.py", helper)
    command = [sys.executable, str(helper)]
    first = subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
    assert f"{len(rebuild_readme.SAVE_CALLS)} previews" in first.stdout
    snapshot = output_snapshot(checkout)
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
    assert output_snapshot(checkout) == snapshot
    assert list((checkout / "build").iterdir()) == []
    for name in rebuild_readme.SAVE_CALLS:
        with Image.open(checkout / "examples" / "images" / f"{name}.png") as image:
            assert image.width == 2400
            assert image.info["dpi"] == pytest.approx((600, 600), abs=.02)
            assert json.loads(image.info["beampath-attribution"])["assets"]
