from dataclasses import FrozenInstanceError
import math
from uuid import uuid4

import pytest

from beampath import (
    Artwork, ComponentDefinition, ComponentSpec, Geometry, HWP, LP, LayoutError,
    Port, QWP, Setup, Style, beam, beamsplitter, component, fiber_launch, fiber_coupler, iris,
    mirror, register_component,
)
from beampath.examples import cage_system, mzi
from beampath.layout import segment_intersects


@pytest.mark.parametrize("direction", [0, 90, 180, 270, 31.7])
def test_input_stub_follows_heading_and_preserves_graph(direction):
    path = beam(direction, origin=(120, -60)) >> mirror(turn="left") >> iris()
    before = path.setup.optics, path.setup.connections
    result = path.layout()
    lead, = [s for s in result.segments if s.source is None]
    first = result.placements["optic-001"]
    assert first.position == (120, -60)
    assert lead.output is None and lead.target == first.id and lead.input == "in"
    assert lead.end == pytest.approx(first.port_position("in"))
    assert lead.length == pytest.approx(result.style.open_length)
    assert tuple(lead.end[i] - lead.start[i] for i in (0, 1)) == pytest.approx((
        95 * math.cos(math.radians(direction)), 95 * math.sin(math.radians(direction))))
    assert (path.setup.optics, path.setup.connections) == before
    assert len(result.placements) == 2 and len(path.setup.connections) == 1
    assert all(not segment_intersects(lead.start, lead.end, label.bounds)
               for label in result.labels)
    x0, y0, x1, y1 = result.bounds
    for x, y in (lead.start, lead.end):
        assert x0 + result.style.margin <= x <= x1 - result.style.margin
        assert y0 + result.style.margin <= y <= y1 - result.style.margin


def test_shorthand_chain_draws_the_same_input_stub_as_explicit_beam():
    shorthand = (iris() >> HWP()).layout()
    explicit = (beam() >> iris() >> HWP()).layout()
    assert shorthand == explicit
    assert len([s for s in shorthand.segments if s.source is None]) == 1


def test_input_stub_uses_displaced_port_and_extends_for_artwork():
    spec = ComponentSpec(ComponentDefinition(
        "wide", "", Artwork((0, 0), (-150, -20, 40, 20),
                            svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda p: Geometry((Port("in", "input", position=(-20, 5)),
                            Port("out", "output", position=(10, 5))))))
    path = beam(origin=(100, -70)).append(spec, at=(500, 60))
    result = path.layout(style=Style(open_length=30, clearance=20))
    lead, = [s for s in result.segments if s.source is None]
    assert result.placements[path.end.id].position == (500, 60)
    assert lead.end == pytest.approx((480, 65))
    assert lead.start == pytest.approx((330, 65))
    assert lead.length == pytest.approx(150)


@pytest.mark.parametrize("direction", [0, 90, 180, 270, 31.7])
@pytest.mark.parametrize("factory", [fiber_launch, fiber_coupler])
def test_fiber_launch_has_no_input_stub_but_coupler_does(direction, factory):
    path = beam(direction) >> factory()
    result = path.layout()
    leads = [s for s in result.segments if s.source is None]
    if factory is fiber_launch:
        assert leads == []
        outgoing, = result.segments
        assert outgoing.source == path.end.id and outgoing.target is None
    else:
        lead, = result.segments
        assert leads == [lead]
        assert lead.target == path.end.id and lead.input == "in"
        assert tuple((lead.end[i] - lead.start[i]) / lead.length
                     for i in (0, 1)) == pytest.approx((
                         math.cos(math.radians(direction)), math.sin(math.radians(direction))))


@pytest.mark.parametrize("ports,default_input", [
    ((Port("out", "output"),), None),
    ((Port("in", "input", draw_lead_in=False), Port("out", "output")), "in"),
])
def test_custom_sources_can_omit_input_stub(ports, default_input):
    spec = ComponentSpec(ComponentDefinition(
        "source", "", Artwork((0, 0), (-5, -5, 5, 5),
                              svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda p: Geometry(ports), default_input=default_input))
    result = (beam() >> spec).layout()
    outgoing, = result.segments
    assert outgoing.source == "optic-001" and outgoing.target is None


def test_splitter_only_draws_input_stubs_for_bound_roots():
    result = (beam() >> beamsplitter(angle=-45)).layout()
    lead, = [s for s in result.segments if s.source is None]
    assert lead.input == "primary"


def test_input_stub_crossing_unrelated_optic_fails():
    blocker = ComponentSpec(ComponentDefinition(
        "blocker", "", Artwork((0, 0), (-5, -5, 5, 5),
                               svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda p: Geometry((Port("in", "input", draw_lead_in=False),))))
    drawing = Setup()
    drawing.beam() >> iris(label="")
    drawing.beam(origin=(-70, 0)) >> blocker
    with pytest.raises(LayoutError, match="lead-in-.*beam crosses unrelated optic optic-002"):
        drawing.layout()


def test_cage_layout_and_labels():
    p = cage_system()
    result = p.layout()
    grid = [(0, 0), (1, 0), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
            (6, 1), (7, 1), (8, 1), (9, 1), (9, 0), (10, 0)]
    for optic, (x, y) in zip(result.placements.values(), grid):
        assert optic.position == pytest.approx((190 * x, 190 * y))
    assert len(result.placements) == 13
    assert len(result.segments) == 12
    assert [label.text for label in result.labels] == [n.spec.display_label for n in p.setup.optics]
    assert all(s.length == pytest.approx(190) for s in result.segments)


@pytest.mark.parametrize("direction", [0, 90, 37])
@pytest.mark.parametrize("font_size", [23, 40])
@pytest.mark.parametrize("text", ["HWP\nIn Rotation Mount", "\nHWP\n\nIn Rotation Mount\n"])
def test_multiline_label_bounds_cover_longest_line_and_all_rows(direction, font_size, text):
    style = Style(font_size=font_size)
    result = (beam(direction) >> HWP(text)).layout(style=style)
    label, = result.labels
    lines = text.split("\n")
    single_lines = [(beam(direction) >> HWP(line)).layout(style=style).labels[0]
                    for line in lines if line]
    x0, y0, x1, y1 = label.bounds
    assert label.text == text
    assert x1 - x0 == pytest.approx(max(line.bounds[2] - line.bounds[0] for line in single_lines))
    assert y1 - y0 == pytest.approx(len(lines) * (single_lines[0].bounds[3] - single_lines[0].bounds[1]))
    assert all(not segment_intersects(s.start, s.end, label.bounds) for s in result.segments)
    for placed in result.placements.values():
        a0, b0, a1, b1 = placed.bounds
        assert x1 <= a0 - style.label_gap or x0 >= a1 + style.label_gap or (
            y1 <= b0 - style.label_gap or y0 >= b1 + style.label_gap)
    bx0, by0, bx1, by1 = result.bounds
    assert x0 >= bx0 + style.margin and x1 <= bx1 - style.margin
    assert y0 >= by0 + style.margin and y1 <= by1 - style.margin


def test_unequal_mzi_closes_shared_optic_by_stretching():
    p = mzi()
    result = p.layout()
    combined = next(o for o in result.placements.values() if o.instance.spec.label == "NPBS2")
    incident = [s for s in result.segments if s.source is not None and s.target == combined.id]
    assert sorted(s.length for s in incident) == pytest.approx([380, 570])
    assert all(s.end == pytest.approx(combined.position) for s in incident)
    assert combined.position == pytest.approx((570, 570))
    assert len([o for o in result.placements.values() if o.instance.spec.label == "NPBS2"]) == 1
    assert len([s for s in result.segments if s.source == combined.id]) == 2
    assert p.layout() == result


def test_layout_is_immutable_and_snapshot_survives_edits():
    p = iris() >> HWP()
    layout = p.layout()
    with pytest.raises(TypeError):
        layout.placements["new"] = None
    with pytest.raises(FrozenInstanceError):
        layout.segments[0].start = (0, 1)
    p >> LP()
    assert len(layout.placements) == 2
    assert len(p.layout().placements) == 3


def test_numeric_direction_ports_and_distance_hint():
    p = beam(31.7, origin=(100, -70)) >> iris()
    p.append(HWP(), distance=250)
    result = p.layout()
    assert result.placements["optic-001"].position == (100, -70)
    assert result.segments[0].length == pytest.approx(250)
    dx, dy = (result.segments[0].end[i] - result.segments[0].start[i] for i in (0, 1))
    assert (dx, dy) == pytest.approx((250 * math.cos(math.radians(31.7)), 250 * math.sin(math.radians(31.7))))


def test_position_hint_and_subpitch_explicit_distance():
    p = beam() >> HWP()
    p.append(LP(), distance=100, at=(100, 0))
    assert p.layout().segments[0].length == pytest.approx(100)
    q = beam() >> iris()
    q.append(HWP(), at=(420, 0))
    assert q.layout().segments[0].length == pytest.approx(420)


@pytest.mark.parametrize("hints", [{"distance": 10}, {"at": (0, 100)}, {"distance": 200, "at": (300, 0)}])
def test_infeasible_hints_fail_proximately(hints):
    p = beam() >> iris()
    p.append(HWP(), **hints)
    before = p.setup.optics, p.setup.connections
    with pytest.raises(LayoutError, match="optic-002.in.*incompatible"):
        p.layout()
    assert (p.setup.optics, p.setup.connections) == before


def test_disconnected_and_missing_required_ports():
    drawing = Setup()
    drawing.add(iris())
    with pytest.raises(LayoutError, match="connect the optic"):
        drawing.layout()
    with pytest.raises(LayoutError, match="no components"):
        beam().layout()
    name = "two-inputs-" + uuid4().hex
    register_component(ComponentDefinition(name, "custom", Artwork((0, 0), (-5, -5, 5, 5), svg='<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'),
                        lambda p: Geometry((Port("in", "input"), Port("extra", "input", 90), Port("out", "output")))))
    p = beam() >> component(name)
    with pytest.raises(LayoutError, match="extra.*not connected"):
        p.layout()


def test_multi_root_overlap_fails():
    drawing = Setup()
    drawing.beam() >> iris()
    drawing.beam("north") >> LP()
    with pytest.raises(LayoutError, match="artwork overlaps"):
        drawing.layout()


def test_registration_three_outputs_and_displaced_ports():
    name = "fork-" + uuid4().hex
    register_component(ComponentDefinition(
        name, "Fork", Artwork((0, 0), (-10, -10, 10, 10), svg='<svg xmlns="http://www.w3.org/2000/svg"><rect x="-10" y="-10" width="20" height="20"/></svg>'),
        lambda p: Geometry((Port("in", "input", 0, (-10, 0)),
                            Port("forward", "output", 0, (10, 0)),
                            Port("up", "output", 270, (0, -10)),
                            Port("down", "output", 90, (0, 10))))))
    fork = iris() >> component(name)
    for output in ("forward", "up", "down"):
        fork.out(output) >> LP()
    result = fork.layout()
    node = result.placements[fork.end.id]
    assert node.position == pytest.approx((200, 0))  # 190 gap ends at local x=-10.
    assert node.port_position("forward") == pytest.approx((210, 0))
    assert node.port_position("up") == pytest.approx((200, -10))
    assert node.port_position("down") == pytest.approx((200, 10))
    assert len([s for s in result.segments if s.source == node.id]) == 3
    svg = fork.to_svg()
    assert svg.count('data-component="' + name + '"') == 1


def test_nested_split_layout():
    p = iris() >> beamsplitter(angle=-45)
    p.straight() >> HWP()
    q = p.reflect() >> beamsplitter(angle=45)
    q.straight() >> LP()
    q.reflect() >> QWP()
    assert len(p.layout().placements) == 6


def test_crossing_beams_do_not_connect():
    drawing = Setup()
    drawing.beam(origin=(-200, 0)) >> HWP() >> LP()
    drawing.beam("south", origin=(-100, -150)) >> HWP() >> LP()
    result = drawing.layout(style=Style(pitch=300))
    assert len(drawing.connections) == 2
    assert len([s for s in result.segments
                if s.source is not None and s.target is not None]) == 2


def test_style_scales_spacing_and_clearance():
    result = (iris() >> HWP()).layout(style=Style(pitch=250))
    assert result.segments[0].length == pytest.approx(250)
    with pytest.raises(LayoutError, match="positive"):
        Style(pitch=-1)
