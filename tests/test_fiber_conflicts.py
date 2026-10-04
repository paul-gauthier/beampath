"""Crossing preferences survive search, group composition and rendering."""
from dataclasses import replace

import pytest

from beampath import FiberRoute, beam, fiber_coupler, fiber_laser, fiber_launch, inline_power_meter
from beampath import group_layout, routing
from beampath.errors import LayoutError
from beampath.fiber_conflicts import conflict_score, route_contacts, route_set_score
from beampath.geometry import add, rotate
from beampath.layout import segment_intersects


def cable(ident, points, source=None, target=None):
    return FiberRoute(ident, points, source, "out" if source else None, target, "in" if target else None)


@pytest.mark.parametrize("rotation", [0, 90, 31.7])
@pytest.mark.parametrize("points,peer,expected", [
    (((0, 0), (10, 0)), ((5, -5), (5, 5)), ((5, 5),)),
    (((0, 0), (5, 0), (10, 0)), ((5, -5), (5, 0), (5, 5)), ((5, 5),)),
    (((0, 0), (10, 0)), ((5, 3), (5, 0), (8, 3)), ((5, 5),)),
    (((0, 0), (2, 0), (6, 0), (10, 0)), ((8, 0), (5, 0), (3, 0)), ((3, 8),)),
    (((0, 0), (10, 0), (10, 10)), ((5, 0), (10, 0), (10, 5)), ((5, 15),)),
    (((0, 0), (10, 0)), ((2, -2), (2, 2), (8, 2), (8, -2)), ((2, 2), (8, 8))),
    (((0, 0), (10, 0)), ((0, 1), (10, 1)), ()),
])
def test_contacts_are_geometric_events_not_leg_pairs(rotation, points, peer, expected):
    transform = lambda pts: tuple(add(rotate(p, rotation), (127, -43)) for p in pts)
    a, b = cable("a", transform(points)), cable("b", transform(peer))
    contacts = route_contacts(a, b)
    assert len(contacts) == len(expected)
    for actual, wanted in zip(contacts, expected):
        assert actual == pytest.approx(wanted)
    assert conflict_score(a, (b,)) == conflict_score(b, (a,))


def test_only_real_shared_attachments_are_exempt():
    a = cable("a", ((0, 0), (10, 0)), "laser", "splice")
    b = cable("b", ((10, 0), (10, 10)), "splice", "meter")
    assert route_contacts(a, b) == ()
    assert route_contacts(a, replace(b, source="another optic")) == ((10, 10),)
    # Starting at the same attachment does not exempt an overlapping run.
    assert route_contacts(a, replace(b, points=((10, 0), (5, 0), (5, 10)))) == ((5, 10),)


def test_search_contact_cost_does_not_depend_on_grid_subdivision():
    peer = cable("barrier", ((5, -20), (5, 20)))
    # A wall of artwork above and below forces a crossing. Adding distant
    # obstacle coordinates subdivides the grid but cannot multiply that event.
    boxes = [(-20, -30, 30, -1), (-20, 1, 30, 30),
             (-20, -30, -19, 30), (29, -30, 30, 30)]
    for extra in ([], [(2, 40, 4, 42), (5, 40, 6, 42), (7, 40, 8, 42)]):
        points = routing.orthogonal_path((0, 0), (10, 0), boxes + extra, 0, 0, 2, (peer,), 1)
        result = cable("route", routing.simplify(points))
        assert route_contacts(result, peer) == ((5, 5),)
        assert result.length == pytest.approx(10)


def test_composition_removes_crossing_without_moving_optics_or_adding_bends(monkeypatch):
    from beampath.examples.composition import setup

    def old_refinement(edges, placements, style, labels, fibers, fixed=()):
        return [r if r.id in fixed else routing.center_route(r, placements, style, labels) for r in fibers]

    with monkeypatch.context() as patch:
        patch.setattr(group_layout, "refine_routes", old_refinement)
        original = setup.layout()
    result = setup.layout()
    assert route_set_score(original.fibers)[0] == 1
    assert route_set_score(result.fibers)[0] == 0
    assert result.placements == original.placements
    assert result.labels == original.labels
    assert result.segments == original.segments
    for before, after in zip(original.fibers, result.fibers):
        assert before.id == after.id
        assert before.length == pytest.approx(after.length)
        assert len(before.points) == len(after.points)
        assert (before.start, before.end) == (after.start, after.end)
        if before.id != "segment-006":
            assert before == after  # Measured child routes stay fixed.
    assert setup.layout() == result


def test_centering_cannot_slide_a_clear_run_across_a_fiber():
    path = beam().append(fiber_coupler(""), at=(600, 0))
    path.append(fiber_launch(""), at=(0, 400))
    layout = path.layout()
    route, = layout.fibers
    points = list(route.points)
    points[2] = (points[2][0], 80)
    points[3] = (points[3][0], 80)
    raw = replace(route, points=points)
    peer = cable("monitor", ((300, 150), (300, 450)))
    assert conflict_score(raw, (peer,)) == (0, 0)
    assert conflict_score(routing.center_route(raw, layout.placements, layout.style), (peer,))[0] == 1
    centered = routing.center_route(raw, layout.placements, layout.style, peers=(peer,))
    assert conflict_score(centered, (peer,)) == (0, 0)
    assert centered.length == pytest.approx(raw.length)
    assert len(centered.points) == len(raw.points)


@pytest.mark.parametrize("failed_search", [False, True])
def test_unavoidable_lead_contact_keeps_a_valid_route(monkeypatch, failed_search):
    path = fiber_laser("") >> inline_power_meter("")
    layout = path.layout()
    route = next(r for r in layout.fibers if r.target)
    start, escape = routing.connector_lead(layout.placements[route.source], route.output, layout.style.clearance)
    x = (start[0] + escape[0]) / 2
    peer = cable("fixed-stub", ((x, start[1] - 20), (x, start[1] + 20)))
    calls = []
    search = routing.route_connection

    def attempt(*args):
        calls.append(1)
        if failed_search:
            raise LayoutError("replacement has no clear escape")
        return search(*args)

    monkeypatch.setattr(routing, "route_connection", attempt)
    result = routing.refine_routes(path.setup.connections, layout.placements, layout.style, layout.labels,
                                   [route, peer], fixed=(peer.id,))
    assert result == [route, peer]
    assert route_set_score(result)[0] == 1
    assert len(calls) == 1  # Stop after the first sweep cannot improve anything.


@pytest.mark.parametrize("contact", ["crossing", "overlap", "touch"])
def test_straight_shortcut_considers_peers_and_can_take_a_longer_route(contact):
    path = fiber_laser("") >> inline_power_meter("")
    layout = path.layout()
    edge, = path.setup.connections
    straight = routing.route_connection(edge, layout.placements, layout.style)
    x = (straight.start[0] + straight.end[0]) / 2
    points = {"crossing": ((x, -200), (x, 200)),
              "overlap": ((x - 10, 0), (x + 10, 0)),
              "touch": ((x, 0), (x, 200))}[contact]
    peer = cable("fixed", points)
    replacement = routing.route_connection(edge, layout.placements, layout.style, layout.labels, (peer,))
    assert conflict_score(straight, (peer,))[0] == 1
    assert conflict_score(replacement, (peer,))[0] == 0
    assert replacement.length > straight.length
    assert len(replacement.points) > len(straight.points)
    for leg in replacement.legs:
        for label in layout.labels:
            assert not segment_intersects(leg.start, leg.end, label.bounds)


def test_rounding_cannot_introduce_contact_between_clear_polylines():
    route = cable("a", ((0, 0), (20, 0), (20, 20)))
    peer = cable("b", ((12, 3), (18, 3)))
    assert route_contacts(route, peer) == ()
    assert " Q " in routing.rounded_path(route, 10, (), 1)
    assert " Q " not in routing.rounded_path(route, 10, (), 1, (peer,))


def test_conflict_free_layout_does_not_search_again(monkeypatch):
    path = fiber_laser("") >> inline_power_meter("")
    layout = path.layout()
    def unexpected(*args):
        pytest.fail("a conflict-free route was searched again")
    monkeypatch.setattr(routing, "route_connection", unexpected)
    assert routing.refine_routes(path.setup.connections, layout.placements, layout.style,
                                 layout.labels, layout.fibers) == list(layout.fibers)
