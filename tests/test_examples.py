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
    "zwm": 8,
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


def test_zwm_overlaps_idlers_and_recombines_separate_signals():
    from beampath.examples.zwm import build

    path = build()
    layout = path.layout()
    crystals = [node for node in path.setup.optics if node.spec.definition.name == "spdc"]
    c1, c2 = crystals
    connections = path.setup.connections
    idler, = [edge for edge in connections if edge.source == c1.id and edge.output == "idler"]
    assert (idler.target, idler.input) == (c2.id, "idler_in")
    incoming = next(s for s in layout.segments if s.id == idler.id)
    outgoing, = [s for s in layout.segments if s.source == c2.id and s.output == "idler"]
    assert incoming.end == outgoing.start
    assert tuple((b - a) / incoming.length for a, b in zip(incoming.start, incoming.end)) == (
        pytest.approx(tuple((b - a) / outgoing.length for a, b in zip(outgoing.start, outgoing.end)))
    )

    signal_ends, signal_inputs, pump_sources = [], set(), set()
    nodes = {node.id: node for node in path.setup.optics}
    for crystal in crystals:
        assert not any(edge.target == crystal.id and edge.input == "signal_in" for edge in connections)
        pump, = [edge for edge in connections if edge.target == crystal.id and edge.input == "in"]
        while nodes[pump.source].spec.definition.name == "mirror":
            pump, = [edge for edge in connections if edge.target == pump.source]
        pump_sources.add(pump.source)
        signal, = [edge for edge in connections if edge.source == crystal.id and edge.output == "signal"]
        assert nodes[signal.target].spec.definition.name == "mirror"
        end, = [edge for edge in connections if edge.source == signal.target]
        signal_ends.append(end.target)
        signal_inputs.add(end.input)
    assert len(pump_sources) == 1
    assert nodes[pump_sources.pop()].spec.definition.name == "beamsplitter"
    assert signal_ends[0] == signal_ends[1]
    assert nodes[signal_ends[0]].spec.definition.name == "beamsplitter"
    assert signal_inputs == {"primary", "secondary"}


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
        # Each format solves the layout independently. Compare coordinates at
        # SVG's 12-significant-digit precision, ignoring solver roundoff while
        # keeping all attribution text and graph identities exact.
        def svg_precision(value):
            return float(f"{float(value):.12g}")

        assert json.loads(reader.metadata["/beampath-attribution"], parse_float=svg_precision) == (
            json.loads(expected, parse_float=svg_precision)
        ), name
