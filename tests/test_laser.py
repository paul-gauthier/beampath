import json
import math
import xml.etree.ElementTree as ET

import pytest

import beampath
from beampath import ComponentError, ConnectionError, beam, component, detector, fiber_power_meter, iris
from beampath.components import laser
from beampath.layout import artwork_point
from beampath.render import tag


def test_laser_is_public_with_standard_labels():
    assert beampath.laser is laser
    assert "laser" in beampath.__all__
    assert laser() == component("laser")
    assert laser().display_label == "Laser"
    assert laser("780 nm").display_label == "780 nm"
    assert laser("").display_label == ""
    with pytest.raises(ComponentError, match="Unknown component parameter"):
        component("laser", unsupported=True)


@pytest.mark.parametrize("direction", [0, 90, 180, 270, 31.4])
def test_laser_starts_at_nozzle_with_only_an_outgoing_stub(direction):
    path = beam(direction, origin=(123, 45)) >> laser()
    layout = path.layout()
    placed = layout.placements[path.end.id]
    stub, = layout.segments
    nozzle = artwork_point(placed.instance, (85, 26))
    assert placed.instance.heading == pytest.approx(direction)
    assert stub.start == pytest.approx(tuple(placed.position[i] + nozzle[i] for i in (0, 1)))
    assert stub.start == placed.port_position("out")
    assert (stub.source, stub.output, stub.target) == (path.end.id, "out", None)
    angle = math.radians(direction)
    length = math.dist(stub.start, stub.end)
    assert tuple((stub.end[i] - stub.start[i]) / length for i in (0, 1)) == pytest.approx(
        (math.cos(angle), math.sin(angle)))
    assert not layout.fibers
    with pytest.raises(ConnectionError, match="no default input"):
        path.end.input()


def test_laser_drives_free_space_optics_and_respects_port_distance():
    path = laser() >> iris()
    path.append(detector(), distance=80)
    layout = path.layout()
    source, aperture, sink = layout.placements.values()
    first, second = layout.segments
    assert first.start == source.port_position("out")
    assert first.end == aperture.port_position("in")
    assert second.end == sink.port_position("in")
    assert math.dist(second.start, second.end) == pytest.approx(80)
    assert all(segment.source is not None and segment.target is not None for segment in layout.segments)


def test_laser_rejects_incoming_beams_and_direct_fiber_connections():
    path = beam() >> iris()
    before = path.setup.optics, path.setup.connections, path.end
    with pytest.raises(ConnectionError, match="cannot append an optic without an input"):
        path >> laser()
    assert (path.setup.optics, path.setup.connections, path.end) == before

    source = beam() >> laser()
    before = source.setup.optics, source.setup.connections, source.end
    with pytest.raises(ConnectionError, match="free_space.*cannot connect.*fiber"):
        source >> fiber_power_meter()
    assert (source.setup.optics, source.setup.connections, source.end) == before


def test_laser_renders_only_housing_and_nozzle_with_pcl_attribution():
    root = ET.fromstring((beam() >> laser("780 nm")).to_svg())
    housing = root.find(f"{tag('g')}[@id='components']/{tag('g')}[@data-component='laser']")
    assert [child.tag for child in housing] == [tag("rect"), tag("rect")]
    labels = [node.text for node in root.find(f"{tag('g')}[@id='component-labels']")]
    assert labels == ["780 nm"]
    manifest = json.loads(root.find(
        f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    asset, = manifest["assets"]
    assert asset["source_url"].endswith("/26_semiconductor_lasers/fs-diode-laser.svg")
    assert "Creative Commons Attribution" in asset["attribution"]
    assert "electrical leads" in asset["attribution"]
