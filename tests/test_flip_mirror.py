import json
import math
from importlib import import_module, resources
import xml.etree.ElementTree as ET

import pytest

import beampath
from beampath import ComponentError, ConnectionError, beam, component, detector
from beampath.components import flip_mirror
from beampath.layout import artwork_point
from beampath.render import tag


def _artwork():
    return ET.fromstring(resources.files("beampath").joinpath("assets/fs-flip-mirror.svg").read_text())


def _line_points(line):
    return tuple(tuple(float(line.get(f"{axis}{end}")) for axis in ("x", "y")) for end in (1, 2))


def test_flip_mirror_is_public_registered_and_accepts_standard_labels():
    assert beampath.flip_mirror is flip_mirror
    assert "flip_mirror" in beampath.__all__
    assert "flip_mirror" in beampath.components.__all__
    assert flip_mirror() == component("flip_mirror", turn="left")
    assert flip_mirror().geometry == component("flip_mirror").geometry
    assert flip_mirror("Pickoff").display_label == "Pickoff"
    assert flip_mirror("Pickoff", "alignment").display_label == "Pickoff\nalignment"
    assert flip_mirror("").display_label == ""


@pytest.mark.parametrize("factory", [flip_mirror, lambda **kw: component("flip_mirror", **kw)])
@pytest.mark.parametrize("initial", [0, 90, 180, 270, 31.4])
@pytest.mark.parametrize("parameters,delta", [
    ({}, -90), ({"turn": "left"}, -90), ({"turn": "right"}, 90),
    ({"turn": "LEFT"}, -90), ({"turn": "RIGHT"}, 90),
])
def test_flip_mirror_alternative_paths_and_surface_follow_incidence(factory, initial, parameters, delta):
    path = beam(initial) >> factory(**parameters)
    optic = path.end.instance
    straight = path.straight() >> detector("Out")
    reflected = path.reflect() >> detector("In")
    assert straight.end.instance.heading == pytest.approx(initial)
    assert reflected.end.instance.heading == pytest.approx((initial + delta) % 360)

    # Reflection must follow the actual solid mirror line in the SVG, and both
    # alternative paths must meet that surface at the component's beam anchor.
    assert artwork_point(optic, (0, 0)) == pytest.approx((0, 0))
    surface = _artwork().find(f".//{tag('line')}[@id='mirror-surface']")
    a, b = (artwork_point(optic, point) for point in _line_points(surface))
    assert tuple((a[i] + b[i]) / 2 for i in (0, 1)) == pytest.approx((0, 0))
    tangent = tuple((b[i] - a[i]) / math.dist(a, b) for i in (0, 1))
    incoming = (math.cos(math.radians(initial)), math.sin(math.radians(initial)))
    dot = sum(incoming[i] * tangent[i] for i in (0, 1))
    expected = tuple(2 * dot * tangent[i] - incoming[i] for i in (0, 1))
    angle = math.radians(reflected.end.instance.heading)
    outgoing = (math.cos(angle), math.sin(angle))
    assert outgoing == pytest.approx(expected)
    # The hatch marks identify the back of the mirror. The incoming beam
    # approaches the front, and the reflected beam leaves on that same side.
    hatch = _artwork().find(f"{tag('g')}[@stroke='#666666']/{tag('line')}")
    hatch_start, hatch_end = (artwork_point(optic, point) for point in _line_points(hatch))
    backing = tuple(hatch_end[i] - hatch_start[i] for i in (0, 1))
    assert sum(incoming[i] * backing[i] for i in (0, 1)) > 0
    assert sum(outgoing[i] * backing[i] for i in (0, 1)) < 0


def test_flip_mirror_outputs_can_be_selected_from_a_stable_optic_reference():
    path = beam() >> flip_mirror(turn="right")
    optic = path.end
    straight = optic.straight() >> detector("Out")
    reflected = optic.reflect() >> detector("In")
    assert straight.end.instance.heading == 0
    assert reflected.end.instance.heading == 90
    connections = [edge for edge in path.setup.connections if edge.source == optic.id]
    assert {(edge.output, edge.target) for edge in connections} == {
        ("straight", straight.end.id), ("reflect", reflected.end.id),
    }


@pytest.mark.parametrize("turn", ["straight", "north", "", None, 90, True, [], {}])
def test_flip_mirror_rejects_invalid_turns(turn):
    for factory in (flip_mirror, lambda **kw: component("flip_mirror", **kw)):
        with pytest.raises(ComponentError, match="turn must be 'left' or 'right'"):
            factory(turn=turn)


@pytest.mark.parametrize("parameters", [{"heading": "north"}, {"angle": 45}, {"unsupported": True}])
def test_flip_mirror_rejects_unknown_parameters(parameters):
    with pytest.raises(ComponentError, match="Unknown component parameter"):
        component("flip_mirror", **parameters)


@pytest.mark.parametrize("turn", ["left", "right"])
def test_flip_mirror_has_one_input_and_two_open_alternative_outputs(turn):
    path = beam("south") >> flip_mirror(turn=turn)
    optic = path.end
    inputs = [port for port in optic.instance.geometry.ports if port.kind == "input"]
    assert [port.name for port in inputs] == ["in"]
    assert inputs[0].required
    with pytest.raises(ConnectionError, match="no input port 'secondary'"):
        optic.input("secondary")

    layout = path.layout()
    placement = layout.placements[optic.id]
    incoming, = [segment for segment in layout.segments if segment.target == optic.id]
    outgoing = [segment for segment in layout.segments if segment.source == optic.id]
    assert incoming.input == "in"
    assert incoming.end == pytest.approx(placement.port_position("in"))
    assert {segment.output for segment in outgoing} == {"straight", "reflect"}
    assert len(layout.segments) == 3
    for segment in outgoing:
        assert segment.start == pytest.approx(incoming.end)
        dx, dy = (segment.end[i] - segment.start[i] for i in (0, 1))
        assert math.degrees(math.atan2(dy, dx)) % 360 == pytest.approx(
            placement.port_direction(segment.output))


@pytest.mark.parametrize("initial", [0, 31.4])
@pytest.mark.parametrize("turn", ["left", "right"])
def test_flip_mirror_alternate_position_rotates_ninety_degrees_about_shared_pivot(initial, turn):
    optic = (beam(initial) >> flip_mirror(turn=turn)).end.instance
    artwork = _artwork()
    surface = artwork.find(f".//{tag('line')}[@id='mirror-surface']")
    alternate = artwork.find(f".//{tag('line')}[@id='mirror-alternate']")
    pivot, solid_end = (artwork_point(optic, point) for point in _line_points(surface))
    ghost_pivot, ghost_end = (artwork_point(optic, point) for point in _line_points(alternate))
    assert pivot == pytest.approx(ghost_pivot)
    solid = tuple(solid_end[i] - pivot[i] for i in (0, 1))
    ghost = tuple(ghost_end[i] - ghost_pivot[i] for i in (0, 1))
    assert sum(solid[i] * ghost[i] for i in (0, 1)) == pytest.approx(0, abs=1e-10)
    assert math.hypot(*solid) == pytest.approx(math.hypot(*ghost))
    assert alternate.get("stroke-dasharray")

    # The flipped-out mirror clears the through beam and lies entirely behind
    # the reflected output's origin, where that output has no beam ray.
    normal = (-math.sin(math.radians(initial)), math.cos(math.radians(initial)))
    clearance = beampath.Style().beam_width / 2 + optic.spec.definition.artwork.scale * float(
        alternate.get("stroke-width")) / 2
    across_beam = [sum(point[i] * normal[i] for i in (0, 1)) for point in (ghost_pivot, ghost_end)]
    assert across_beam[0] * across_beam[1] > 0
    assert min(abs(value) for value in across_beam) > clearance
    reflected = math.radians(initial + optic.port("reflect").direction)
    outgoing = (math.cos(reflected), math.sin(reflected))
    assert max(sum(point[i] * outgoing[i] for i in (0, 1))
               for point in (ghost_pivot, ghost_end)) < -clearance


@pytest.mark.parametrize("initial", [0, 31.4])
@pytest.mark.parametrize("turn", ["left", "right"])
def test_flip_mirror_mount_clears_input_and_both_output_beams(initial, turn):
    optic = (beam(initial) >> flip_mirror(turn=turn)).end.instance
    artwork = _artwork()
    scale = optic.spec.definition.artwork.scale
    for identifier in ("mirror-housing", "mirror-hinge", "mirror-stem"):
        shape = artwork.find(f".//*[@id='{identifier}']")
        radius = 0
        if shape.tag == tag("rect"):
            x, y, width, height = (float(shape.get(key)) for key in ("x", "y", "width", "height"))
            points = [(x, y), (x + width, y), (x, y + height), (x + width, y + height)]
        elif shape.tag == tag("circle"):
            points = [(float(shape.get("cx")), float(shape.get("cy")))]
            radius = float(shape.get("r")) * scale
        else:
            points = _line_points(shape)
        transformed = [artwork_point(optic, point) for point in points]
        clearance = radius + float(shape.get("stroke-width")) * scale / 2 + beampath.Style().beam_width / 2
        # Full-line clearance is conservative for the incoming and reflected
        # rays, and also covers the straight-through output.
        for heading in (initial, initial + optic.port("reflect").direction):
            normal = (-math.sin(math.radians(heading)), math.cos(math.radians(heading)))
            across_beam = [sum(point[i] * normal[i] for i in (0, 1)) for point in transformed]
            assert min(across_beam) * max(across_beam) > 0, identifier
            assert min(abs(value) for value in across_beam) > clearance, identifier


def test_flip_mirror_demo_keeps_alternate_position_and_bundled_artwork_credits():
    path = import_module(flip_mirror.__module__).demo()
    root = ET.fromstring(path.to_svg())
    artwork, = root.findall(f".//{tag('g')}[@data-component='flip_mirror']")
    assert not list(artwork.iter(tag("text")))
    assert not any(element.get("stroke", "").lower() == "#cc0000" for element in artwork.iter())
    assert any(element.get("stroke-dasharray") for element in artwork.iter())

    manifest = json.loads(root.find(
        f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    asset, = [asset for asset in manifest["assets"] if asset["component"] == "flip_mirror"]
    assert "Original beampath schematic artwork" in asset["attribution"]
    assert asset["source_url"] == ""
    provenance = json.loads(resources.files("beampath").joinpath("assets/provenance.json").read_text())
    original, = [entry for entry in provenance["assets"] if entry["file"] == "fs-flip-mirror.svg"]
    assert asset["sha256"] == original["sha256"]
    assert path.end.instance.spec.definition.artwork.package_resource == "fs-flip-mirror.svg"
