import json
import math
import xml.etree.ElementTree as ET

import pytest

from beampath import (
    Artwork, ComponentDefinition, ComponentError, ComponentSpec, ConnectionError, Geometry, HWP,
    Label, LayoutError, Port, Setup, Style, beam, fiber_laser, fiber_launch, fiber_coupler,
    inline_power_meter, iris, fiber_splitter,
)
from beampath.layout import artwork_point, segment_intersects
from beampath.render import tag
from beampath.routing import rounded_path, route_connection


def mixed(output_at=None):
    path = (fiber_laser("Tunable laser") >> inline_power_meter("Input power")
            >> fiber_launch() >> HWP() >> fiber_coupler())
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


@pytest.mark.parametrize("turn,sign", [("left", -1), ("right", 1)])
@pytest.mark.parametrize("branch_first", [False, True])
def test_fiber_splitter_has_straight_and_perpendicular_runs(turn, sign, branch_first):
    split = fiber_laser("") >> fiber_splitter("", turn=turn)
    ref = split.end
    before = split.setup.optics, split.setup.connections
    with pytest.raises(ConnectionError, match="select an output"):
        split >> inline_power_meter("")
    assert (split.setup.optics, split.setup.connections) == before
    if branch_first:
        branch = ref.turn() >> inline_power_meter("")
        main = split.straight() >> fiber_launch("", heading="east")
    else:
        main = ref.straight() >> fiber_launch("", heading="east")
        branch = split.turn() >> inline_power_meter("")
    layout = split.layout()
    junction = layout.placements[ref.id]
    assert junction.rotation == 0
    assert junction.instance.heading is None
    assert all(p.medium == "fiber" and p.direction is None for p in junction.instance.geometry.ports)
    routes = {r.output: r for r in layout.fibers if r.source == ref.id}
    straight, turned = routes["straight"], routes["turn"]
    assert len(straight.points) == len(turned.points) == 2
    assert straight.start[1] == straight.end[1] == junction.position[1]
    assert straight.end[0] > straight.start[0]
    assert turned.start[0] == turned.end[0] == junction.port_position("turn")[0]
    assert sign * (turned.end[1] - turned.start[1]) > 0
    assert branch.end.instance.heading is None
    assert main.end.instance.heading == 0
    with pytest.raises(ConnectionError, match="already connected"):
        split.turn()
    assert_routes_clear(layout)


@pytest.mark.parametrize("turn,sign", [("left", -1), ("right", 1)])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_fiber_splitter_rotates_docks_without_setting_optical_headings(turn, sign, rotation):
    radians = math.radians(rotation)
    axis = math.cos(radians), math.sin(radians)
    side = -sign * axis[1], sign * axis[0]
    split = beam().append(fiber_laser(""), at=(0, 0))
    split.append(fiber_splitter("", turn=turn), at=tuple(250 * v for v in axis))
    ref = split.end
    split.straight().append(inline_power_meter(""), at=tuple(500 * v for v in axis))
    split.turn().append(inline_power_meter(""),
                        at=tuple(280 * axis[i] + 250 * side[i] for i in (0, 1)))
    layout = split.layout()
    junction = layout.placements[ref.id]
    assert junction.rotation == rotation
    assert all(node.heading is None for node in split.setup.optics)
    docks = {"in": (20, 60), "straight": (120, 60), "turn": (90, 10)}
    for name, dock in docks.items():
        offset = artwork_point(junction.instance, dock, junction.rotation)
        assert junction.port_position(name) == pytest.approx(
            tuple(junction.position[i] + offset[i] for i in (0, 1)))
    assert all(len(r.points) == 2 for r in layout.fibers)
    assert_routes_clear(layout)


def test_fiber_splitter_curve_matches_routed_fiber_style_and_unused_output():
    split = fiber_laser("") >> fiber_splitter("90:10 splitter")
    ref = split.end
    split.straight() >> fiber_launch("")
    layout = split.layout(style=Style(fiber_color="#112233", fiber_width=6))
    stub, = [r for r in layout.fibers if r.source == ref.id and r.output == "turn"]
    assert stub.target is None
    assert stub.length == pytest.approx(layout.style.open_length)
    assert stub.start[0] == stub.end[0] and stub.end[1] < stub.start[1]
    root = ET.fromstring(split.to_svg(style=layout.style))
    symbol = root.find(f"{tag('g')}[@id='components']/{tag('g')}[@id='{ref.id}']")
    assert not symbol.findall(tag("rect")) and not symbol.findall(tag("text"))
    through, = symbol.findall(tag("line"))
    curve, = symbol.findall(tag("path"))
    assert " C" in curve.get("d")
    for primitive in (through, curve):
        assert primitive.get("stroke") == layout.style.fiber_color
        assert float(primitive.get("stroke-width")) * ref.instance.spec.definition.artwork.scale == layout.style.fiber_width
    manifest = json.loads(root.find(f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    asset, = [a for a in manifest["assets"] if a["component"] == "fiber_splitter"]
    assert asset["source_url"] == ""
    assert "Original beampath schematic artwork" in asset["attribution"]
    assert_routes_clear(layout)


@pytest.mark.parametrize("turn", ["up", "", None, 90])
def test_fiber_splitter_rejects_invalid_turn(turn):
    with pytest.raises(ComponentError, match="turn must be 'left' or 'right'"):
        fiber_splitter(turn=turn)


@pytest.mark.parametrize("direction", [0, 90, 180, 270, 31.7])
def test_launch_seeds_independent_heading_after_fiber(direction):
    p = fiber_laser("") >> fiber_launch(heading=direction) >> HWP() >> fiber_coupler()
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
        p >> fiber_coupler(heading="north")
    assert (p.setup.optics, p.setup.connections) == before


@pytest.mark.parametrize("spec", [iris(), fiber_coupler()])
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
    with pytest.raises(LayoutError, match="pinned placement.*component artwork overlaps"):
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
    # The short tap fiber inside the instrument follows the routed fiber style.
    components = svg.find(f"{tag('g')}[@id='components']")
    tap, = components.iter(tag("line"))
    assert tap.get("stroke") == style.fiber_color
    assert float(tap.get("stroke-width")) * p.end.instance.spec.definition.artwork.scale == style.fiber_width
    assert all(route.length == style.open_length for route in result.fibers)


def test_avoidable_crossing_is_rerouted_without_creating_junctions():
    from beampath.fiber_conflicts import route_set_score
    setup = Setup()
    a = setup.beam(origin=(-800, 0)) >> fiber_laser("")
    a.append(inline_power_meter(""), at=(800, 0))
    b = setup.beam(origin=(0, -700)) >> fiber_laser("")
    b.append(inline_power_meter(""), at=(0, 700))
    before = setup.optics, setup.connections
    result = setup.layout()
    assert len(result.placements) == 4
    routes = [r for r in result.fibers if r.target]
    assert len(routes) == 2
    assert route_set_score(result.fibers)[:2] == (0, 0)
    assert any(len(r.points) > 2 for r in routes)
    assert routes[0].start[1] == routes[0].end[1] == 0
    assert routes[1].start[0] == routes[1].end[0] == 0
    assert (setup.optics, setup.connections) == before
    assert_routes_clear(result)


def test_router_can_detour_around_reserved_label_bounds():
    path = beam().append(fiber_laser(""))
    path.append(inline_power_meter(""), at=(600, 0))
    layout = path.layout()
    label = Label("note", "Reserved label", (300, 0), (270, -20, 330, 20))
    route = route_connection(path.setup.connections[0], layout.placements, layout.style, [label])
    assert len(route.points) > 2
    assert all(not segment_intersects(leg.start, leg.end, label.bounds) for leg in route.legs)


@pytest.mark.parametrize("medium", ["fiber", "free_space"])
def test_two_initial_paths_cannot_pin_one_component_to_different_positions(medium):
    setup = Setup()
    shared = setup.add(fiber_component("shared", [
        Port("in", "input", medium=medium), Port("other", "input", medium=medium),
        Port("out", "output", medium=medium)]))
    setup.beam().connect(shared.input())
    setup.beam(origin=(50, 0)).connect(shared.input("other"))
    with pytest.raises(LayoutError, match="incompatible placement constraints"):
        setup.layout()


def test_pinned_input_meter_keeps_free_space_heading_independent():
    p = beam().append(fiber_laser(""))
    p.append(inline_power_meter(""), at=(0, 650))
    p >> fiber_launch() >> HWP() >> fiber_coupler() >> inline_power_meter("")
    result = p.layout()
    assert result.placements["optic-002"].position == (0, 650)
    assert result.placements["optic-002"].rotation == 90
    assert [p.instance.heading for p in result.placements.values()][2:5] == [0, 0, 0]
    assert_routes_clear(result)


def test_pinned_fiber_device_can_rotate_to_clear_artwork():
    device = fiber_component("wide", [
        Port("in", "input", medium="fiber", position=(-100, 0), draw_lead_in=False),
        Port("out", "output", medium="fiber", position=(100, 0), draw_open=False),
    ], (-100, -10, 100, 10))
    p = beam().append(device)
    p.append(device, at=(150, 0))
    result = p.layout()
    assert result.placements["optic-002"].rotation in (90, 270)
    assert result.placements["optic-002"].position == (150, 0)
    assert_routes_clear(result)


@pytest.mark.parametrize("factory,incoming,outgoing", [
    (fiber_laser, 0, 1), (inline_power_meter, 1, 1),
    (fiber_launch, 1, 0), (fiber_coupler, 0, 1),
])
def test_standalone_fiber_ports_have_null_ended_stubs(factory, incoming, outgoing):
    path = beam().append(factory())
    before = path.setup.optics, path.setup.connections
    layout = path.layout()
    assert len(layout.placements) == 1
    assert len([r for r in layout.fibers if r.source is None]) == incoming
    assert len([r for r in layout.fibers if r.target is None]) == outgoing
    assert all(r.length == pytest.approx(layout.style.open_length) for r in layout.fibers)
    assert (path.setup.optics, path.setup.connections) == before
    assert before[1] == ()
    assert_routes_clear(layout)


def test_connected_fiber_replaces_open_stub_without_adding_components():
    path = beam().append(inline_power_meter("Input power"))
    before = path.layout()
    before_end = path.end.id
    open_output, = [r for r in before.fibers if r.target is None]
    path >> fiber_launch() >> HWP() >> fiber_coupler() >> inline_power_meter("Output power")
    after = path.layout()
    connected, = [r for r in after.fibers if r.source == before_end]
    assert connected.target == "optic-002"
    assert connected.start == open_output.start
    assert len(after.placements) == len(path.setup.optics) == 5
    assert len(path.setup.connections) == 4
    assert len([r for r in after.fibers if r.source is None]) == 1
    assert len([r for r in after.fibers if r.target is None]) == 1
    assert_routes_clear(after)


@pytest.mark.parametrize("spec,attachments", [
    (fiber_laser(""), {"out": (115, 32)}),
    (inline_power_meter(""), {"in": (85, 27), "out": (85, 27)}),
    (fiber_launch("", heading=31.7), {"in": (110, 27)}),
    (fiber_coupler("", heading=31.7), {"out": (110, 27)}),
])
def test_fiber_docks_at_asset_attachment_without_embedded_cable(spec, attachments):
    path = beam(31.7).append(spec)
    layout = path.layout()
    placed = layout.placements[path.end.id]
    for name, asset_point in attachments.items():
        offset = artwork_point(placed.instance, asset_point, placed.rotation)
        expected = tuple(placed.position[i] + offset[i] for i in (0, 1))
        assert placed.port_position(name) == pytest.approx(expected)
    svg = ET.fromstring(path.to_svg())
    components = svg.find(f"{tag('g')}[@id='components']")
    cables = [node for node in components.iter() if node.get("stroke") == layout.style.fiber_color]
    if spec.definition.name == "inline_power_meter":
        tap, = cables
        assert tap.tag == tag("line") and tap.get("x1") == tap.get("x2")
        assert float(tap.get("stroke-width")) * spec.definition.artwork.scale == layout.style.fiber_width
    else:
        assert not cables
    assert_routes_clear(layout)


@pytest.mark.parametrize("pitch", [190, 300])
def test_fiber_and_free_space_pitch_measures_the_gap_between_ports(pitch):
    path = mixed()
    layout = path.layout(style=Style(pitch=pitch))
    fibers = [r for r in layout.fibers if r.source and r.target]
    assert len(fibers) == 3
    assert [r.length for r in fibers] == pytest.approx([pitch] * 3)
    assert [s.length for s in layout.segments] == pytest.approx([pitch] * 2)
    # Attachment offsets enlarge center spacing, never consume the cable gap.
    laser, meter, launch = list(layout.placements.values())[:3]
    assert meter.position[0] - laser.position[0] == pytest.approx(pitch + 75)
    assert launch.position[0] - meter.position[0] == pytest.approx(pitch + 152.4)
    assert_routes_clear(layout)


def test_unused_optional_fiber_input_has_an_open_stub():
    device = fiber_component("optional-input", [
        Port("in", "input", medium="fiber", position=(-20, -10)),
        Port("spare", "input", medium="fiber", position=(-20, 10), required=False),
        Port("out", "output", medium="fiber", position=(20, 0)),
    ])
    path = fiber_laser("") >> device
    before = path.setup.optics, path.setup.connections
    layout = path.layout()
    spare, = [r for r in layout.fibers if r.input == "spare"]
    assert spare.source is None and spare.output is None
    assert spare.target == path.end.id
    assert (path.setup.optics, path.setup.connections) == before
