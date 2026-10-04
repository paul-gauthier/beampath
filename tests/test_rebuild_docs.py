from importlib import import_module
from io import BytesIO
from pathlib import Path
import inspect
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from beampath import Style, components
from beampath.examples._discovery import example_names
from scripts import rebuild_docs as docs


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checkout(tmp_path):
    project = tmp_path / "checkout"
    project.mkdir()
    shutil.copytree(PROJECT / "examples", project / "examples",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PROJECT / "docs", project / "docs")
    shutil.copy(PROJECT / "README.md", project / "README.md")
    return project


def snapshot(project):
    return {p.relative_to(project): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in project.rglob("*") if p.is_file() and "build" not in p.parts
            and "__pycache__" not in p.parts}


def fake_preview(diagram, destination, **kwargs):
    destination.write_bytes(f"preview {diagram.slug}".encode())


def normalize_svg(svg):
    # Layout solves may differ at floating-point roundoff in metadata.
    root = ET.fromstring(svg)
    for element in root.iter():
        if element.get("id") == "asset-attribution-manifest":
            def rounded(value):
                if isinstance(value, float):
                    return round(value, 7)
                if isinstance(value, list):
                    return [rounded(v) for v in value]
                if isinstance(value, dict):
                    return {k: rounded(v) for k, v in value.items()}
                return value
            element.text = json.dumps(rounded(json.loads(element.text)), sort_keys=True)
    return ET.tostring(root)


def test_example_source_is_verbatim_except_leading_docstring():
    code = '# Keep this comment.\nfrom beampath import beam\n\ndef stage():\n    return beam()\n\nsetup = stage()'
    description, actual = docs.example_source('"""A description.\n\nMore detail."""\n\n' + code + '\n')
    assert description == "A description.\n\nMore detail."
    assert actual == code


@pytest.mark.parametrize("source", ["setup = None", '""""""\nsetup = None', '"""Only prose."""'])
def test_incomplete_example_reports_filename(source):
    with pytest.raises(ValueError, match="broken.py"):
        docs.example_source(source, "broken.py")


def test_discovery_uses_only_public_python_basenames(tmp_path):
    for name in ("zeta.py", "hello.py", "alpha.py", "_helper.py", "README.md"):
        (tmp_path / name).touch()
    assert example_names(tmp_path) == ("hello", "alpha", "zeta")


def test_every_published_example_code_reproduces_its_setup():
    entries = docs.examples()
    assert [d.slug for d in entries] == list(example_names())
    for diagram in entries:
        namespace = {}
        exec(compile(diagram.code, str(diagram.source), "exec"), namespace)
        assert normalize_svg(namespace["setup"].to_svg(style=namespace.get("style"))) == normalize_svg(
            diagram.setup.to_svg(style=diagram.style)), diagram.slug
        assert "# DOCS:" not in diagram.code
        assert "run_example" not in diagram.code


def test_all_public_components_have_standalone_matching_demos():
    entries = docs.component_demos()
    assert {d.slug for d in entries} == set(components.__all__)
    for diagram in entries:
        namespace = {}
        exec(diagram.code, namespace)
        assert normalize_svg(namespace["setup"].to_svg()) == normalize_svg(diagram.setup.to_svg())
        assert len(diagram.setup.setup.optics) == 1
        assert diagram.setup.setup.optics[0].spec.definition.name == diagram.slug


@pytest.mark.parametrize("missing", ["docstring", "demo"])
def test_missing_component_documentation_is_an_error(monkeypatch, missing):
    module = import_module(components.HWP.__module__)
    if missing == "docstring":
        monkeypatch.setattr(components.HWP, "__doc__", None)
    else:
        monkeypatch.delattr(module, "demo")
    with pytest.raises(ValueError, match="HWP"):
        docs.component_demos()


def test_invalid_demo_contract_is_an_error():
    def demo():
        return None
    with pytest.raises(ValueError, match="return setup"):
        docs.demo_source(demo)


def test_api_summaries_and_style_defaults_come_from_python(monkeypatch):
    monkeypatch.setattr(components.HWP, "__doc__", "A revised waveplate description.")
    custom_example = next(d for d in docs.examples() if d.slug == "custom_component")
    page = docs.components_page(docs.component_demos(), custom_example)
    assert "A revised waveplate description." in page
    assert docs.signature(components.HWP) in page
    summary = docs.api_summary()
    assert f'| `pitch` | `{inspect.signature(Style).parameters["pitch"].default!r}` |' in summary
    assert "Setup.save(filename, *, style=None, width=None, dpi=96)" in summary


def test_success_check_mode_and_idempotence(checkout, monkeypatch):
    monkeypatch.setattr(docs, "render_preview", fake_preview)
    before = snapshot(checkout)
    assert docs.rebuild_docs(checkout, check=True)
    assert snapshot(checkout) == before
    assert docs.rebuild_docs(checkout)
    first = snapshot(checkout)
    assert docs.rebuild_docs(checkout) == []
    assert docs.rebuild_docs(checkout, check=True) == []
    assert snapshot(checkout) == first
    assert list((checkout / "build").iterdir()) == []


def test_new_example_appears_without_registration_and_obsolete_previews_are_removed(checkout, monkeypatch):
    monkeypatch.setattr(docs, "render_preview", fake_preview)
    (checkout / "examples/new_optic.py").write_text('"""A new example."""\nfrom beampath import beam, iris\nsetup = beam() >> iris()\n')
    obsolete = checkout / "examples/images/removed.png"
    obsolete.write_bytes(b"obsolete")
    social = checkout / "examples/images/hello-social.png"
    social.write_bytes(b"keep social")
    assert "examples/images/removed.png" in docs.rebuild_docs(checkout, check=True)
    assert obsolete.exists()
    docs.rebuild_docs(checkout)
    assert "## new_optic" in (checkout / "docs/gallery.md").read_text()
    assert (checkout / "examples/images/new_optic.png").read_bytes() == b"preview new_optic"
    assert not obsolete.exists()
    assert social.read_bytes() == b"keep social"


@pytest.mark.parametrize("source", [
    '"""Broken."""\nsetup = None\n',
    '"""Broken."""\nfrom beampath import beam, iris\nsetup = beam() >> iris()\nstyle = 123\n',
    '"""Broken."""\nsetup = )\n',
])
def test_invalid_example_does_not_render_or_replace_outputs(checkout, monkeypatch, source):
    (checkout / "examples/broken.py").write_text(source)
    before = snapshot(checkout)
    monkeypatch.setattr(docs, "render_preview", lambda *a, **k: pytest.fail("rendered invalid sources"))
    with pytest.raises((ValueError, SyntaxError)):
        docs.rebuild_docs(checkout)
    assert snapshot(checkout) == before


def test_render_failure_keeps_existing_outputs_and_cleans_staging(checkout, monkeypatch):
    before = snapshot(checkout)
    def fail(diagram, destination, **kwargs):
        destination.write_bytes(b"partial preview")
        raise RuntimeError("Cairo unavailable")
    monkeypatch.setattr(docs, "render_preview", fail)
    with pytest.raises(RuntimeError, match="Cairo"):
        docs.rebuild_docs(checkout)
    assert snapshot(checkout) == before
    assert list((checkout / "build").iterdir()) == []


def test_malformed_generated_block_does_not_render(checkout, monkeypatch):
    path = checkout / "README.md"
    path.write_text(path.read_text().replace("<!-- HELLO:END -->", ""))
    before = snapshot(checkout)
    monkeypatch.setattr(docs, "render_preview", lambda *a, **k: pytest.fail("rendered invalid README"))
    with pytest.raises(ValueError, match="README.md"):
        docs.rebuild_docs(checkout)
    assert snapshot(checkout) == before


def test_cli_rebuilds_from_another_directory_and_checks_without_rewriting(checkout, tmp_path):
    try:
        import cairosvg
    except (ImportError, OSError):
        pytest.skip("PNG export requires native Cairo")
    scripts = checkout / "scripts"
    scripts.mkdir()
    shutil.copy(PROJECT / "scripts/rebuild_docs.py", scripts)
    command = [sys.executable, str(scripts / "rebuild_docs.py")]
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
    before = snapshot(checkout)
    subprocess.run(command + ["--check"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert snapshot(checkout) == before
    from PIL import Image
    for relative, width in (("examples/images", 2400), ("docs/images/components", 960)):
        for path in (checkout / relative).glob("*.png"):
            if path.stem == "hello-social":
                continue
            with Image.open(path) as image:
                assert image.width == width
                assert image.info["dpi"] == pytest.approx((600, 600), abs=.02)
                assert json.loads(image.info["beampath-attribution"])["assets"]
    (checkout / "docs/gallery.md").write_text("stale")
    before = snapshot(checkout)
    result = subprocess.run(command + ["--check"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1
    assert "docs/gallery.md" in result.stdout
    assert snapshot(checkout) == before


def test_preview_comparison_ignores_only_metadata_roundoff():
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    def png(y, *, color="white", credit="Original artwork", dpi=600):
        info = PngInfo()
        info.add_itxt("beampath-attribution", json.dumps({
            "optics": [{"position": [190, y]}], "assets": [{"attribution": credit}],
        }))
        output = BytesIO()
        Image.new("RGB", (2, 2), color).save(output, format="PNG", pnginfo=info, dpi=(dpi, dpi))
        return output.getvalue()

    original = png(125.41016151377531)
    repeated = png(125.41016151377532)
    assert original != repeated
    assert docs.output_signature(original) == docs.output_signature(repeated)
    for changed in (png(125.42), png(125.41016151377531, color="red"),
                    png(125.41016151377531, credit="Different credit"),
                    png(125.41016151377531, dpi=300)):
        assert docs.output_signature(original) != docs.output_signature(changed)


def test_documentation_links_resolve():
    files = [PROJECT / "README.md", *sorted((PROJECT / "docs").glob("*.md")),
             PROJECT / "examples/README.md", PROJECT / "src/beampath/components/README.md"]
    for path in files:
        text = path.read_text()
        links = re.findall(r'\]\(([^)]+)\)|src="([^"]+)"', text)
        for markdown, html in links:
            link = markdown or html
            if "://" in link:
                continue
            target, _, anchor = link.partition("#")
            destination = path.parent / target if target else path
            assert destination.exists(), (path, link)
            if anchor and destination.suffix == ".md":
                headings = re.findall(r"^#+ (.+)$", destination.read_text(), re.MULTILINE)
                anchors = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}
                assert anchor in anchors, (path, link)
