import json
import math
import xml.etree.ElementTree as ET

import pytest

from beampath import (
    Artwork, ComponentDefinition, ComponentSpec, ConnectionError, Geometry, HWP,
    LayoutError, Port, Setup, Style, beam, fiber_laser, fiber_launch,
    inline_power_meter, iris,
)
from beampath.layout import segment_intersects
from beampath.render import tag
from beampath.routing import rounded_path


def mixed(output_at=None):
    path = (fiber_laser("Tunable laser") >> inline_power_meter("Input power")
            >> fiber_launch() >> HWP() >> fiber_launch(role="couple"))
    return path.append(inline_power_meter("Output power"), at=output_at)


def fiber_component(name, ports, bounds=(-20, -20, 20, 20)):
    return ComponentSpec(ComponentDefinition(name, "", Artwork(
        (0, 0), bounds, svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda p: Geometry(tuple(ports))))


def assert_routes_clear(layout):
    for route in layout.fibers:
        for leg in route.legs:
            for placed in layout.placements.values():
                if placed.id not in {route.source, route.target}:
                    assert not segment_intersects(leg.start, leg.end, placed.bounds)
            for label in layout.labels:
                assert not segment_intersects(leg.start, leg.end, label.bounds)
        for point in route.points:
            assert layout.bounds[0] <= point[0] <= layout.bounds[2]
            assert layout.bounds[1] <= point[1] <= layout.bounds[3]
        if route.source:
            assert route.start == pytest.approx(layout.placements[route.source].port_position(route.output))
        if route.target:
            assert route.end == pytest.approx(layout.placements[route.target].port_position(route.input))


def test_mixed_chain_is_semantic_straight_and_repeatable():
    path = mixed()
    before = path.setup.optics, path.setup.connections
    layout = path.layout()
    assert len(layout.placements) == 6
    assert [e.medium for e in path.setup.connections] == ["fiber", "fiber", "free_space", "free_space", "fiber"]
    assert [n.heading for n in path.setup.optics] == [None, None, 0, 0, 0, None]
    assert len(layout.segments) == 2
    assert len([r for r in layout.fibers if r.target]) == 3
    assert all(p.position[1] == 0 for p in layout.placements.values())
    assert all(len(route.points) == 2 for route in layout.fibers)
    assert path.layout() == layout
    assert (path.setup.optics, path.setup.connections) == before
    assert_routes_clear(layout)


@pytest.mark.parametrize("position", [(1900, -400), (1900, 400), (-500, -400)])
def test_pinned_output_meter_routes_without_changing_beam_section(position):
    straight = mixed().layout()
    layout = mixed(position).layout()
    for ident in ("optic-003", "optic-004", "optic-005"):
        assert layout.placements[ident] == straight.placements[ident]
    assert layout.placements["optic-006"].position == position
    route = next(r for r in layout.fibers if r.id == "segment-005")
    assert len(route.points) > 2
    assert_routes_clear(layout)


def test_vertical_fiber_components_have_pose_but_no_heading():
    p = beam().append(fiber_laser(""))
    p.append(inline_power_meter(""), at=(0, 650))
    layout = p.layout()
    assert [v.rotation for v in layout.placements.values()] == [90, 90]
    assert all(n.heading is None for n in p.setup.optics)
    assert all(len(route.points) == 2 for route in layout.fibers)
    assert layout.placements[p.end.id].port_direction("in") is None
    assert_routes_clear(layout)


def test_unpinned_meter_follows_a_vertical_run_toward_a_pin():
    p = fiber_laser("") >> inline_power_meter("")
    p.append(inline_power_meter(""), at=(0, 1200))
    layout = p.layout()
    assert all(p.position[0] == 0 for p in layout.placements.values())
    assert all(p.rotation == 90 for p in layout.placements.values())
    assert_routes_clear(layout)


def test_fiber_detours_around_an_unrelated_component():
    p = beam().append(fiber_laser(""))
    p.append(inline_power_meter(""), at=(900, 0))
    obstacle = fiber_component("obstacle", [Port("in", "input", medium="fiber", draw_lead_in=False)],
                               (-40, -120, 40, 120))
    p.setup.beam(origin=(470, 0)) >> obstacle
    layout = p.layout()
    route = next(r for r in layout.fibers if r.target)
    assert len(route.points) >= 4
    assert any(abs(y) >= 140 for _, y in route.points)
    assert_routes_clear(layout)


def test_fiber_branch_and_rejoin_use_existing_graph_api():
    splitter = fiber_component("splitter", [
        Port("in", "input", medium="fiber", position=(-20, 0)),
        Port("a", "output", medium="fiber", position=(20, -10)),
        Port("b", "output", medium="fiber", position=(20, 10)),
    ])
    combiner = fiber_component("combiner", [
        Port("in", "input", medium="fiber", position=(-20, -10)),
        Port("other", "input", medium="fiber", position=(-20, 10)),
        Port("out", "output", medium="fiber", position=(20, 0)),
    ])
    fork = fiber_laser("") >> splitter
    a = fork.out("a") >> inline_power_meter("")
    b = fork.out("b") >> inline_power_meter("")
    joined = a.join(b, combiner)
    joined >> fiber_launch() >> HWP()
    layout = joined.layout()
    assert len(layout.placements) == 7
    assert len([r for r in layout.fibers if r.target]) == 6
    assert len(joined.setup.connections) == 7
    assert_routes_clear(layout)


@pytest.mark.parametrize("direction", [0, 90, 180, 270, 31.7])
def test_launch_seeds_independent_heading_after_fiber(direction):
    p = fiber_laser("") >> fiber_launch(heading=direction) >> HWP() >> fiber_launch(role="couple")
    p >> inline_power_meter("") >> fiber_launch(heading="north") >> HWP()
    assert [n.heading for n in p.setup.optics] == [None, direction, direction, direction, None, 270, 270]
    layout = p.layout()
    assert_routes_clear(layout)
    route = next(r for r in layout.fibers if r.id == "segment-001")
    a, b = route.points[-2:]
    assert math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360 == pytest.approx(direction)


def test_explicit_launch_and_legacy_beam_heading():
    assert (fiber_launch(heading="north") >> HWP()).end.instance.heading == 270
    assert (beam("west") >> fiber_launch() >> HWP()).end.instance.heading == 180
    p = fiber_laser() >> fiber_launch(heading="east") >> HWP()
    before = p.setup.optics, p.setup.connections
    with pytest.raises(ConnectionError, match="disagrees"):
        p >> fiber_launch(role="couple", heading="north")
    assert (p.setup.optics, p.setup.connections) == before


@pytest.mark.parametrize("spec", [iris(), fiber_launch(role="couple")])
def test_mismatched_media_reject_atomically(spec):
    p = fiber_laser() >> inline_power_meter()
    before = p.setup.optics, p.setup.connections, p.end
    with pytest.raises(ConnectionError, match=r"optic-002.out \(fiber\).*optic-003.in \(free_space\)"):
        p >> spec
    assert (p.setup.optics, p.setup.connections, p.end) == before
    p >> fiber_launch()


def test_fiber_distance_rejects_append_and_connect_atomically():
    p = beam().append(fiber_laser())
    before = p.setup.optics, p.setup.connections, p.end
    with pytest.raises(ConnectionError, match="distance=.*free-space"):
        p.append(inline_power_meter(), distance=300)
    assert (p.setup.optics, p.setup.connections, p.end) == before
    target = p.setup.add(inline_power_meter())
    with pytest.raises(ConnectionError, match="distance=.*free-space"):
        p.connect(target.input(), distance=300)
    p.connect(target.input())
    assert len(p.layout().placements) == 2


def test_unconnected_fiber_components_and_conflicting_pins_fail_clearly():
    setup = Setup()
    setup.add(fiber_laser())
    with pytest.raises(LayoutError, match="connect the optic"):
        setup.layout()
    p = beam().append(fiber_laser())
    p.append(inline_power_meter(), at=(0, 0))
    with pytest.raises(LayoutError, match="pinned component artwork overlaps"):
        p.layout()


def test_fiber_svg_paths_metadata_and_safe_rounding():
    p = mixed((1900, -400))
    layout = p.layout()
    root = ET.fromstring(p.to_svg())
    group = root.find(f"{tag('g')}[@id='fiber-path']")
    assert group.get("stroke") == "#1B1E89"
    assert len(group.findall(tag("path"))) == len(layout.fibers)
    assert any(" Q " in path.get("d") for path in group)
    assert all(path.get("marker-end") is None for path in group)
    manifest = json.loads(root.find(f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    assert len(manifest["optics"]) == 6
    assert manifest["optics"][0]["heading"] is None
    assert manifest["optics"][-1]["artwork_rotation"] == 270
    assert len(manifest["fibers"]) == len(layout.fibers)
    assert all(len(a["points"]) == len(b.points) for a, b in zip(manifest["fibers"], layout.fibers))
    route = next(r for r in layout.fibers if len(r.points) > 2)
    assert " Q " not in rounded_path(route, 0, (), 3)
    corner = route.points[1]
    obstacle = (corner[0] - 20, corner[1] - 20, corner[0] + 20, corner[1] + 20)
    assert " Q " not in rounded_path(route, 10, (obstacle,), 3)


def test_fiber_style_and_root_stub():
    p = beam().append(inline_power_meter(""))
    style = Style(fiber_color="#112233", fiber_width=6, fiber_radius=0)
    result = p.layout(style=style)
    assert len(result.fibers) == 2
    assert len(result.segments) == 0
    svg = ET.fromstring(p.to_svg(style=style))
    group = svg.find(f"{tag('g')}[@id='fiber-path']")
    assert group.get("stroke") == "#112233"
    assert group.get("stroke-width") == "6"
