"""Labels stay nearby and unambiguously belong to their physical components."""
import importlib
import math
import runpy

import pytest

from beampath import (
    Artwork, ComponentDefinition, ComponentSpec, Geometry, HWP, LayoutError,
    Port, Setup, Style, beam, fiber_coupler, fiber_laser, fiber_launch,
    fiber_power_meter, inline_power_meter, rows,
)
from beampath.examples._discovery import example_names
from beampath.geometry import add, overlap, rotate
from beampath.layout import segment_intersects
from beampath.labels import space_labels


def distance(a, b):
    return math.hypot(max(0, a[0] - b[2], b[0] - a[2]),
                      max(0, a[1] - b[3], b[1] - a[3]))


def assert_labels_clear(layout):
    for index, label in enumerate(layout.labels):
        owner = layout.placements[label.optic]
        gap = distance(label.bounds, owner.bounds)
        assert gap >= layout.style.label_gap - 1e-7
        assert gap <= math.sqrt(2) * layout.style.label_gap + 1e-7
        for other in layout.placements.values():
            assert not overlap(label.bounds, other.bounds)
            if other.id != owner.id:
                assert distance(label.bounds, other.bounds) >= gap + 3 - 1e-7
        assert all(not overlap(label.bounds, other.bounds, 3) for other in layout.labels[index + 1:])
        lines = list(layout.segments) + [leg for route in layout.fibers for leg in route.legs]
        assert all(not segment_intersects(line.start, line.end, label.bounds) for line in lines)


@pytest.mark.parametrize("name", example_names())
def test_examples_have_adjacent_unambiguous_labels_without_changing_graph(name):
    namespace = runpy.run_module("beampath.examples." + name)
    setup = namespace["setup"]
    graph = setup.setup if hasattr(setup, "setup") else setup
    before = graph.optics, graph.connections
    layout = setup.layout(style=namespace.get("style"))
    assert_labels_clear(layout)
    assert (graph.optics, graph.connections) == before
    repeated = setup.layout(style=namespace.get("style"))
    # Kiwi's tableau may differ below SVG precision, especially in closed loops.
    for ident, placed in layout.placements.items():
        assert repeated.placements[ident].position == pytest.approx(placed.position, abs=1e-7, rel=0)
    for first, second in zip(layout.labels, repeated.labels, strict=True):
        assert (first.optic, first.text) == (second.optic, second.text)
        assert second.position == pytest.approx(first.position, abs=1e-7, rel=0)


@pytest.mark.parametrize("name,text,kind", [
    ("ghz_path_identity", "Pump HWP\n45°", "HWP"),
    ("spdc", "Transmitted pump", "beam_block"),
])
def test_reported_labels_stay_at_the_normal_gap(name, text, kind):
    setup = runpy.run_module("beampath.examples." + name)["setup"]
    layout = setup.layout()
    labels = [label for label in layout.labels if label.text == text]
    assert len(labels) == (2 if name == "ghz_path_identity" else 1)
    for label in labels:
        owner = layout.placements[label.optic]
        assert owner.instance.spec.definition.name == kind
        assert distance(label.bounds, owner.bounds) == pytest.approx(layout.style.label_gap)
    assert_labels_clear(layout)


@pytest.mark.parametrize("clearance", [20, 35])
def test_label_spacing_rechecks_artwork_clearance(clearance):
    setup = runpy.run_module("beampath.examples.swapping")["setup"].setup
    initial = setup.layout(style=Style(clearance=1))
    optics = list(initial.placements.values())
    # Exercise label spacing independently of the initial component solver.
    assert any(overlap(a.bounds, b.bounds, clearance)
               for index, a in enumerate(optics) for b in optics[index + 1:])
    style = Style(clearance=clearance)
    placements, labels = space_labels(setup, initial.placements, style)
    optics = list(placements.values())
    for index, a in enumerate(optics):
        for b in optics[index + 1:]:
            assert not overlap(a.bounds, b.bounds, clearance), (a.id, b.id)
    assert len(labels) == len(initial.labels)


def box(label="", bounds=(-5, -5, 5, 5), anchor=None):
    return ComponentSpec(ComponentDefinition(
        "label-fixture", "", Artwork((0, 0), bounds, svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda p: Geometry((Port("in", "input", draw_lead_in=False),)), label_anchor=anchor), label)


def test_an_obstructed_preferred_side_uses_another_side_without_moving_components():
    setup = Setup()
    setup.beam() >> box("Target")
    setup.beam(origin=(0, 45)) >> box()
    setup.beam(origin=(0, -300)) >> box()
    layout = setup.layout()
    label, = layout.labels
    assert label.bounds[3] == pytest.approx(-5 - layout.style.label_gap)
    assert [p.position for p in layout.placements.values()] == [(0, 0), (0, 45), (0, -300)]
    assert_labels_clear(layout)


def test_competing_labels_fit_jointly_with_all_positions_fixed():
    setup = Setup()
    setup.beam() >> box("Wide first label")
    setup.beam(origin=(130, 0)) >> box("Wide second label")
    layout = setup.layout()
    a, b = layout.labels
    assert a.bounds[1] * b.bounds[1] < 0  # Opposite sides resolve the shared space.
    assert [p.position for p in layout.placements.values()] == [(0, 0), (130, 0)]
    assert_labels_clear(layout)


@pytest.mark.parametrize("direction", [0, 90, 37])
@pytest.mark.parametrize("font_size", [23, 32])
def test_only_automatic_gaps_expand_and_fixed_distance_and_pin_survive(direction, font_size):
    setup = beam(direction, origin=(120, -80)) >> HWP("Input")
    setup.append(HWP("Pump\npolarization"), distance=300)
    fixed = setup.end.id
    setup >> HWP("Pump\npolarization")
    style = Style(pitch=40, font_size=font_size)
    layout = setup.layout(style=style)
    segment = next(s for s in layout.segments if s.target == fixed)
    assert segment.length == pytest.approx(300)
    assert layout.placements[fixed].position == pytest.approx(add((120, -80), rotate((300, 0), direction)))
    automatic = next(s for s in layout.segments if s.source == fixed and s.target)
    assert automatic.length > style.pitch
    assert_labels_clear(layout)


def crowded_fixed_setup():
    setup = Setup()
    setup.beam() >> box("Label that needs room")
    for position, bounds in [((0, 50), (-65, -5, 65, 5)),
                             ((0, -50), (-65, -5, 65, 5)),
                             ((90, 0), (-5, -40, 5, 40)),
                             ((-90, 0), (-5, -40, 5, 40))]:
        setup.beam(origin=position) >> box(bounds=bounds)
    return setup


def test_impossible_fixed_geometry_reports_the_label_instead_of_displacing_it():
    setup = crowded_fixed_setup()
    before = setup.optics, setup.connections
    with pytest.raises(LayoutError, match=r"optic-001.*Label that needs room.*no feasible adjacent labeling"):
        setup.layout()
    assert (setup.optics, setup.connections) == before


def test_label_spacing_budget_is_distinct_from_infeasibility(monkeypatch):
    layout_module = importlib.import_module("beampath.layout")
    monkeypatch.setattr(layout_module, "_BEAM_SEARCH_LIMIT", 1)
    with pytest.raises(LayoutError, match=r"optic-001.*label.*search budget exhausted"):
        crowded_fixed_setup().layout()


def test_joint_label_search_budget_does_not_silently_trigger_expansion(monkeypatch):
    from beampath import labels

    monkeypatch.setattr(labels, "_SEARCH_LIMIT", 0)
    with pytest.raises(LayoutError, match=r"optic-001.*Target.*label search budget exhausted"):
        (beam() >> box("Target")).layout()


@pytest.mark.parametrize("direction", [0, 90, 37])
def test_multiline_custom_anchor_is_transformed_with_the_artwork(direction):
    setup = beam(direction, origin=(120, -80)) >> box("Custom\nlabel", (-30, -10, 30, 10), (20, 0))
    layout = setup.layout()
    label, = layout.labels
    placed, = layout.placements.values()
    anchor = add(placed.position, rotate((20, 0), direction))
    cx = (label.bounds[0] + label.bounds[2]) / 2
    cy = (label.bounds[1] + label.bounds[3]) / 2
    if 45 < direction % 180 < 135:
        assert cy == pytest.approx(anchor[1])
    else:
        assert cx == pytest.approx(anchor[0])
    assert label.bounds[3] - label.bounds[1] == pytest.approx(2 * layout.style.font_size * 1.25)
    assert_labels_clear(layout)


def test_hidden_labels_do_not_force_expansion():
    setup = beam() >> HWP("") >> HWP("")
    layout = setup.layout(style=Style(pitch=40))
    assert not layout.labels
    assert next(s for s in layout.segments if s.source and s.target).length == pytest.approx(40)


@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize("label_gap", [1, 14])
def test_nested_mixed_stages_keep_solved_labels_attached(depth, label_gap):
    setup = fiber_launch("Input") >> HWP("Pump\npolarization") >> fiber_coupler("Output")
    style = Style(pitch=40, label_gap=label_gap)
    before = setup.layout(style=style)
    for _ in range(depth):
        setup = rows(setup)
    layout = setup.layout(style=style)
    assert_labels_clear(layout)
    for local, grouped in zip(before.labels, layout.labels):
        a = before.placements[local.optic].position
        b = layout.placements[grouped.optic].position
        assert tuple(grouped.position[i] - b[i] for i in (0, 1)) == pytest.approx(
            tuple(local.position[i] - a[i] for i in (0, 1)))
    assert setup.layout(style=style) == layout


@pytest.mark.parametrize("grouped", [False, True])
def test_expanding_crowded_fiber_components_keeps_connector_exits_routable(grouped):
    setup = beam() >> fiber_laser("Source")
    for _ in range(3):
        setup >> inline_power_meter("Transmission monitoring label")
    setup >> fiber_power_meter("Output")
    if grouped:
        setup = rows(setup)
    style = Style(pitch=5)
    graph = setup.setup.optics, setup.setup.connections
    layout = setup.layout(style=style)
    assert_labels_clear(layout)
    assert any(len(route.points) > 2 for route in layout.fibers)
    for edge in setup.setup.connections:
        source, target = layout.placements[edge.source], layout.placements[edge.target]
        assert target.bounds[0] >= source.bounds[2] + style.clearance - 1e-7
    for route in layout.fibers:
        for leg in route.legs:
            for placed in layout.placements.values():
                if placed.id not in {route.source, route.target}:
                    assert not segment_intersects(leg.start, leg.end, placed.bounds)
    assert (setup.setup.optics, setup.setup.connections) == graph
