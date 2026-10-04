"""Stage groups retain topology and defer row placement until rendering."""
from dataclasses import replace

import pytest

from beampath import (
    Artwork, ComponentDefinition, ComponentError, ComponentSpec, ConnectionError,
    Geometry, HWP, LayoutError, OpticRef, Port, Style, beam,
    fiber_coupler, fiber_laser, fiber_launch, fiber_power_meter, fiber_splitter,
    inline_power_meter, iris, rows,
)
from beampath.geometry import envelope, overlap
from beampath.layout import segment_intersects


def stage(label="Stage", *, monitor=True, direction="east", origin=(0, 0)):
    split = (beam(direction, origin=origin) >> fiber_launch(f"{label}\nInput")
             >> HWP() >> fiber_coupler() >> fiber_splitter(turn="right"))
    if monitor:
        split.turn() >> inline_power_meter("Branch power") >> fiber_power_meter("Monitor\nreading")
    return split.straight()


def snapshot(path):
    return (path.setup.optics, path.setup.connections, tuple(path.setup._roots),
            dict(path.setup._heading_seeds), path.setup._layout_groups,
            path._end, path._port, path._consumed)


def content_bounds(layout, members):
    bounds = [p.bounds for ident, p in layout.placements.items() if ident in members]
    bounds += [label.bounds for label in layout.labels if label.optic in members]
    points = [p for b in bounds for p in ((b[0], b[1]), (b[2], b[3]))]
    for item in (*layout.segments, *layout.fibers):
        if (item.source in members or item.source is None) and (item.target in members or item.target is None):
            points.extend(item.points if hasattr(item, "points") else (item.start, item.end))
    return envelope(points)


def assert_clear(layout):
    for route in layout.fibers:
        if route.source:
            assert route.start == pytest.approx(layout.placements[route.source].port_position(route.output))
        if route.target:
            assert route.end == pytest.approx(layout.placements[route.target].port_position(route.input))
        for leg in route.legs:
            for placed in layout.placements.values():
                if placed.id not in {route.source, route.target}:
                    assert not segment_intersects(leg.start, leg.end, placed.bounds)
            for label in layout.labels:
                assert not segment_intersects(leg.start, leg.end, label.bounds)
    for i, label in enumerate(layout.labels):
        assert not any(overlap(label.bounds, p.bounds) for p in layout.placements.values())
        assert not any(overlap(label.bounds, other.bounds) for other in layout.labels[i + 1:])


@pytest.mark.parametrize("count", [2, 3])
@pytest.mark.parametrize("gap", [None, 1, 90, 320])
def test_rows_align_entries_and_clear_all_stage_content(count, gap):
    sources = [stage(f"Stage {i}", origin=(80 + i * 130, 60 - i * 100)) for i in range(count)]
    before = [snapshot(source) for source in sources]
    result = rows(*sources, gap=gap)
    layout = result.layout()
    groups = result.setup._layout_groups[0].children
    assert layout.placements[groups[0].entry].position == pytest.approx((80, 60))
    for a, b in zip(groups, groups[1:]):
        assert layout.placements[b.entry].position[0] == pytest.approx(80)
        assert content_bounds(layout, b.members)[1] - content_bounds(layout, a.members)[3] >= (
            (gap if gap is not None else layout.style.pitch) - 1e-7)
    assert [snapshot(source) for source in sources] == before
    assert result.end.id in groups[-1].members
    assert len(result.setup.optics) == sum(len(source.setup.optics) for source in sources)
    assert len(result.setup.connections) == sum(len(source.setup.connections) for source in sources) + count - 1
    assert_clear(layout)
    assert result.layout() == layout


def test_style_is_resolved_late_and_canvas_margin_does_not_space_rows():
    result = rows(stage(), stage())
    before = snapshot(result)
    standard = result.layout()
    bigger = result.layout(style=Style(pitch=270, font_size=35, label_gap=22))
    groups = result.setup._layout_groups[0].children
    assert bigger.placements[groups[1].entry].position[1] > standard.placements[groups[1].entry].position[1]
    assert content_bounds(bigger, groups[1].members)[1] - content_bounds(bigger, groups[0].members)[3] == (
        pytest.approx(270))
    padded = result.layout(style=replace(standard.style, margin=180))
    assert padded.placements == standard.placements
    assert padded.labels == standard.labels
    assert padded.fibers == standard.fibers
    assert padded.bounds == pytest.approx((standard.bounds[0] - 100, standard.bounds[1] - 100,
                                         standard.bounds[2] + 100, standard.bounds[3] + 100))
    assert result.layout(style=replace(standard.style, margin=1e10)).placements == standard.placements
    assert snapshot(result) == before
    assert_clear(bigger)


def test_rows_do_not_measure_boundary_stubs():
    first = fiber_laser("") >> inline_power_meter("")
    last = beam() >> fiber_power_meter("")
    result = rows(first, last)
    normal = result.layout()
    long_stubs = result.layout(style=Style(open_length=1600))
    assert normal.placements == long_stubs.placements
    assert normal.fibers == long_stubs.fibers
    assert not any(route.source is None or route.target is None for route in normal.fibers)


def test_nested_rows_keep_inner_gap_and_are_reusable_with_local_pins():
    pinned = beam(origin=(100, 80)).append(fiber_launch(), at=(120, 90))
    pinned.append(HWP(), at=(470, 90), distance=350) >> fiber_coupler()
    inner = rows(pinned, stage("Inner"), gap=95)
    outer = rows(inner, stage("Outer"), gap=310)
    before = snapshot(outer)
    layout = outer.layout()
    a, b = outer.setup._layout_groups[0].children
    assert content_bounds(layout, b.members)[1] - content_bounds(layout, a.members)[3] == pytest.approx(310)
    inner_a, inner_b = a.children[0].children
    assert content_bounds(layout, inner_b.members)[1] - content_bounds(layout, inner_a.members)[3] == pytest.approx(95)
    assert layout.placements["optic-002"].position[0] - layout.placements["optic-001"].position[0] == (
        pytest.approx(350))
    # Embedding translates the whole arrangement, including all local pins.
    copy = beam(origin=(700, 500)) >> outer
    copied = copy.layout()
    for ident, placed in layout.placements.items():
        assert copied.placements[ident].position == pytest.approx((placed.position[0] + 580, placed.position[1] + 410))
    assert copied.placements["optic-002"].instance.at == (1050, 500)
    assert snapshot(outer) == before
    assert_clear(copied)


def test_repeated_grouped_stages_copy_independently_and_translate_downstream():
    unit = rows(stage(monitor=False), stage(monitor=False), gap=120)
    source = snapshot(unit)
    destination = beam().append(fiber_laser(), at=(-600, 0))
    destination.append(unit, at=(0, 0))
    destination.append(unit, at=(2400, 0))
    destination >> fiber_power_meter("Final")
    layout = destination.layout()
    assert len(destination.setup._layout_groups[0].children[-1].members) == 13
    assert len(destination.setup.optics) == 18
    assert snapshot(unit) == source
    assert_clear(layout)


def test_later_appends_and_branches_expand_their_own_row():
    result = rows(stage(monitor=False), stage(monitor=False))
    before = result.layout()
    first, last = result.setup._layout_groups[0].children
    split = next(ident for ident in first.members
                 if result.setup._nodes[ident].spec.definition.name == "fiber_splitter")
    branch = OpticRef(result.setup, split).turn()
    branch >> inline_power_meter() >> inline_power_meter() >> fiber_power_meter("Added monitor")
    result >> inline_power_meter() >> fiber_power_meter("Final")
    after = result.layout()
    grown_first, grown_last = result.setup._layout_groups[0].children
    assert branch.end.id in grown_first.members
    assert result.end.id in grown_last.members
    assert after.placements[last.entry].position[1] > before.placements[last.entry].position[1]
    assert after.placements[first.entry].position == before.placements[first.entry].position
    assert_clear(after)


@pytest.mark.parametrize("direction", ["north", "west", "south"])
def test_rows_preserve_authored_headings_and_first_origin(direction):
    source = beam(direction, origin=(130, 70)) >> fiber_launch() >> HWP() >> fiber_coupler()
    result = rows(source, source)
    layout = result.layout()
    assert layout.placements["optic-001"].position == pytest.approx((130, 70))
    assert layout.placements["optic-004"].position[0] == pytest.approx(130)
    assert [n.heading for n in result.setup.optics] == [n.heading for n in source.setup.optics] * 2
    assert_clear(layout)


def test_single_row_and_group_endpoint_keep_normal_path_semantics():
    source = beam("north", origin=(60, 80)) >> iris() >> HWP()
    one = rows(source)
    assert one.setup is not source.setup
    assert [p.position for p in one.layout().placements.values()] == [
        p.position for p in source.layout().placements.values()]
    grouped = rows(fiber_laser() >> inline_power_meter(),
                   fiber_launch() >> fiber_coupler() >> fiber_splitter())
    with pytest.raises(ConnectionError, match="select an output"):
        grouped >> fiber_power_meter()
    grouped.straight() >> fiber_power_meter("Main")
    grouped.turn() >> fiber_power_meter("Monitor")
    assert_clear(grouped.layout())


def test_shared_optics_are_copied_once_inside_a_row(fiber_mzi):
    mzi = fiber_mzi
    result = rows(fiber_laser() >> inline_power_meter(), mzi)
    assert len(result.setup.optics) == len(mzi.setup.optics) + 2
    recombiner, = [n for n in result.setup.optics if n.spec.label == "NPBS2"]
    assert sum(edge.target == recombiner.id for edge in result.setup.connections) == 2
    assert_clear(result.layout())


def test_grouped_first_row_can_attach_to_a_free_space_receiver():
    source = rows(iris() >> fiber_coupler(), fiber_launch() >> iris())
    destination = beam("east") >> iris("Upstream")
    destination.append(source, distance=420)
    layout = destination.layout()
    boundary = next(segment for segment in layout.segments if segment.id == "segment-001")
    assert boundary.length == pytest.approx(420)
    assert_clear(layout)


def test_attached_stage_does_not_reserve_a_phantom_free_space_lead():
    child = rows(iris("") >> fiber_coupler(""), beam() >> fiber_power_meter(""))
    path = beam() >> iris("")
    path.append(child, distance=420)
    normal = path.layout()
    long_lead = path.layout(style=Style(open_length=2000))
    assert normal.placements == long_lead.placements
    assert normal.fibers == long_lead.fibers
    assert len([s for s in long_lead.segments if s.source is None]) == 1


def test_incompatible_group_pins_cannot_silently_overlap_labels():
    split = fiber_laser() >> fiber_splitter()
    meter = rows(beam() >> fiber_power_meter("A long label " * 6))
    split.straight().append(meter, at=(0, 600))
    split.turn().append(meter, at=(150, 600))
    with pytest.raises(LayoutError, match="stage labels overlap"):
        split.layout()


@pytest.mark.parametrize("turn", ["left", "right"])
@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize("style", [Style(), Style(pitch=20, clearance=40), Style(pitch=5, clearance=2)])
def test_parent_reserves_fixed_child_label_and_connector_clearance(turn, depth, style):
    meter = beam() >> inline_power_meter("Transmission\npower meter")
    for _ in range(depth):
        meter = rows(meter)
    original = snapshot(meter)
    split = beam(origin=(120, -60)) >> fiber_laser("") >> fiber_splitter("", turn=turn)
    split.turn().append(meter)
    layout = split.layout(style=style)
    assert_clear(layout)
    placed = layout.placements["optic-003"]
    label, = layout.labels
    local = meter.layout(style=style)
    assert placed.rotation == local.placements["optic-001"].rotation
    assert tuple(label.position[i] - placed.position[i] for i in (0, 1)) == pytest.approx(
        tuple(local.labels[0].position[i] - local.placements["optic-001"].position[i] for i in (0, 1)))
    assert snapshot(meter) == original
    assert layout == split.layout(style=style)


def _unlit_box(bounds=(-5, -5, 5, 5), *, source=False):
    ports = (Port("out", "output"),) if source else (Port("in", "input", draw_lead_in=False),)
    return ComponentSpec(ComponentDefinition(
        "box", "", Artwork((0, 0), bounds, svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda p: Geometry(ports), default_input=None if source else "in"))


@pytest.mark.parametrize("content", ["label", "fiber", "beam"])
def test_unpinned_stage_moves_as_a_frame_to_clear_all_fixed_content(content):
    unit = fiber_launch("Input") >> HWP("Waveplate") >> fiber_coupler("Output")
    path = fiber_laser("") >> rows(unit, unit)
    before = path.layout()
    members = set(before.placements) - {"optic-001"}
    if content == "label":
        box = before.labels[0].bounds
        position = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    else:
        if content == "fiber":
            route = next(r for r in before.fibers
                         if r.source in members and r.target in members and len(r.points) > 2)
            segment = max(route.legs, key=lambda s: s.length)
        else:
            segment = before.segments[0]
        position = tuple((a + b) / 2 for a, b in zip(segment.start, segment.end))
    obstacle = path.setup.beam(origin=position) >> _unlit_box()
    result = path.layout()
    assert_clear(result)
    assert result.placements[obstacle.end.id].position == pytest.approx(position)
    entry = min(members)
    delta = tuple(result.placements[entry].position[i] - before.placements[entry].position[i] for i in (0, 1))
    assert delta != (0, 0)
    for ident in members:
        assert result.placements[ident].position == pytest.approx(
            tuple(before.placements[ident].position[i] + delta[i] for i in (0, 1)))


@pytest.mark.parametrize("fixed", [False, True])
def test_beam_solver_reserves_group_labels_without_relaxing_distance(fixed):
    source = _unlit_box((-5, -5, 5, 160), source=True)
    child = rows(iris("Transmission monitoring input") >> fiber_coupler(""),
                 beam() >> fiber_power_meter(""))
    path = beam() >> source
    path.append(child, distance=190 if fixed else None)
    if fixed:
        with pytest.raises(LayoutError, match="stage label overlaps component artwork"):
            path.layout()
    else:
        layout = path.layout()
        assert_clear(layout)
        boundary = next(s for s in layout.segments if s.source == "optic-001")
        assert boundary.length > layout.style.pitch


def test_parent_can_use_empty_space_inside_a_measured_stage():
    unit = fiber_launch("") >> HWP("") >> fiber_coupler("")
    path = fiber_laser("") >> rows(unit, unit)
    before = path.layout()
    segment = before.segments[0]
    position = ((segment.start[0] + segment.end[0]) / 2, segment.start[1] + 80)
    path.setup.beam(origin=position) >> _unlit_box()
    result = path.layout()
    assert_clear(result)
    for ident, p in before.placements.items():
        assert result.placements[ident].position == pytest.approx(p.position)


def test_fixed_child_connector_conflict_does_not_relax_parent_pins():
    # A mixed component's optical frame fixes its pose. Rotating a fiber-only
    # source would otherwise be a legitimate way to escape these position pins.
    source = ComponentSpec(ComponentDefinition(
        "fixed-source", "", Artwork((0, 0), (-5, -5, 5, 5),
                                     svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda p: Geometry((Port("alignment", "output", draw_open=False),
                            Port("fiber", "output", medium="fiber", exit_direction=270)), heading=0),
        default_input=None))
    path = beam() >> source
    path.out("fiber").append(rows(beam() >> inline_power_meter("Transmission\npower meter")),
                             at=(0, -175))
    with pytest.raises(LayoutError, match="pinned placement.*fiber connector has insufficient clearance"):
        path.layout()


def test_rows_expand_for_oblique_boundary_connector_escapes():
    artwork = Artwork((0, 0), (-300, -20, 300, 20),
                      svg='<svg xmlns="http://www.w3.org/2000/svg"/>')
    source = ComponentSpec(ComponentDefinition(
        "wide-source", "", artwork,
        lambda p: Geometry((Port("out", "output", medium="fiber", exit_direction=45),)),
        default_input=None))
    sink = ComponentSpec(ComponentDefinition(
        "wide-sink", "", artwork,
        lambda p: Geometry((Port("in", "input", medium="fiber", exit_direction=270),))))
    path = rows(beam() >> source, beam() >> sink, gap=1)
    layout = path.layout()
    first, second = layout.placements.values()
    assert first.position == (0, 0)
    assert second.position[0] == 0
    assert second.bounds[1] - first.bounds[3] > 2 * layout.style.clearance
    assert_clear(layout)


def test_parent_beam_can_cross_a_fixed_stage_fiber():
    unit = fiber_launch("") >> HWP("") >> fiber_coupler("")
    path = fiber_laser("") >> rows(unit, unit)
    before = path.layout()
    route = next(r for r in before.fibers if len(r.points) > 2)
    leg = max(route.legs, key=lambda s: s.length)
    x, y = (leg.start[0] + leg.end[0]) / 2, leg.start[1]
    assert leg.start[1] == leg.end[1]
    crossing = path.setup.beam("south", origin=(x, y - 60)) >> _unlit_box(source=True)
    result = path.layout()
    stub = next(s for s in result.segments if s.source == crossing.end.id)
    assert stub.start[1] < y < stub.end[1]
    assert_clear(result)
    for ident, p in before.placements.items():
        assert result.placements[ident].position == pytest.approx(p.position)


@pytest.mark.parametrize("case", ["no_stages", "non_path", "free_space", "wrong_input", "terminal",
                                  "group", "stale", "consumed", "empty", "roots", "disconnected"])
def test_invalid_rows_leave_every_source_intact(case):
    a, b = stage(monitor=False), stage(monitor=False)
    args = (a, b)
    if case == "no_stages":
        args = ()
    elif case == "non_path":
        args = (a, iris())
    elif case == "free_space":
        a, b = iris() >> HWP(), iris() >> HWP()
        args = (a, b)
    elif case == "wrong_input":
        b = iris() >> HWP()
        args = (a, b)
    elif case == "terminal":
        a >> fiber_power_meter()
    elif case == "group":
        a = fiber_launch() >> fiber_coupler() >> fiber_splitter()
        args = (a, b)
    elif case == "stale":
        a.end.straight() >> fiber_power_meter()
    elif case == "consumed":
        a.connect(a.setup.add(fiber_power_meter()).input())
    elif case == "empty":
        b = beam()
        args = (a, b)
    elif case == "roots":
        b.setup.beam(origin=(0, 800)) >> iris()
    elif case == "disconnected":
        b.setup.add(iris())
    before = snapshot(a), snapshot(b)
    with pytest.raises(ConnectionError):
        rows(*args)
    assert (snapshot(a), snapshot(b)) == before


@pytest.mark.parametrize("gap", [0, -1, float("inf"), float("nan"), "bad"])
def test_invalid_gap(gap):
    with pytest.raises((ConnectionError, ComponentError), match="positive|finite"):
        rows(stage(), gap=gap)


def test_failed_append_rolls_back_group_membership_and_remains_usable():
    result = rows(stage(), stage())
    before = snapshot(result)
    # The first item joins the final row before the second fails on medium.
    with pytest.raises(ConnectionError):
        result >> (inline_power_meter() >> iris())
    assert snapshot(result) == before
    result >> fiber_power_meter()
    assert_clear(result.layout())
