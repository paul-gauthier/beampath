"""Reciprocal splitter views reuse one optic for outbound and return beams."""
import math
import runpy
import xml.etree.ElementTree as ET

import pytest

from beampath import (
    PBS, ComponentError, ConnectionError, Geometry, LayoutError, OpticRef, Port, Setup, beam, beamsplitter,
    detector, fiber_coupler, fiber_launch, iris, mirror, rows,
)
from beampath.render import tag


def snapshot(path):
    return (path.setup.optics, path.setup.connections, tuple(path.setup._roots),
            dict(path.setup._heading_seeds), dict(path.setup._output_labels),
            path._end, path._port, path._consumed)


def round_trip(factory=beamsplitter, direction=0, turn="left"):
    path = beam(direction) >> factory("BS", turn=turn)
    split = path.end
    split.reflect() >> detector("yyy")
    returning = split.straight() >> mirror("mirror", angle=0)
    returning.connect(split.reverse().input())
    return path, split, returning


@pytest.mark.parametrize("factory", [beamsplitter, PBS])
def test_reverse_is_a_nonmutating_view_of_the_same_physical_optic(factory):
    path = beam() >> factory("BS")
    split = path.end
    before = snapshot(path)
    forward_svg = path.to_svg()

    back = split.reverse()
    assert isinstance(back, OpticRef)
    assert back.setup is split.setup
    assert back.id == split.id
    assert back.instance is split.instance
    assert back.reverse() == split
    assert split.reverse() == back
    assert path.reverse() == back
    assert path.end == split
    assert back.input().name == dict(split.instance.geometry.reverse_ports)["primary"]
    assert snapshot(path) == before
    assert path.to_svg() == forward_svg


@pytest.mark.parametrize("factory", [beamsplitter, PBS])
@pytest.mark.parametrize("direction", [0, 90, 180, 270, 31.4])
@pytest.mark.parametrize("turn,delta", [("left", -90), ("right", 90)])
def test_reverse_primary_input_orients_both_outputs(factory, direction, turn, delta):
    setup = Setup()
    split = setup.add(factory(turn=turn), at=(240, -50))
    back = split.reverse()
    setup.beam((direction + 180) % 360).connect(back.input())
    straight = back.straight() >> detector("Return transmission")
    reflected = back.reflect() >> detector("Return reflection")

    assert split.instance.heading == pytest.approx(direction)
    assert straight.end.instance.heading == pytest.approx((direction + 180) % 360)
    assert reflected.end.instance.heading == pytest.approx((direction + 180 + delta) % 360)
    result = setup.layout()
    placed = result.placements[split.id]
    assert placed.position == (240, -50)
    assert placed.port_direction(back.input().name) == pytest.approx((direction + 180) % 360)
    lead, = [segment for segment in result.segments if segment.source is None]
    assert lead.input == back.input().name
    assert lead.end == pytest.approx(placed.position)


@pytest.mark.parametrize("factory", [beamsplitter, PBS])
@pytest.mark.parametrize("turn,delta", [("left", -90), ("right", 90)])
def test_reverse_secondary_is_optional_and_can_bind_before_forward_primary(factory, turn, delta):
    setup = Setup()
    split = setup.add(factory(turn=turn), at=(30, 50))
    back = split.reverse()
    direction = 37
    secondary = back.input("secondary")
    assert not split.instance.port(secondary.name).required
    setup.beam(direction + delta + 180).connect(secondary)
    setup.beam(direction).connect(split.input())

    assert split.instance.heading == pytest.approx(direction)
    result = setup.layout()
    leads = [segment for segment in result.segments if segment.source is None]
    assert {segment.input for segment in leads} == {"primary", secondary.name}
    reverse_outputs = {dict(split.instance.geometry.reverse_ports)[name]
                       for name in ("straight", "reflect")}
    assert reverse_outputs <= {segment.output for segment in result.segments
                               if segment.source == split.id and segment.target is None}


@pytest.mark.parametrize("factory", [beamsplitter, PBS])
def test_unused_reverse_ports_add_no_stubs_to_a_forward_diagram(factory):
    path = beam() >> factory()
    result = path.layout()
    assert len(result.segments) == 3
    assert {segment.input for segment in result.segments if segment.target is not None} == {"primary"}
    assert {segment.output for segment in result.segments if segment.source is not None} == {
        "straight", "reflect"}
    assert path.to_svg() == path.to_svg()


@pytest.mark.parametrize("factory", [beamsplitter, PBS])
@pytest.mark.parametrize("direction", [0, 90, 31.4])
@pytest.mark.parametrize("turn,delta", [("left", -90), ("right", 90)])
def test_mirror_return_reuses_splitter_and_retraces_the_outbound_segment(factory, direction, turn, delta):
    path, split, returning = round_trip(factory, direction, turn)
    reverse_detector = split.reverse().reflect() >> detector("xxx")
    assert returning._consumed
    assert reverse_detector.end.instance.heading == pytest.approx((direction + delta + 180) % 360)
    assert len(path.setup.optics) == 4
    assert sum(node.spec.label == "BS" for node in path.setup.optics) == 1
    result = path.layout()
    outbound, = [segment for segment in result.segments
                 if segment.source == split.id and segment.output == "straight"]
    inbound, = [segment for segment in result.segments
                if segment.target == split.id and segment.input == split.reverse().input().name]
    assert outbound.source == inbound.target
    assert outbound.target == inbound.source
    assert outbound.start == pytest.approx(inbound.end)
    assert outbound.end == pytest.approx(inbound.start)
    assert outbound.length == pytest.approx(inbound.length)
    assert result == path.layout()
    assert path.to_svg() == path.to_svg()


def test_round_trip_matches_north_yyy_east_mirror_south_xxx_diagram():
    path, split, _ = round_trip()
    split.reverse().reflect() >> detector("xxx")
    result = path.layout()
    by_label = {placed.instance.spec.label: placed for placed in result.placements.values()}
    center = by_label["BS"].position
    assert by_label["yyy"].position[0] == pytest.approx(center[0])
    assert by_label["yyy"].position[1] < center[1]
    assert by_label["mirror"].position[0] > center[0]
    assert by_label["mirror"].position[1] == pytest.approx(center[1])
    assert by_label["xxx"].position[0] == pytest.approx(center[0])
    assert by_label["xxx"].position[1] > center[1]

    root = ET.fromstring(path.to_svg())
    cubes = root.findall(f".//{tag('g')}[@data-component='beamsplitter']")
    mirrors = root.findall(f".//{tag('g')}[@data-component='mirror']")
    assert len(cubes) == len(mirrors) == 1
    beams = root.find(f"{tag('g')}[@id='optical-path']")
    paired = [segment for segment in result.segments
              if {segment.source, segment.target} == {split.id, by_label["mirror"].id}]
    arrows = [beams.find(f"{tag('line')}[@id='{segment.id}-arrow']") for segment in paired]
    centers = []
    for segment, arrow in zip(paired, arrows):
        start = tuple(float(arrow.get(axis + "1")) for axis in ("x", "y"))
        end = tuple(float(arrow.get(axis + "2")) for axis in ("x", "y"))
        assert sum((end[i] - start[i]) * (segment.end[i] - segment.start[i])
                   for i in (0, 1)) > 0
        centers.append(tuple((start[i] + end[i]) / 2 for i in (0, 1)))
    assert len(centers) == 2
    assert math.dist(*centers) > 0


def test_retroreflection_example_matches_the_requested_diagram():
    example = runpy.run_module("beampath.examples.retroreflection")
    path, split, back = (example[name] for name in ("setup", "bs", "back"))
    assert back == split.reverse()
    result = path.layout()
    assert len(result.placements) == 4
    placed = {item.instance.spec.display_label: item for item in result.placements.values()}
    center = placed["BS"].position
    assert placed["yyy"].position[0] == pytest.approx(center[0])
    assert placed["yyy"].position[1] < center[1]
    assert placed["xxx"].position[0] == pytest.approx(center[0])
    assert placed["xxx"].position[1] > center[1]
    assert placed["Mirror"].position[0] > center[0]
    assert placed["Mirror"].position[1] == pytest.approx(center[1])


def test_reverse_outputs_have_shared_ownership_across_views():
    path = beam() >> beamsplitter()
    back = path.reverse()
    first, stale = back.reflect(), path.end.reverse().out("reflect")
    first >> detector()
    before = snapshot(stale)
    with pytest.raises(ConnectionError, match="already connected"):
        stale >> iris()
    assert snapshot(stale) == before
    with pytest.raises(ConnectionError, match="already connected"):
        path.reverse().reflect()
    # The original forward reflection is a different directed port.
    path.reflect() >> detector()


def test_reverse_input_occupancy_failure_is_atomic_and_keeps_cursor_usable():
    path, split, _ = round_trip()
    retry = path.setup.beam("west", origin=(500, 300))
    before = snapshot(retry)
    with pytest.raises(ConnectionError, match="already connected"):
        retry.connect(split.reverse().input())
    assert snapshot(retry) == before
    retry >> iris()
    assert not retry._consumed


def test_incompatible_reverse_heading_rolls_back_connection_and_cursor():
    path = beam() >> beamsplitter()
    returning = path.straight() >> mirror(turn="left")
    before = snapshot(returning)
    with pytest.raises(ConnectionError, match="direction disagrees"):
        returning.connect(path.reverse().input())
    assert snapshot(returning) == before
    returning >> iris()


def test_reverse_connections_keep_setup_ownership_and_consumed_cursor_rules():
    first = beam() >> beamsplitter()
    other = beam("west") >> iris()
    before = snapshot(other)
    with pytest.raises(ConnectionError, match="different setups"):
        other.connect(first.reverse().input())
    assert snapshot(other) == before
    returned = first.straight() >> mirror(angle=0)
    back = returned.connect(first.reverse().input())
    assert back == first.reverse()
    with pytest.raises(ConnectionError, match="consumed"):
        returned.reverse()


def test_incompatible_fixed_round_trip_distances_still_fail_layout():
    path = beam() >> beamsplitter()
    returning = path.straight().append(mirror(angle=0), distance=200)
    returning.connect(path.reverse().input(), distance=300)
    with pytest.raises(LayoutError, match="incompatible"):
        path.layout()


def test_copy_preserves_cycle_and_selected_reverse_output_without_mutating_source():
    source, split, _ = round_trip()
    endpoint = split.reverse().reflect()
    before = snapshot(endpoint)
    source_svg = source.to_svg()
    destination = beam("north") >> iris()
    destination >> endpoint
    copied_split, = [node for node in destination.setup.optics if node.spec.label == "BS"]
    assert destination.end.id == copied_split.id
    destination >> detector("Copied xxx")
    assert destination.end.instance.heading == 0
    incoming = [edge for edge in destination.setup.connections if edge.target == copied_split.id]
    assert len(incoming) == 2
    assert len(destination.setup.optics) == len(source.setup.optics) + 2
    destination.layout()
    assert snapshot(endpoint) == before
    assert source.to_svg() == source_svg
    endpoint >> detector("Original xxx")
    assert destination.end.instance.spec.label == "Copied xxx"


def test_rows_copy_round_trip_topology_once_per_stage():
    entry = beam() >> fiber_launch() >> beamsplitter("BS")
    split = entry.end
    split.reflect() >> detector("yyy")
    (split.straight() >> mirror(angle=0)).connect(split.reverse().input())
    stage = split.reverse().reflect() >> fiber_coupler()
    before = snapshot(stage)
    grouped = rows(stage, stage)
    assert len(grouped.setup.optics) == 2 * len(stage.setup.optics)
    assert sum(node.spec.label == "BS" for node in grouped.setup.optics) == 2
    assert len(grouped.setup.connections) == 2 * len(stage.setup.connections) + 1
    result = grouped.layout()
    assert grouped.layout() == result
    assert snapshot(stage) == before


@pytest.mark.parametrize("factory", [iris, lambda: mirror(angle=0), fiber_coupler])
def test_reverse_rejects_unsupported_components_without_changing_them(factory):
    path = beam() >> factory()
    before = snapshot(path)
    with pytest.raises(ConnectionError, match="does not support reverse traversal"):
        path.end.reverse()
    with pytest.raises(ConnectionError, match="does not support reverse traversal"):
        path.reverse()
    assert snapshot(path) == before


def test_reverse_rejects_empty_paths_and_unknown_port_aliases():
    with pytest.raises(ConnectionError, match="no first component"):
        beam().reverse()
    path = beam() >> beamsplitter()
    before = snapshot(path)
    with pytest.raises(ConnectionError):
        path.reverse().input("unknown")
    with pytest.raises(ConnectionError):
        path.reverse().out("unknown")
    assert snapshot(path) == before


def test_selected_reverse_path_retains_its_view_when_selecting_another_output():
    path = beam() >> beamsplitter()
    back = path.reverse()
    selected = back.straight()
    assert selected.end == back
    assert selected.reverse() == path.end
    reflected = selected.reflect() >> detector()
    assert reflected.end.instance.heading == 90
    assert path.setup.connections[-1].output == dict(path.end.instance.geometry.reverse_ports)["reflect"]


def test_compatible_closed_loop_uses_existing_heading_and_placement_constraints():
    path = beam() >> beamsplitter()
    split = path.end
    loop = split.straight() >> mirror(turn="right") >> mirror(turn="right") >> mirror(turn="right")
    loop.connect(split.input("secondary"))
    result = path.layout()
    assert len(result.placements) == 4
    assert len(path.setup.connections) == 4
    assert result == path.layout()
    for edge in path.setup.connections:
        source, target = result.placements[edge.source], result.placements[edge.target]
        assert source.port_direction(edge.output) == target.port_direction(edge.input)


@pytest.mark.parametrize("pairs", [None, (None,), (("out", "missing"),), (("out", "out"),),
                                    (("out", "back"), ("out", "back")), ((["out"], "back"),)])
def test_invalid_reverse_port_mapping_reports_a_component_error(pairs):
    with pytest.raises(ComponentError, match="Reverse ports"):
        Geometry((Port("out", "output"), Port("back", "output", 180)), reverse_ports=pairs)


@pytest.mark.parametrize("back", [
    Port("back", "input", 180), Port("back", "output", 90),
    Port("back", "output", 180, absolute=True),
    Port("back", "output", medium="fiber"),
])
def test_reverse_port_pairs_must_preserve_kind_and_opposite_free_space_heading(back):
    with pytest.raises(ComponentError, match="opposite free-space headings"):
        Geometry((Port("out", "output"), back), reverse_ports=(("out", "back"),))
