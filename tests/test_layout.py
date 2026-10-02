from dataclasses import FrozenInstanceError
import math
from uuid import uuid4

import pytest

from beampath import (
    Artwork, ComponentDefinition, Geometry, HWP, LP, LayoutError, Port, QWP,
    Setup, Style, beam, beamsplitter, component, iris, mirror, register_component,
)
from beampath.examples import cage_system, mzi


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


def test_unequal_mzi_closes_shared_optic_by_stretching():
    p = mzi()
    result = p.layout()
    combined = next(o for o in result.placements.values() if o.instance.spec.label == "BS2")
    incident = [s for s in result.segments if s.target == combined.id]
    assert sorted(s.length for s in incident) == pytest.approx([380, 570])
    assert all(s.end == pytest.approx(combined.position) for s in incident)
    assert combined.position == pytest.approx((570, 570))
    assert len([o for o in result.placements.values() if o.instance.spec.label == "BS2"]) == 1
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
    assert len([s for s in result.segments if s.target]) == 2


def test_style_scales_spacing_and_clearance():
    result = (iris() >> HWP()).layout(style=Style(pitch=250))
    assert result.segments[0].length == pytest.approx(250)
    with pytest.raises(LayoutError, match="positive"):
        Style(pitch=-1)
