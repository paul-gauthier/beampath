from pathlib import Path
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


EXAMPLES = {
    "hello": 5,
    "cage": 13,
    "mirror_heading": 3,
    "mzi": 9,
    "franson": 17,
    "shared_optic": 10,
    "reuse": 8,
    "composition": 12,
    "rendering": 3,
    "custom_component": 4,
    "mixed_fiber": 6,
    "fiber_bends": 6,
    "fiber_splitter": 4,
    "spdc": 5,
    "spdc_collinear": 4,
}
SVG = "{http://www.w3.org/2000/svg}"


def test_franson_analyzers_have_matching_nonzero_arm_imbalance():
    from beampath.examples.franson import build

    path = build()
    layout = path.layout()
    nodes = {optic.id: optic for optic in path.setup.optics}
    incoming, outgoing = {}, {}
    for segment in layout.segments:
        if segment.source is not None and segment.target is not None:
            incoming.setdefault(segment.target, []).append(segment)
            outgoing.setdefault(segment.source, []).append(segment)
    splitters = [node for node in nodes.values()
                 if node.spec.definition.name == "beamsplitter" and len(incoming[node.id]) == 1]
    assert len(splitters) == 2
    imbalances = []
    detectors = set()
    for splitter in splitters:
        lengths, ends = [], []
        for segment in outgoing[splitter.id]:
            length = segment.length
            while nodes[segment.target].spec.definition.name == "mirror":
                segment, = outgoing[segment.target]
                length += segment.length
            lengths.append(length)
            ends.append(segment.target)
        assert len(lengths) == 2
        assert ends[0] == ends[1]  # Both arms meet the same physical optic.
        recombiner = ends[0]
        assert nodes[recombiner].spec.definition.name == "beamsplitter"
        assert {segment.input for segment in incoming[recombiner]} == {"primary", "secondary"}
        imbalances.append(max(lengths) - min(lengths))
        outputs = outgoing[recombiner]
        assert {segment.output for segment in outputs} == {"straight", "reflect"}
        for segment in outputs:
            detector = nodes[segment.target]
            assert detector.spec.definition.name == "franson_detector"
            assert all(port.kind == "input" for port in detector.geometry.ports)
            detectors.add(detector.id)
    assert len(detectors) == 4
    assert imbalances[0] > 0
    assert imbalances[0] == pytest.approx(imbalances[1])


@pytest.mark.parametrize("name,count", EXAMPLES.items())
def test_example_scripts_run_from_another_directory(tmp_path, name, count):
    project = Path(__file__).resolve().parents[1]
    destination = tmp_path / "output"
    subprocess.run(
        [sys.executable, str(project / "examples" / f"{name}.py"),
         "--output-dir", str(destination)],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert sorted(p.name for p in destination.iterdir()) == [f"{name}.svg"]
    root = ET.parse(destination / f"{name}.svg").getroot()
    assert len(root.find(f"{SVG}g[@id='components']")) == count
    assert root.find(f"{SVG}g[@id='optical-path']").get("stroke") == (
        "#1f77b4" if name == "rendering" else "#CC0000"
    )


def test_all_examples_export_png_with_requested_width_and_credits(tmp_path):
    try:
        import cairosvg
    except (ImportError, OSError):
        pytest.skip("Optional PNG converter or native Cairo is unavailable")
    from PIL import Image

    subprocess.run(
        [sys.executable, "-m", "beampath.examples", "--diagram", "all", "--png",
         "--width", "640", "--output-dir", str(tmp_path)],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert {p.stem for p in tmp_path.glob("*.svg")} == set(EXAMPLES)
    assert {p.stem for p in tmp_path.glob("*.png")} == set(EXAMPLES)
    for name, count in EXAMPLES.items():
        with Image.open(tmp_path / f"{name}.png") as image:
            assert image.width == 640
            assert image.info["dpi"] == pytest.approx((600, 600), abs=.02)
            manifest = json.loads(image.info["beampath-attribution"])
            assert len(manifest["optics"]) == count
            assert all(asset["attribution"] for asset in manifest["assets"])


@pytest.mark.parametrize("entry_point", ["script", "module"])
def test_examples_export_pdf_with_vector_artwork_and_credits(tmp_path, entry_point):
    pypdf = pytest.importorskip("pypdf")
    try:
        import cairosvg
    except (ImportError, OSError):
        pytest.skip("Optional PDF converter or native Cairo is unavailable")
    project = Path(__file__).resolve().parents[1]
    command = ([str(project / "examples" / "hello.py")] if entry_point == "script"
               else ["-m", "beampath.examples", "--diagram", "all"])
    names = {"hello"} if entry_point == "script" else set(EXAMPLES)
    subprocess.run(
        [sys.executable, *command, "--pdf", "--png", "--width", "640",
         "--output-dir", str(tmp_path)],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    for suffix in (".svg", ".png", ".pdf"):
        assert {p.stem for p in tmp_path.glob("*" + suffix)} == names
    for name in names:
        reader = pypdf.PdfReader(tmp_path / f"{name}.pdf")
        assert len(reader.pages) == 1
        assert not list(reader.pages[0].images)
        root = ET.parse(tmp_path / f"{name}.svg").getroot()
        assert float(reader.pages[0].mediabox.width) == pytest.approx(float(root.get("width")) * .75)
        expected = root.find(f"{SVG}metadata/{SVG}metadata[@id='asset-attribution-manifest']").text
        assert reader.metadata["/beampath-attribution"] == expected
