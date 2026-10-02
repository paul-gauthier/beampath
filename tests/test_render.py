import builtins
from hashlib import sha256
from importlib import resources
import json
import math
import re
import xml.etree.ElementTree as ET

import pytest

from beampath import Artwork, ComponentDefinition, ComponentSpec, Geometry, Port, Style, beam, iris, HWP, QWP, mirror
from beampath.examples import cage_system, mzi
from beampath.layout import artwork_point
from beampath.render import artwork_bytes, render_svg, tag


def test_incoming_stub_renders_with_arrow_and_open_source_metadata():
    path = beam("east") >> mirror(heading="north") >> mirror(turn="right") >> iris()
    layout = path.layout()
    lead, = [s for s in layout.segments if s.source is None]
    root = ET.fromstring(path.to_svg())
    beams = root.find(f"{tag('g')}[@id='optical-path']")
    line = beams.find(f"{tag('line')}[@id='{lead.id}']")
    assert (float(line.get("x1")), float(line.get("y1"))) == (-95, 0)
    assert (float(line.get("x2")), float(line.get("y2"))) == (0, 0)
    assert line.get("data-source") == line.get("data-output") == ""
    assert line.get("data-target") == "optic-001" and line.get("data-input") == "in"
    arrow = beams.find(f"{tag('line')}[@id='{lead.id}-arrow']")
    assert arrow.get("marker-end") == "url(#beam-arrow)"
    assert float(arrow.get("x2")) > float(arrow.get("x1"))
    assert float(arrow.get("y1")) == float(arrow.get("y2")) == 0
    assert len(beams.findall(tag("line"))) == 2 * len(layout.segments)
    manifest = json.loads(root.find(
        f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    incoming, = [s for s in manifest["segments"] if s["source"] is None]
    assert incoming["output"] is None
    assert incoming["target"] == "optic-001" and incoming["input"] == "in"
    assert len(manifest["optics"]) == 3


def test_each_physical_optic_and_beam_segment_render_once():
    p = mzi()
    layout = p.layout()
    root = ET.fromstring(render_svg(layout))
    groups = root.find(f"{tag('g')}[@id='components']")
    assert len(groups) == len(layout.placements) == 10
    combined = next(n for n in p.setup.optics if n.spec.label == "BS2")
    assert len(root.findall(f".//{tag('g')}[@id='{combined.id}']")) == 1
    beams = root.find(f"{tag('g')}[@id='optical-path']")
    assert len(beams.findall(tag("line"))) == 2 * len(layout.segments)
    assert list(root).index(beams) < list(root).index(groups)


def test_namespaces_and_internal_svg_references():
    artwork = '<svg xmlns="http://www.w3.org/2000/svg"><defs><clipPath id="clip"><circle r="8"/></clipPath></defs><rect x="-10" y="-10" width="20" height="20" clip-path="url(#clip)"/></svg>'
    definition = ComponentDefinition("custom", "Custom", Artwork((0, 0), (-10, -10, 10, 10), svg=artwork),
                                     lambda p: Geometry((Port("in", "input"), Port("out", "output"))))
    spec = ComponentSpec(definition)
    root = ET.fromstring((spec >> spec).to_svg())
    ids = [n.get("id") for n in root.iter() if n.get("id")]
    assert len(ids) == len(set(ids))
    assert "optic-001-clip" in ids and "optic-002-clip" in ids
    for node in root.iter():
        for value in node.attrib.values():
            for ref in re.findall(r"url\(#([^)]*)\)", value):
                assert ref in ids


def test_bundled_primitives_and_provenance_are_retained():
    p = cage_system()
    root = ET.fromstring(p.to_svg())
    manifest = json.loads(root.find(f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    assert len(manifest["assets"]) == 6
    assert all("Creative Commons Attribution" in a["attribution"] for a in manifest["assets"])
    assert all("7e44e14341489b067d7c8e1390af87b9c423103e" in a["source_url"] for a in manifest["assets"])
    for node in p.setup.optics:
        art = node.spec.definition.artwork
        original = ET.fromstring(artwork_bytes(art))
        selected = [child for child in original if child.tag == tag("defs") or art.selector(child)]
        imported = list(root.find(f"{tag('g')}[@id='components']/{tag('g')}[@id='{node.id}']"))
        assert len(selected) == len(imported)

        def compare(a, b):
            assert a.tag == b.tag and (a.text or "").strip() == (b.text or "").strip()
            attributes = dict(b.attrib)
            attributes.pop("id", None)
            expected = dict(a.attrib)
            expected.pop("id", None)
            if a.tag == tag("text"):
                attributes.pop("transform", None)
                expected.pop("transform", None)
            for key, value in attributes.items():
                attributes[key] = value.replace("#" + node.id + "-", "#")
            assert expected == attributes
            assert len(a) == len(b)
            for ac, bc in zip(a, b):
                compare(ac, bc)
        for a, b in zip(selected, imported):
            compare(a, b)
    pinned = json.loads(resources.files("beampath").joinpath("assets/provenance.json").read_text())
    license_data = resources.files("beampath").joinpath("assets", pinned["library"]["license_file"]).read_bytes()
    assert sha256(license_data).hexdigest() == pinned["library"]["license_sha256"]
    for asset in pinned["assets"]:
        assert sha256(resources.files("beampath").joinpath("assets", asset["file"]).read_bytes()).hexdigest() == asset["sha256"]


def test_fiber_role_orientation_and_mirror_backing():
    layout = cage_system().layout()
    nodes = list(layout.placements.values())
    launch, couple = nodes[0].instance, nodes[-1].instance
    assert artwork_point(launch, (85, 27))[0] < 0
    assert artwork_point(couple, (85, 27))[0] > 0
    for placed in nodes:
        node = placed.instance
        if node.spec.definition.name == "mirror":
            a, b = artwork_point(node, (50, 15)), artwork_point(node, (75, 55))
            surface = b[0] - a[0], b[1] - a[1]
            assert abs(surface[0]) == pytest.approx(abs(surface[1]))
            # A hatch end is deeper into backing than its reflecting-surface start.
            hatch_a, hatch_b = artwork_point(node, (51.4, 17.2)), artwork_point(node, (47.1, 19.9))
            d = math.cos(math.radians(node.heading)), math.sin(math.radians(node.heading))
            assert sum((hatch_b[i] - hatch_a[i]) * d[i] for i in (0, 1)) > 0


@pytest.mark.parametrize("initial,normal,parameters", [
    (0, 45, {"heading": "north"}), (90, 45, {"heading": "east"}),
    (180, -45, {"heading": 270}), (31.4, 12.7, {"heading": 236.8}),
    (270, 45, {"turn": "left"}), (37, -45, {"turn": "right"}),
])
def test_mirror_heading_and_turn_render_like_equivalent_normal(initial, normal, parameters):
    actual = beam(initial) >> mirror(**parameters) >> iris()
    expected = beam(initial) >> mirror(angle=normal) >> iris()
    actual_layout, expected_layout = actual.layout(), expected.layout()
    for ident, placed in actual_layout.placements.items():
        assert placed.position == pytest.approx(expected_layout.placements[ident].position)
        assert placed.bounds == pytest.approx(expected_layout.placements[ident].bounds)
    actual_svg, expected_svg = ET.fromstring(actual.to_svg()), ET.fromstring(expected.to_svg())
    for ident in actual_layout.placements:
        selector = f"{tag('g')}[@id='components']/{tag('g')}[@id='{ident}']"
        assert actual_svg.find(selector).get("transform") == expected_svg.find(selector).get("transform")
    manifest = json.loads(actual_svg.find(f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    assert manifest["optics"][0]["parameters"] == parameters


def test_text_is_editable_upright_and_labels_escaped():
    p = beam("south") >> HWP('A < B & "C"')
    root = ET.fromstring(p.to_svg())
    text = root.find(f"{tag('g')}[@id='component-labels']/{tag('text')}")
    assert text.text == 'A < B & "C"'
    assert text.get("transform") is None
    assert not any(n.tag in {tag("image"), tag("foreignObject"), tag("script")} for n in root.iter())


@pytest.mark.parametrize("direction", [0, 90, 37])
@pytest.mark.parametrize("content", [
    "HWP\nIn Rotation Mount", 'A < B\n& "C"', "\nHWP\n\nIn Rotation Mount\n",
])
def test_multiline_labels_render_as_centered_editable_lines(direction, content):
    style = Style(font_size=36)
    layout = (beam(direction) >> HWP(content)).layout(style=style)
    label, = layout.labels
    root = ET.fromstring(render_svg(layout))
    group = root.find(f"{tag('g')}[@id='component-labels']")
    assert group.get("text-anchor") == "middle"
    text, = group.findall(tag("text"))
    assert text.get("transform") is None
    lines = text.findall(tag("tspan"))
    assert [line.text or "" for line in lines] == content.split("\n")
    assert all(float(line.get("x")) == pytest.approx(label.position[0]) for line in lines)
    baselines = [float(line.get("y")) for line in lines]
    assert all(b - a == pytest.approx(style.font_size * 1.25)
               for a, b in zip(baselines, baselines[1:]))
    assert (baselines[0] + baselines[-1]) / 2 == pytest.approx(
        (label.bounds[1] + label.bounds[3]) / 2 + style.font_size * .35)
    manifest = json.loads(root.find(
        f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    assert manifest["labels"][0]["text"] == content


@pytest.mark.parametrize("factory,default_label", [(HWP, "HWP"), (QWP, "QWP")])
@pytest.mark.parametrize("direction", [0, 90, 180, 270, 37, 127])
@pytest.mark.parametrize("label", [None, "Mount", ""])
def test_waveplates_display_only_their_label(factory, default_label, direction, label):
    p = beam(direction) >> factory(label)
    root = ET.fromstring(p.to_svg())
    expected = default_label if label is None else label
    assert [t.text for t in root.iter(tag("text"))] == ([expected] if expected else [])


def test_default_labels_and_canvas_margins():
    p = iris() >> HWP()
    layout = p.layout()
    assert [label.text for label in layout.labels] == ["Iris", "HWP"]
    x0, y0, x1, y1 = layout.bounds
    for box in [o.bounds for o in layout.placements.values()] + [label.bounds for label in layout.labels]:
        assert box[0] >= x0 + layout.style.margin - 1e-6
        assert box[1] >= y0 + layout.style.margin - 1e-6
        assert box[2] <= x1 - layout.style.margin + 1e-6
        assert box[3] <= y1 - layout.style.margin + 1e-6


def test_save_svg_and_invalid_options(tmp_path):
    p = iris() >> HWP()
    dest = tmp_path / "setup.svg"
    assert p.save(dest) == dest
    assert dest.read_text() == p.to_svg()
    for options in ({"width": 0}, {"width": 100}, {"dpi": -1}):
        with pytest.raises(ValueError):
            p.save(dest, **options)
    with pytest.raises(ValueError, match=".svg or .png"):
        p.save(tmp_path / "setup.pdf")


def test_missing_png_dependency_has_clear_error(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "cairosvg":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(RuntimeError, match=r"beampath\[png\].*Cairo"):
        (beam() >> iris()).save(tmp_path / "setup.png")
    assert not (tmp_path / "setup.png").exists()


def test_png_matches_svg_raster_and_retains_credits(tmp_path):
    try:
        import cairosvg
    except (ImportError, OSError):
        pytest.skip("Optional PNG converter or native Cairo is unavailable")
    from PIL import Image
    from io import BytesIO
    p = mzi()
    path = tmp_path / "mzi.png"
    p.save(path, width=1800, dpi=600)
    actual = Image.open(path)
    expected = Image.open(BytesIO(cairosvg.svg2png(bytestring=p.to_svg().encode(), output_width=1800, dpi=600)))
    assert actual.size == expected.size
    assert actual.tobytes() == expected.tobytes()
    assert actual.width == 1800
    assert actual.info["dpi"] == pytest.approx((600, 600), abs=.02)
    credits = json.loads(actual.info["beampath-attribution"])
    assert len(credits["assets"]) == 7
    assert "attribution" in credits["assets"][0]
    assert actual.convert("RGB").getpixel((0, 0)) == (255, 255, 255)
