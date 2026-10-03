from dataclasses import replace
import math

import pytest

from beampath import Label, Style, beam, fiber_coupler, fiber_launch
from beampath.geometry import add, rotate
from beampath.layout import segment_intersects
from beampath.routing import center_route, connector_lead, inflate, route_connection


def return_path(gap=400, rotation=0, offset=(0, 0)):
    path = beam(rotation).append(fiber_coupler(""),
                                 at=add(rotate((600, 0), rotation), offset))
    path.append(fiber_launch("", heading=rotation),
                at=add(rotate((0, gap), rotation), offset))
    return path


def assert_refinement(original, centered, layout, labels=()):
    assert centered.start == original.start
    assert centered.end == original.end
    assert centered.length == pytest.approx(original.length)
    assert len(centered.points) == len(original.points)
    for old, new in zip(original.legs, centered.legs):
        assert new.length > 0
        old_direction = tuple((old.end[i] - old.start[i]) / old.length for i in (0, 1))
        new_direction = tuple((new.end[i] - new.start[i]) / new.length for i in (0, 1))
        assert new_direction == pytest.approx(old_direction)
    for index, leg in enumerate(centered.legs):
        for placed in layout.placements.values():
            if (index == 0 and placed.id == centered.source
                    or index == len(centered.legs) - 1 and placed.id == centered.target):
                continue
            assert not segment_intersects(leg.start, leg.end,
                                          inflate(placed.bounds, layout.style.clearance))
        for label in labels:
            assert not segment_intersects(leg.start, leg.end, label.bounds)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("gap", [160, 400, 800])
def test_return_centers_between_sections_at_any_cardinal_orientation(rotation, gap):
    offset = (135, -271)
    path = return_path(gap, rotation, offset)
    graph = path.setup.optics, path.setup.connections
    layout = path.layout()
    route, = layout.fibers
    raw = route_connection(path.setup.connections[0], layout.placements, layout.style)
    middle = route.points[2:4]
    for point in middle:
        local = rotate((point[0] - offset[0], point[1] - offset[1]), -rotation)
        assert local[1] == pytest.approx(gap / 2)
    assert_refinement(raw, route, layout)
    assert path.layout() == layout
    assert (path.setup.optics, path.setup.connections) == graph


@pytest.mark.parametrize("label_x,expected_y", [(50, 219.6), (650, 219.6), (1000, 200)])
def test_centering_uses_labels_anywhere_along_the_run(label_x, expected_y):
    path = return_path()
    layout = path.layout()
    route, = layout.fibers
    # Start against the lower wall, with a label protruding from the upper wall.
    points = list(route.points)
    points[2] = (points[2][0], 339.2)
    points[3] = (points[3][0], 339.2)
    raw = replace(route, points=points)
    label = Label("note", "Note", (label_x, 70), (label_x, 50, label_x + 30, 80))
    centered = center_route(raw, layout.placements, layout.style, [label])
    assert centered.points[2][1] == pytest.approx(expected_y)
    assert centered.points[3][1] == pytest.approx(expected_y)
    assert_refinement(raw, centered, layout, [label])


def test_label_placement_precedes_centering(monkeypatch):
    from beampath import fiber_layout

    label = Label("note", "Note", (300, 20), (280, 10, 320, 40))
    monkeypatch.setattr(fiber_layout, "_labels", lambda *args: (label,))
    path = return_path()
    initial = path.layout()
    raw = route_connection(path.setup.connections[0], initial.placements, initial.style)
    # Put the label on the opposite side of the raw route, keeping it valid.
    if raw.points[2][1] < 200:
        label = replace(label, bounds=(280, 310, 320, 350))
        expected_y = (60.8 + 290) / 2
    else:
        label = replace(label, bounds=(280, 50, 320, 90))
        expected_y = (110 + 339.2) / 2
    result = path.layout()
    route, = result.fibers
    assert route.points[2][1] == pytest.approx(expected_y)
    assert_refinement(raw, route, result, [label])


def test_an_intermediate_component_splits_the_corridor():
    path = return_path()
    path.setup.beam(origin=(300, 180)) >> fiber_coupler("")
    layout = path.layout()
    route, = [r for r in layout.fibers if r.source and r.target]
    raw = route_connection(path.setup.connections[0], layout.placements, layout.style)
    # Center in the clear channel on the chosen side of the middle component;
    # centering between the two endpoints alone would run through its artwork.
    expected_y = 90 if raw.points[2][1] < 180 else 290
    assert route.points[2][1] == pytest.approx(expected_y)
    assert_refinement(raw, route, layout)


def test_existing_tight_label_clearance_does_not_force_an_unsafe_move():
    path = return_path()
    layout = path.layout()
    route, = layout.fibers
    label = Label("note", "Note", (300, 215), (280, 210, 320, 230))
    # The original centerline is clear, but already inside the label's preferred
    # padding. Leave it alone rather than guessing which side to escape toward.
    centered = center_route(route, layout.placements, layout.style, [label])
    assert centered == route
    assert_refinement(route, centered, layout, [label])


@pytest.mark.parametrize("clearance", [10, 35])
def test_two_bend_dogleg_centers_without_shortening_connector_escapes(clearance):
    path = beam().append(fiber_coupler(""))
    path.append(fiber_launch(""), at=(800, 400))
    layout = path.layout(style=Style(clearance=clearance))
    route, = layout.fibers
    raw = route_connection(path.setup.connections[0], layout.placements, layout.style)
    assert len(route.points) == 4
    assert route.points[1][0] == route.points[2][0] == pytest.approx(400)
    for ident, port, leg in ((route.source, route.output, route.legs[0]),
                             (route.target, route.input, route.legs[-1])):
        start, escape = connector_lead(layout.placements[ident], port, clearance)
        assert leg.length >= math.dist(start, escape)
    assert_refinement(raw, route, layout)


@pytest.mark.parametrize("destination,heading", [((800, 0), 0), ((800, 400), 90), ((-500, 0), 0)])
def test_straight_elbow_and_exterior_detour_keep_their_routes(destination, heading):
    path = beam().append(fiber_coupler(""))
    path.append(fiber_launch("", heading=heading), at=destination)
    layout = path.layout()
    route, = layout.fibers
    raw = route_connection(path.setup.connections[0], layout.placements, layout.style)
    assert route == raw


def test_tight_corridor_remains_clear():
    path = return_path(gap=121.6)
    layout = path.layout()
    route, = layout.fibers
    raw = route_connection(path.setup.connections[0], layout.placements, layout.style)
    assert route == raw
    assert_refinement(raw, route, layout)


def test_oblique_connector_leads_keep_their_positions_and_directions():
    path = return_path(rotation=31.7)
    layout = path.layout()
    route, = layout.fibers
    raw = route_connection(path.setup.connections[0], layout.placements, layout.style)
    assert route.points[:2] == raw.points[:2]
    assert route.points[-2:] == raw.points[-2:]
    assert_refinement(raw, route, layout)
