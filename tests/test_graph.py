import math
from dataclasses import FrozenInstanceError

import pytest

from beampath import (
    HWP, LP, QWP, ComponentError, ConnectionError, Setup, beam,
    beamsplitter, chain, component, fiber_launch, iris, mirror,
)


def mzi():
    split = fiber_launch() >> beamsplitter("BS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(angle=-45)
    b = split.reflect() >> LP() >> QWP() >> mirror(angle=45)
    combined = a.join(b, beamsplitter("BS2", angle=45))
    return split, a, b, combined


def test_mzi_graph_and_mutable_cursors():
    split, a, b, combined = mzi()
    assert len(split.setup.optics) == 8
    assert len(split.setup.connections) == 8
    assert a.end.instance.heading == 0
    assert b.end.instance.heading == 90
    assert combined.end.instance.heading == 90
    assert sum(n.spec.label == "BS2" for n in split.setup.optics) == 1
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
    p = iris() >> beamsplitter(angle=-45)
    before = p.setup.optics, p.setup.connections
    with pytest.raises(ConnectionError, match="select an output"):
        p >> iris()
    assert (p.setup.optics, p.setup.connections) == before
    q = p.reflect() >> beamsplitter(angle=45)
    assert q.end.instance.heading == 90
    assert q.reflect().end.id == q.end.id
    p.straight() >> iris()
    with pytest.raises(ConnectionError, match="already connected"):
        p.straight()


def test_explicit_sharing_secondary_first():
    split = iris() >> beamsplitter(angle=-45)
    a = split.straight() >> mirror(angle=-45)
    b = split.reflect() >> mirror(angle=45)
    shared = split.setup.add(beamsplitter("shared", angle=45))
    b.connect(shared.input("secondary"))
    a.connect(shared.input("primary"))
    assert shared.instance.heading == 90
    assert len([n for n in split.setup.optics if n.spec.label == "shared"]) == 1
    shared.reflect() >> LP()


def test_two_nominal_inputs_can_start_at_one_splitter():
    drawing = Setup()
    shared = drawing.add(beamsplitter(angle=-45), at=(200, 300))
    drawing.beam("east").connect(shared.input("primary"))
    drawing.beam("south").connect(shared.input("secondary"))
    assert shared.instance.heading == 0
    assert drawing.layout().placements[shared.id].position == (200, 300)


def test_failed_chain_is_atomic():
    p = beam() >> iris()
    previous = p.end.id
    before = p.setup.optics, p.setup.connections
    with pytest.raises(ConnectionError, match="select an output"):
        p >> chain(HWP(), beamsplitter(angle=-45), LP())
    assert (p.setup.optics, p.setup.connections) == before
    assert p.end.id == previous
    p >> QWP()


def test_failed_join_is_atomic_and_inputs_remain_usable():
    split = iris() >> beamsplitter(angle=-45)
    a, b = split.straight(), split.reflect()
    before = split.setup.optics, split.setup.connections
    with pytest.raises(ConnectionError, match="direction disagrees"):
        a.join(b, beamsplitter(angle=45))
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
    p = iris() >> beamsplitter(angle=-45)
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
        a.join(b, beamsplitter(angle=-45))
    with pytest.raises(ConnectionError, match="different setups"):
        a.connect(b.end.input())
    a >> fiber_launch(role="couple")
    with pytest.raises(ConnectionError, match="ends the beam"):
        a >> iris()


@pytest.mark.parametrize("factory", [
    lambda: beam("up"), lambda: mirror(angle=float("nan")),
    lambda: beamsplitter(angle=0), lambda: beamsplitter(angle=90),
    lambda: fiber_launch(role="other"), lambda: component("LP", unexpected=1),
    lambda: chain(), lambda: chain(Setup()),
])
def test_invalid_specs(factory):
    with pytest.raises(ComponentError):
        factory()
