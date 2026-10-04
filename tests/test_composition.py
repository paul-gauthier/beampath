import runpy
"""Composition copies topology and constraints, without sharing physical optics."""
import pytest

from beampath import (
    ConnectionError, HWP, LayoutError, Setup, beam, beamsplitter, fiber_coupler,
    fiber_laser, fiber_launch, fiber_power_meter, fiber_splitter, inline_power_meter,
    iris, mirror,
)


def monitored_stage():
    split = fiber_launch() >> HWP() >> fiber_coupler() >> fiber_splitter()
    split.turn() >> fiber_power_meter("Monitor")
    return split.straight()


def snapshot(path):
    return (path.setup.optics, path.setup.connections, tuple(path.setup._roots),
            dict(path.setup._heading_seeds), path._end, path._port, path._consumed)


def test_repeated_branched_stage_copies_are_independent_and_keep_selected_output():
    stage = monitored_stage()
    original = snapshot(stage)
    svg = stage.to_svg()
    destination = beam() >> fiber_laser()
    alias = destination
    assert destination.append(stage) is alias
    first_end = destination.end
    destination >>= stage
    second_end = destination.end
    assert destination is alias
    assert first_end != second_end
    assert len(destination.setup.optics) == 11
    assert len(destination.setup.connections) == 10
    assert len({node.id for node in destination.setup.optics}) == 11
    assert len({edge.id for edge in destination.setup.connections}) == 10
    assert sum(node.spec.label == "Monitor" for node in destination.setup.optics) == 2
    for original_node, first, second in zip(
        stage.setup.optics, destination.setup.optics[1:6], destination.setup.optics[6:]
    ):
        assert original_node is not first and first is not second
        assert original_node.spec is first.spec is second.spec
    destination >> fiber_power_meter("Final")
    destination.to_svg()
    assert snapshot(stage) == original
    assert stage.to_svg() == svg
    stage >> inline_power_meter()
    assert len(destination.setup.optics) == 12


def test_copy_shared_recombiner_once_and_preserve_all_branches():
    stage = runpy.run_module("beampath.examples.mzi")["setup"]
    before = snapshot(stage)
    svg = stage.to_svg()
    destination = beam().append(fiber_laser(), at=(-500, 0))
    destination.append(stage, at=(0, 0))
    recombiner, = [node for node in destination.setup.optics if node.spec.label == "NPBS2"]
    assert sum(edge.target == recombiner.id for edge in destination.setup.connections) == 2
    assert sum(edge.source == recombiner.id for edge in destination.setup.connections) == 2
    assert len(destination.setup.optics) == len(stage.setup.optics) + 1
    assert len(destination.setup.connections) == len(stage.setup.connections) + 1
    assert len(destination.setup._roots) == 1
    destination.to_svg()
    assert snapshot(stage) == before
    assert stage.to_svg() == svg


def test_splitter_group_and_terminal_endpoints_are_valid():
    stage = fiber_launch() >> fiber_coupler() >> fiber_splitter()
    stage.turn() >> fiber_power_meter("Monitor")
    destination = fiber_laser() >> stage
    with pytest.raises(ConnectionError, match="select an output"):
        destination >> fiber_power_meter()
    destination.straight() >> fiber_power_meter()
    destination.to_svg()
    terminal = fiber_launch() >> fiber_coupler() >> fiber_power_meter()
    destination = fiber_laser() >> terminal
    destination.to_svg()
    with pytest.raises(ConnectionError, match="ends the beam path"):
        destination >> inline_power_meter()


def test_empty_receiver_accepts_inputless_stage_and_uses_its_origin():
    source = fiber_laser() >> inline_power_meter()
    destination = beam(origin=(100, 200)) >> source
    assert destination.layout().placements["optic-001"].position == (100, 200)
    assert source.layout().placements["optic-001"].position == (0, 0)
    destination >> fiber_power_meter()
    assert len(source.setup.optics) == 2


@pytest.mark.parametrize("empty", [False, True])
def test_free_space_copy_inherits_receiving_direction(empty):
    source = beam("north") >> mirror(turn="right") >> iris()
    destination = beam("south")
    if not empty:
        destination >> iris()
    destination >> source
    assert destination.end.instance.heading == 180
    assert source.end.instance.heading == 0
    destination.layout()


@pytest.mark.parametrize("explicit", [False, True])
def test_fiber_attachment_preserves_launch_heading_through_edits_and_nested_copy(explicit):
    source = beam("north") >> fiber_launch(**({"heading": "west"} if explicit else {})) >> iris()
    expected = 180 if explicit else 270
    destination = fiber_laser() >> source
    assert destination.end.instance.heading == expected
    destination >> HWP()
    assert destination.end.instance.heading == expected
    copy = beam() >> destination
    copy >> iris()
    assert copy.end.instance.heading == expected
    copy.layout()
    assert source.end.instance.heading == expected


def test_empty_receiver_supplies_new_fiber_launch_direction():
    source = beam("north") >> fiber_launch() >> iris()
    destination = beam("south") >> source
    assert destination.end.instance.heading == 90
    destination.layout()


def test_copy_uses_root_input_even_when_it_is_not_the_default():
    drawing = Setup()
    split = drawing.add(beamsplitter(turn="right"))
    drawing.beam("south").connect(split.input("secondary"))
    source = split.straight()
    destination = beam("south") >> iris()
    destination >> source
    assert destination.setup.connections[-1].input == "secondary"
    assert destination.end.instance.heading == 0


def test_position_translates_explicit_pins_and_keeps_internal_distances():
    source = beam(origin=(100, 80)).append(iris(), at=(120, 90))
    source.append(HWP(), distance=350, at=(470, 90))
    before = snapshot(source)
    source_svg = source.to_svg()
    destination = beam() >> iris()
    destination.append(source, at=(500, 0), distance=500)
    placed = destination.layout().placements
    assert placed["optic-002"].position == (500, 0)
    assert placed["optic-003"].position == (850, 0)
    assert [edge.distance for edge in destination.setup.connections] == [500, 350]
    assert snapshot(source) == before
    assert source.to_svg() == source_svg


@pytest.mark.parametrize("at,expected", [(None, (40, 50)), ((600, 70), (600, 70))])
def test_empty_receiver_translates_pins_to_origin_or_at(at, expected):
    source = beam(origin=(100, 80)).append(iris(), at=(120, 90))
    source.append(HWP(), at=(470, 90))
    copy = beam(origin=(40, 50)).append(source, at=at)
    layout = copy.layout()
    assert layout.placements["optic-001"].position == expected
    assert layout.placements["optic-002"].position == (expected[0] + 350, expected[1])


def test_without_at_discards_root_anchor_but_retains_explicit_pins():
    source = beam(origin=(100, 0)) >> iris()
    source.append(HWP(), at=(900, 0))
    destination = beam() >> iris()
    destination >> source
    layout = destination.layout()
    assert layout.placements["optic-002"].position[0] >= layout.style.pitch
    assert layout.placements["optic-003"].position == (900, 0)
    assert len(destination.setup._roots) == 1


def test_position_translates_pins_across_fiber_sections():
    source = beam(origin=(100, 80)) >> fiber_launch() >> fiber_coupler()
    source.append(fiber_launch(), at=(100, 600))
    source >> fiber_coupler()
    destination = beam().append(fiber_laser(), at=(-500, 0))
    destination.append(source, at=(500, 0))
    layout = destination.layout()
    assert layout.placements["optic-002"].position == (500, 0)
    assert layout.placements["optic-004"].position == (500, 520)


def test_copy_runs_combined_layout_instead_of_freezing_standalone_gaps():
    source = iris() >> HWP()
    standalone = source.layout()
    destination = beam() >> iris()
    destination >> source
    destination.append(iris(), at=(1500, 0))
    combined = destination.layout()
    source_gap = standalone.placements["optic-002"].position[0]
    copied_gap = (combined.placements["optic-003"].position[0]
                  - combined.placements["optic-002"].position[0])
    assert copied_gap > source_gap
    assert source.layout() == standalone


def test_incompatible_placement_remains_a_layout_error():
    source = iris() >> HWP()
    destination = beam() >> iris()
    destination.append(source, at=(10, 0))
    with pytest.raises(LayoutError, match="incompatible placement"):
        destination.layout()


def test_pins_and_absolute_headings_are_not_rotated():
    source = beam(origin=(100, 100)) >> mirror(heading="south")
    source.append(iris(), at=(100, 450))
    destination = beam("north", origin=(0, 500)) >> iris()
    destination.append(source, at=(0, 0))
    assert destination.end.instance.heading == 90
    assert destination.end.instance.at == (0, 350)
    assert source.end.instance.at == (100, 450)


@pytest.mark.parametrize("case,match", [
    ("empty_source", "no first component"),
    ("rootless", "exactly one root"),
    ("multiple_roots", "exactly one root"),
    ("disconnected", "every source optic"),
    ("same_setup", "same setup"),
    ("stale_source", "already connected"),
    ("stale_destination", "already connected"),
    ("consumed_source", "consumed"),
    ("consumed_destination", "consumed"),
    ("inputless", "no input"),
    ("medium", "free_space.*fiber"),
    ("fiber_distance", "distance=.*free-space"),
    ("initial_distance", "first component"),
    ("negative_distance", "positive"),
    ("heading", "direction disagrees"),
])
def test_failed_copies_are_atomic(case, match):
    source = iris() >> HWP()
    destination = beam() >> iris()
    kwargs = {}
    if case == "empty_source":
        source = beam()
    elif case == "rootless":
        source = Setup().add(iris()).out("out")
    elif case == "multiple_roots":
        source.setup.beam(origin=(0, 500)) >> iris()
    elif case == "disconnected":
        source.setup.add(iris())
    elif case == "same_setup":
        source = destination.end.out("out")
    elif case == "stale_source":
        source.end.out("out") >> iris()
    elif case == "stale_destination":
        destination.end.out("out") >> iris()
    elif case == "consumed_source":
        source.connect(source.setup.add(iris()).input())
    elif case == "consumed_destination":
        destination.connect(destination.setup.add(iris()).input())
    elif case == "inputless":
        source = fiber_laser() >> inline_power_meter()
    elif case == "medium":
        source = fiber_launch() >> iris()
    elif case == "fiber_distance":
        source = fiber_launch() >> iris()
        destination = beam() >> fiber_laser()
        kwargs = {"distance": 100}
    elif case == "initial_distance":
        destination = beam()
        kwargs = {"distance": 100}
    elif case == "negative_distance":
        kwargs = {"distance": -1}
    elif case == "heading":
        source = beam("north") >> fiber_coupler(heading="north")
    before_source, before_destination = snapshot(source), snapshot(destination)
    with pytest.raises(ConnectionError, match=match):
        destination.append(source, **kwargs)
    assert snapshot(source) == before_source
    assert snapshot(destination) == before_destination


def test_graph_remains_usable_after_failure_with_copied_heading_seed():
    source = beam("north") >> fiber_launch() >> iris()
    destination = beam() >> iris()
    before = snapshot(destination)
    with pytest.raises(ConnectionError, match="free_space.*fiber"):
        destination >> source
    assert snapshot(destination) == before
    destination >> fiber_coupler()
    destination >> source
    destination >> iris()
    assert destination.end.instance.heading == 270
    assert len(destination.setup.optics) == 5
    destination.layout()


def test_connect_and_join_still_reject_different_setups():
    source = iris() >> beamsplitter(turn="right")
    copy = beam() >> source
    with pytest.raises(ConnectionError, match="different setups"):
        copy.straight().connect(source.end.input("secondary"))
    with pytest.raises(ConnectionError, match="same setup"):
        copy.straight().join(source.straight(), beamsplitter())
