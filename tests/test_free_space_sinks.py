import json
import xml.etree.ElementTree as ET

import pytest

import beampath
from beampath import ComponentError, ConnectionError, beam, component, fiber_laser, iris
from beampath.components import beam_block, detector
from beampath.layout import artwork_point
from beampath.render import tag


@pytest.mark.parametrize("factory,default", [(detector, "Detector"), (beam_block, "Beam block")])
def test_sinks_are_public_registered_components_with_standard_labels(factory, default):
    name = factory.__name__
    assert getattr(beampath, name) is factory
    assert name in beampath.__all__
    assert factory() == component(name)
    assert factory().display_label == default
    assert factory("D1").display_label == "D1"
    assert factory("").display_label == ""
    with pytest.raises(ComponentError, match="Unknown component parameter"):
        component(name, unsupported=True)


@pytest.mark.parametrize("factory,face", [(detector, (-22, 0)), (beam_block, (-10, 0))])
@pytest.mark.parametrize("direction", [0, 90, 180, 270, 31.4])
def test_sink_docks_at_entrance_face_and_ends_the_path(factory, face, direction):
    path = beam(direction) >> iris("") >> factory("End")
    layout = path.layout()
    terminal = layout.placements[path.end.id]
    incoming, = [segment for segment in layout.segments if segment.source is not None]
    offset = artwork_point(terminal.instance, face)
    assert terminal.instance.heading == pytest.approx(direction)
    assert incoming.end == pytest.approx(tuple(terminal.position[i] + offset[i] for i in (0, 1)))
    assert (incoming.target, incoming.input) == (path.end.id, "in")
    assert not any(segment.source == path.end.id or segment.target is None for segment in layout.segments)
    assert not layout.fibers

    before = path.setup.optics, path.setup.connections, path.end
    with pytest.raises(ConnectionError, match="ends the beam path"):
        path >> iris()
    assert (path.setup.optics, path.setup.connections, path.end) == before


@pytest.mark.parametrize("factory", [detector, beam_block])
def test_standalone_sink_draws_only_an_incoming_stub(factory):
    path = beam("north") >> factory()
    layout = path.layout()
    stub, = layout.segments
    assert stub.source is None
    assert (stub.target, stub.input) == (path.end.id, "in")
    assert stub.end == layout.placements[path.end.id].port_position("in")
    assert not layout.fibers


@pytest.mark.parametrize("factory", [detector, beam_block])
def test_free_space_sink_rejects_direct_fiber_connection(factory):
    path = beam() >> fiber_laser()
    before = path.setup.optics, path.setup.connections, path.end
    with pytest.raises(ConnectionError, match="fiber.*cannot connect.*free_space"):
        path >> factory()
    assert (path.setup.optics, path.setup.connections, path.end) == before


@pytest.mark.parametrize("factory,filename", [
    (detector, "fs-detector.svg"), (beam_block, "fs-beam-block.svg"),
])
def test_sink_exports_bundled_original_artwork_and_credits(factory, filename):
    path = beam() >> factory()
    root = ET.fromstring(path.to_svg())
    manifest = json.loads(root.find(
        f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    asset, = manifest["assets"]
    assert asset["component"] == factory.__name__
    assert "Original beampath schematic artwork" in asset["attribution"]
    assert asset["source_url"] == ""
    assert path.end.instance.spec.definition.artwork.package_resource == filename
