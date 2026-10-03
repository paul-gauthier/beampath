import json
import math
import xml.etree.ElementTree as ET

import pytest

from beampath import (
    ConnectionError, HWP, beam, fiber_laser, fiber_launch, fiber_coupler, fiber_power_meter,
    fiber_splitter, inline_power_meter,
)
from beampath.layout import artwork_point
from beampath.render import tag


def test_standalone_meter_has_only_an_incoming_fiber_stub():
    path = beam().append(fiber_power_meter())
    before = path.setup.optics, path.setup.connections
    layout = path.layout()
    route, = layout.fibers
    assert route.source is None and route.output is None
    assert (route.target, route.input) == (path.end.id, "in")
    assert route.length == pytest.approx(layout.style.open_length)
    assert len(layout.placements) == 1
    assert not layout.segments
    assert (path.setup.optics, path.setup.connections) == before


@pytest.mark.parametrize("position", [None, (0, 650), (900, -400)])
def test_meter_terminates_connected_path_and_docks_at_housing(position):
    path = beam().append(fiber_laser())
    path.append(fiber_power_meter(), at=position)
    before = path.setup.optics, path.setup.connections, path.end
    layout = path.layout()
    assert path.end.instance.spec.display_label == "Fiber power meter"
    assert all(node.heading is None for node in path.setup.optics)
    route, = layout.fibers
    assert (route.source, route.output, route.target, route.input) == (
        "optic-001", "out", "optic-002", "in")
    assert not layout.segments
    meter = layout.placements[path.end.id]
    offset = artwork_point(meter.instance, (30, 27), meter.rotation)
    assert route.end == pytest.approx(tuple(meter.position[i] + offset[i] for i in (0, 1)))
    if position is not None:
        assert meter.position == position
    with pytest.raises(ConnectionError, match="ends the beam path"):
        path >> inline_power_meter()
    assert (path.setup.optics, path.setup.connections, path.end) == before


@pytest.mark.parametrize("turn", ["left", "right"])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_unpinned_meter_input_aligns_with_splitter_branch_after_rotation(turn, rotation):
    angle = math.radians(rotation)
    split = beam().append(fiber_laser(""))
    split.append(fiber_splitter("", turn=turn),
                 at=(250 * math.cos(angle), 250 * math.sin(angle)))
    ref = split.end
    split.straight() >> fiber_launch("", heading=rotation)
    meter_path = split.turn() >> fiber_power_meter("")
    before = split.setup.optics, split.setup.connections
    layout = split.layout()
    route, = [r for r in layout.fibers if r.source == ref.id and r.output == "turn"]
    assert len(route.points) == 2
    assert route.length == pytest.approx(layout.style.pitch)
    junction = layout.placements[ref.id]
    meter = layout.placements[meter_path.end.id]
    outward = junction.port_exit_direction("turn")
    assert meter.port_exit_direction("in") == pytest.approx((outward + 180) % 360)
    direction = math.cos(math.radians(outward)), math.sin(math.radians(outward))
    assert route.end == pytest.approx(tuple(route.start[i] + layout.style.pitch * direction[i]
                                           for i in (0, 1)))
    assert meter.instance.at is None and meter.instance.heading is None
    assert (split.setup.optics, split.setup.connections) == before
    assert split.layout() == layout


@pytest.mark.parametrize("heading", [0, 270, 31.7])
def test_meter_after_recoupling_preserves_display_and_credits(heading):
    path = (fiber_launch(heading=heading) >> HWP() >> fiber_coupler()
            >> fiber_power_meter("Output power"))
    layout = path.layout()
    assert len(layout.segments) == 2
    assert len(layout.fibers) == 2  # Launch input stub and coupled fiber into the meter.
    connected, = [route for route in layout.fibers if route.source is not None]
    assert (connected.source, connected.target) == ("optic-003", path.end.id)
    assert not any(route.target is None for route in layout.fibers)
    root = ET.fromstring(path.to_svg())
    meter = root.find(f"{tag('g')}[@id='components']/{tag('g')}[@id='{path.end.id}']")
    display, = meter.iter(tag("text"))
    assert display.text == "-3.2 dBm"
    assert display.get("fill") == "#00CC66"
    assert display.get("data-display-readout") == "true"
    assert display.get("transform") is None
    assert not any(node.get("stroke") == layout.style.fiber_color for node in meter.iter())
    manifest = json.loads(root.find(
        f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    asset, = [a for a in manifest["assets"] if a["component"] == "fiber_power_meter"]
    assert asset["source_url"].endswith("/10_test_equipment/f-power-meter.svg")
    assert asset["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert manifest["optics"][-1]["label"] == "Output power"
