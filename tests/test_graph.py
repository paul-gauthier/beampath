import math
from dataclasses import FrozenInstanceError

import pytest

from beampath import (
    HWP, LP, QWP, ComponentError, ConnectionError, Setup, beam,
    beamsplitter, chain, component, fiber_launch, fiber_coupler, iris, mirror,
)


def mzi():
    split = fiber_launch() >> beamsplitter("NPBS1", turn="right")
    a = split.straight() >> HWP() >> mirror(angle=-45)
    b = split.reflect() >> LP() >> QWP() >> mirror(angle=45)
    combined = a.join(b, beamsplitter("NPBS2", turn="left"))
    return split, a, b, combined


def test_mzi_graph_and_mutable_cursors():
    split, a, b, combined = mzi()
    assert len(split.setup.optics) == 8
    assert len(split.setup.connections) == 8
    assert a.end.instance.heading == 0
    assert b.end.instance.heading == 90
    assert combined.end.instance.heading == 90
    assert sum(n.spec.label == "NPBS2" for n in split.setup.optics) == 1
    assert combined.reflect().setup is split.setup
    with pytest.raises(ConnectionError, match="consumed"):
        a >> iris()
    with pytest.raises(ConnectionError, match="consumed"):
        b >> iris()


def test_source_default_and_mutation():
    p = iris() >> HWP()
    alias = p
    p >>= LP()
    assert p is alias
    assert len(p.setup.optics) == 3
    assert all(n.heading == 0 for n in p.setup.optics)
    west = beam("west") >> iris()
    assert west.end.instance.heading == 180


@pytest.mark.parametrize("factory", [
    beamsplitter, lambda **parameters: component("beamsplitter", **parameters),
], ids=["factory", "generic"])
@pytest.mark.parametrize("initial", [0, 90, 180, 270, 31.4])
@pytest.mark.parametrize("parameters,delta", [
    ({}, -90), ({"turn": "left"}, -90), ({"turn": "right"}, 90),
    ({"turn": "LEFT"}, -90), ({"turn": "RIGHT"}, 90),
])
def test_beamsplitter_outputs_follow_primary_incidence(factory, initial, parameters, delta):
    split = beam(initial) >> factory(**parameters)
    straight = split.straight() >> iris()
    reflected = split.reflect() >> iris()
    assert straight.end.instance.heading == pytest.approx(initial)
    assert reflected.end.instance.heading == pytest.approx((initial + delta) % 360)


@pytest.mark.parametrize("turn", ["straight", "north", "", None, 90, True, [], {}])
def test_invalid_beamsplitter_turn(turn):
    with pytest.raises(ComponentError, match="Beamsplitter turn must be 'left' or 'right'"):
        beamsplitter(turn=turn)
    with pytest.raises(ComponentError, match="Beamsplitter turn must be 'left' or 'right'"):
        component("beamsplitter", turn=turn)


@pytest.mark.parametrize("initial", [0, 90, 180, 270, 31.4])
@pytest.mark.parametrize("normal", [-45, 45, -32, 12.7])
def test_reflection_matches_vector_law(initial, normal):
    p = beam(initial) >> mirror(angle=normal)
    node = p.end.instance
    reflected = node.heading + node.port("out").direction
    d = (math.cos(math.radians(initial)), math.sin(math.radians(initial)))
    n = (math.cos(math.radians(initial + normal)), math.sin(math.radians(initial + normal)))
    dot = sum(a * b for a, b in zip(d, n))
    expected = tuple(a - 2 * dot * b for a, b in zip(d, n))
    assert (math.cos(math.radians(reflected)), math.sin(math.radians(reflected))) == pytest.approx(expected)


@pytest.mark.parametrize("initial,target,expected", [
    ("east", "north", 270), ("north", "east", 0),
    ("south", "west", 180), ("west", "south", 90),
    ("east", "west", 180), (31.4, 127.8, 127.8),
    (350, 10, 10), (10, -10, 350), (90, 720, 0),
    ("east", "NORTH", 270),
])
def test_mirror_outbound_heading(initial, target, expected):
    path = beam(initial) >> mirror(heading=target) >> iris()
    assert path.end.instance.heading == pytest.approx(expected)


@pytest.mark.parametrize("initial", [0, 90, 180, 270, 31.4])
@pytest.mark.parametrize("turn,delta", [("left", -90), ("right", 90), ("LEFT", -90)])
def test_mirror_turn_is_relative_to_incidence(initial, turn, delta):
    path = beam(initial) >> mirror(turn=turn) >> iris()
    assert path.end.instance.heading == pytest.approx((initial + delta) % 360)


def test_heading_mirror_spec_is_reusable_across_incidence():
    spec = mirror("North mirror", heading="north")
    east = beam("east") >> spec
    south = beam("south") >> spec
    assert east.end.instance.spec is south.end.instance.spec is spec
    assert east.end.instance.port("out").direction == 270
    assert south.end.instance.port("out").direction == 180
    assert east.end.instance.geometry.artwork_rotation != south.end.instance.geometry.artwork_rotation
    assert dict(spec.parameters) == {"heading": "north"}


def test_heading_mirror_in_repeated_chain():
    fragment = chain(mirror(heading="north"), mirror(turn="right"))
    path = beam() >> fragment >> fragment >> iris()
    assert [node.heading for node in path.setup.optics] == [0, 270, 0, 270, 0]


def test_heading_mirror_can_connect_after_its_outbound_path():
    drawing = Setup()
    optic = drawing.add(mirror(heading="north"))
    downstream = optic.out("out") >> iris()
    assert downstream.end.instance.heading == 270
    assert optic.instance.heading is None
    drawing.beam("east").connect(optic.input())
    assert optic.instance.heading == 0
    assert drawing.layout().placements[downstream.end.id].port_direction("in") == 270


def test_heading_mirrors_on_splitter_branches_and_join():
    split = iris() >> beamsplitter(turn="right")
    a = split.straight() >> mirror(heading="south")
    b = split.reflect() >> mirror(heading="east")
    combined = a.join(b, beamsplitter(turn="left"))
    assert combined.end.instance.heading == 90
    assert len([segment for segment in split.layout().segments
                if segment.source is not None and segment.target is not None]) == 5


@pytest.mark.parametrize("initial,target", [
    ("east", "east"), ("north", 270), (37.2, 397.2), (0, 360),
])
def test_impossible_mirror_heading_leaves_path_usable(initial, target):
    path = beam(initial) >> iris()
    previous = path.end.id
    before = path.setup.optics, path.setup.connections
    with pytest.raises(ComponentError, match="optic-002.*heading unchanged"):
        path >> mirror(heading=target)
    assert (path.setup.optics, path.setup.connections) == before
    assert path.end.id == previous
    path >> mirror(turn="right")


def test_impossible_heading_in_chain_is_atomic():
    path = beam() >> iris()
    before = path.setup.optics, path.setup.connections
    with pytest.raises(ComponentError, match="heading unchanged"):
        path >> chain(mirror(turn="left"), HWP(), mirror(heading="north"))
    assert (path.setup.optics, path.setup.connections) == before
    path >> QWP()


def test_impossible_heading_connect_is_atomic():
    drawing = Setup()
    optic = drawing.add(mirror(heading="east"))
    path = drawing.beam("east")
    before = drawing.optics, drawing.connections
    with pytest.raises(ComponentError, match="heading unchanged"):
        path.connect(optic.input())
    assert (drawing.optics, drawing.connections) == before
    drawing.beam("north").connect(optic.input())
    assert optic.instance.heading == 270
    path >> iris()


@pytest.mark.parametrize("parameters", [
    {}, {"angle": 45, "heading": "north"}, {"angle": 45, "turn": "left"},
    {"heading": 90, "turn": "right"}, {"angle": 45, "heading": 90, "turn": "right"},
    {"heading": "up"}, {"heading": float("nan")}, {"heading": float("inf")},
    {"turn": "straight"}, {"turn": 90},
    {"angle": 90}, {"angle": -90}, {"angle": 270},
])
def test_invalid_mirror_orientation(parameters):
    with pytest.raises(ComponentError):
        mirror(**parameters)
    with pytest.raises(ComponentError):
        component("mirror", **parameters)


def test_generic_component_supports_mirror_heading_and_turn():
    path = beam() >> component("mirror", heading="north") >> component("mirror", turn="right") >> iris()
    assert path.end.instance.heading == 0


def test_reusable_specs_and_chains_make_fresh_instances():
    plate = HWP()
    fragment = chain(LP(), plate, chain(QWP()))
    p = beam() >> fragment >> fragment
    assert len(p.setup.optics) == 6
    assert len({n.id for n in p.setup.optics}) == 6
    assert p.setup.optics[1].spec is plate
    q = plate >> iris()
    assert q.setup is not p.setup
    with pytest.raises(TypeError):
        plate.parameters["angle"] = 10
    with pytest.raises(FrozenInstanceError):
        plate.label = "changed"


def test_nested_split_and_output_selection():
    p = iris() >> beamsplitter(turn="right")
    before = p.setup.optics, p.setup.connections
    with pytest.raises(ConnectionError, match="select an output"):
        p >> iris()
    assert (p.setup.optics, p.setup.connections) == before
    q = p.reflect() >> beamsplitter(turn="left")
    assert q.end.instance.heading == 90
    assert q.reflect().end.id == q.end.id
    p.straight() >> iris()
    with pytest.raises(ConnectionError, match="already connected"):
        p.straight()


def test_explicit_sharing_secondary_first():
    split = iris() >> beamsplitter(turn="right")
    a = split.straight() >> mirror(angle=-45)
    b = split.reflect() >> mirror(angle=45)
    shared = split.setup.add(beamsplitter("shared", turn="left"))
    b.connect(shared.input("secondary"))
    a.connect(shared.input("primary"))
    assert shared.instance.heading == 90
    assert len([n for n in split.setup.optics if n.spec.label == "shared"]) == 1
    shared.reflect() >> LP()


def test_two_nominal_inputs_can_start_at_one_splitter():
    drawing = Setup()
    shared = drawing.add(beamsplitter(turn="right"), at=(200, 300))
    drawing.beam("east").connect(shared.input("primary"))
    drawing.beam("south").connect(shared.input("secondary"))
    assert shared.instance.heading == 0
    result = drawing.layout()
    assert result.placements[shared.id].position == (200, 300)
    leads = [s for s in result.segments if s.source is None]
    assert len(leads) == 2
    assert len({s.id for s in leads}) == 2
    assert all(s.target == shared.id and s.end == (200, 300) for s in leads)
    assert {s.input: s.start for s in leads} == {
        "primary": (105, 300), "secondary": (200, 205)}
    assert drawing.connections == ()


def test_failed_chain_is_atomic():
    p = beam() >> iris()
    previous = p.end.id
    before = p.setup.optics, p.setup.connections
    with pytest.raises(ConnectionError, match="select an output"):
        p >> chain(HWP(), beamsplitter(turn="right"), LP())
    assert (p.setup.optics, p.setup.connections) == before
    assert p.end.id == previous
    p >> QWP()


def test_failed_join_is_atomic_and_inputs_remain_usable():
    split = iris() >> beamsplitter(turn="right")
    a, b = split.straight(), split.reflect()
    before = split.setup.optics, split.setup.connections
    with pytest.raises(ConnectionError, match="direction disagrees"):
        a.join(b, beamsplitter(turn="left"))
    assert (split.setup.optics, split.setup.connections) == before
    a >> LP()
    b >> QWP()


def test_stale_cursor_and_occupied_input():
    p = beam() >> iris()
    stale = p.end.out("out")
    p >> HWP()
    with pytest.raises(ConnectionError, match="already connected"):
        stale >> QWP()
    target = p.setup.add(iris())
    p.connect(target.input())
    with pytest.raises(ConnectionError, match="already connected"):
        p.setup.beam().connect(target.input())


def test_cycle_rejection_is_atomic():
    p = iris() >> beamsplitter(turn="right")
    splitter = p.end
    q = p.reflect() >> mirror(angle=45)
    before = p.setup.optics, p.setup.connections
    with pytest.raises(ConnectionError, match="closed paths"):
        q.connect(splitter.input("secondary"))
    assert (p.setup.optics, p.setup.connections) == before
    q >> iris()


def test_ownership_and_terminal_errors():
    a = beam() >> iris()
    b = beam() >> iris()
    with pytest.raises(ConnectionError, match="same setup"):
        a.join(b, beamsplitter(turn="right"))
    with pytest.raises(ConnectionError, match="different setups"):
        a.connect(b.end.input())
    a >> fiber_coupler()
    with pytest.raises(ConnectionError, match="fiber.*free_space"):
        a >> iris()


@pytest.mark.parametrize("factory", [
    lambda: beam("up"), lambda: mirror(angle=float("nan")),
    lambda: component("fiber_launch", role="couple"),
    lambda: component("fiber_coupler", role="launch"), lambda: component("LP", unexpected=1),
    lambda: chain(), lambda: chain(Setup()),
])
def test_invalid_specs(factory):
    with pytest.raises(ComponentError):
        factory()


@pytest.mark.parametrize("factory", [fiber_launch, fiber_coupler])
def test_fiber_transitions_reject_removed_role_keyword(factory):
    with pytest.raises(TypeError, match="unexpected keyword argument 'role'"):
        factory(role="couple")
