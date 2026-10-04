import math
import xml.etree.ElementTree as ET

import pytest

import beampath
from beampath import ComponentError, Setup, beam, component, detector, iris
from beampath.components import PBS, beamsplitter, mirror
from beampath.layout import artwork_point
from beampath.render import tag


def test_pbs_is_a_distinct_public_component():
    assert beampath.PBS is PBS
    assert PBS().definition.name == PBS().display_label == "PBS"
    assert PBS().definition is not beamsplitter().definition
    assert PBS().definition.artwork.package_resource == "fs-pbs-cube.svg"
    assert PBS("Analyzer").display_label == "Analyzer"
    assert PBS("").display_label == ""


@pytest.mark.parametrize("factory", [PBS, lambda **kw: component("PBS", **kw)])
@pytest.mark.parametrize("initial", [0, 90, 180, 270, 31.4])
@pytest.mark.parametrize("turn,delta", [("left", -90), ("right", 90), ("LEFT", -90)])
def test_pbs_directions_and_surface_follow_incidence(factory, initial, turn, delta):
    split = beam(initial) >> factory(turn=turn)
    cube = split.end.instance
    straight = split.straight() >> detector("p")
    reflected = split.reflect() >> detector("s")
    assert straight.end.instance.heading == pytest.approx(initial)
    assert reflected.end.instance.heading == pytest.approx((initial + delta) % 360)
    assert artwork_point(cube, (60, 45)) == pytest.approx((0, 0))
    a, b = artwork_point(cube, (40, 65)), artwork_point(cube, (80, 25))
    tangent = tuple((b[i] - a[i]) / math.dist(a, b) for i in (0, 1))
    incoming = (math.cos(math.radians(initial)), math.sin(math.radians(initial)))
    dot = sum(incoming[i] * tangent[i] for i in (0, 1))
    expected = tuple(2 * dot * tangent[i] - incoming[i] for i in (0, 1))
    angle = math.radians(reflected.end.instance.heading)
    assert (math.cos(angle), math.sin(angle)) == pytest.approx(expected)
    split.layout()


@pytest.mark.parametrize("turn", ["straight", "north", "", None, 90, True, [], {}])
def test_pbs_rejects_invalid_turns(turn):
    for factory in (PBS, lambda **kw: component("PBS", **kw)):
        with pytest.raises(ComponentError, match="turn must be 'left' or 'right'"):
            factory(turn=turn)


def test_pbs_rejects_unknown_parameters():
    with pytest.raises(ComponentError, match="Unknown component parameter"):
        component("PBS", angle=45)


def test_pbs_unused_secondary_input_has_no_stub():
    path = beam() >> PBS()
    ports = {port.name: port for port in path.end.instance.geometry.ports}
    assert ports["primary"].required
    assert not ports["secondary"].required
    segments = path.layout().segments
    assert len(segments) == 3
    assert {s.input for s in segments if s.target is not None} == {"primary"}
    assert {s.output for s in segments if s.source is not None} == {"straight", "reflect"}


@pytest.mark.parametrize("turn", ["left", "right"])
def test_pbs_join_draws_one_shared_cube(turn):
    other_turn = "right" if turn == "left" else "left"
    split = iris() >> beamsplitter(turn=other_turn)
    first = split.straight() >> mirror(turn=other_turn)
    second = split.reflect() >> mirror(turn=turn)
    combined = first.join(second, PBS(turn=turn))
    combined.straight() >> detector("T")
    combined.reflect() >> detector("R")
    incoming = [edge for edge in split.setup.connections if edge.target == combined.end.id]
    assert {edge.input for edge in incoming} == {"primary", "secondary"}
    root = ET.fromstring(split.to_svg())
    cubes = root.findall(f".//{tag('g')}[@data-component='PBS']")
    assert len(cubes) == 1
    # Captions and sample beams from the upstream asset must not be embedded.
    assert not cubes[0].findall(f".//{tag('text')}")
    assert not cubes[0].findall(f".//{tag('line')}[@stroke='#CC0000']")
    assert "Creative Commons Attribution" in split.to_svg()


@pytest.mark.parametrize("turn,direction,y", [("left", "north", 400), ("right", "south", -400)])
def test_pbs_explicit_connection_can_bind_secondary_first(turn, direction, y):
    setup = Setup()
    cube = setup.add(PBS(turn=turn))
    secondary = setup.beam(direction, origin=(0, y)) >> iris()
    secondary.connect(cube.input("secondary"))
    primary = setup.beam("east", origin=(-400, 0)) >> iris()
    primary.connect(cube.input())
    cube.out("straight") >> detector("T")
    cube.out("reflect") >> detector("R")
    placed = setup.layout().placements[cube.id]
    assert placed.port_direction("primary") == 0
    assert placed.port_direction("secondary") == (270 if turn == "left" else 90)
    assert len([edge for edge in setup.connections if edge.target == cube.id]) == 2
