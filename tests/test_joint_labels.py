"""Readability requires component labels and route captions to share a solve."""
from types import SimpleNamespace

import pytest

from beampath import (
    Artwork, ComponentDefinition, ComponentSpec, Geometry, HWP, LayoutError,
    Port, QWP, Setup, Style, beam, beamsplitter, detector, fiber_coupler,
    flip_mirror, label,
)
from beampath.geometry import overlap
from beampath.layout import FiberRoute, Label, Segment, segment_intersects
from beampath.segment_labels import _texts, domains


def _distance(a, b):
    return max(a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3], 0)


def _assert_readable(layout):
    padding = max(3, layout.style.font_size)
    lines = (*layout.segments, *(leg for route in layout.fibers for leg in route.legs))
    for index, caption in enumerate(layout.labels):
        owner = layout.placements.get(caption.optic)
        own_gap = _distance(caption.bounds, owner.bounds) if owner else None
        for placed in layout.placements.values():
            if placed is owner:
                continue
            assert not overlap(caption.bounds, placed.bounds, padding)
            if owner is not None:
                assert _distance(caption.bounds, placed.bounds) >= own_gap + padding - 1e-7
        assert all(not overlap(caption.bounds, other.bounds, padding)
                   for other in layout.labels[index + 1:])
        assert all(not segment_intersects(line.start, line.end, caption.bounds) for line in lines)


def _box(text="", bounds=(-5, -5, 5, 5)):
    return ComponentSpec(ComponentDefinition(
        "joint-label-fixture", "", Artwork(
            (0, 0), bounds, svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda _: Geometry((Port("in", "input", draw_lead_in=False),
                            Port("out", "output", draw_open=False)))), text)


def test_component_labels_yield_to_route_captions_without_moving_fixed_artwork():
    setup = Setup()
    path = setup.beam() >> _box() >> label("Enclosed")
    path.append(_box(), distance=250)
    source = setup.beam(origin=(125, -95)) >> _box("Wide descriptive component label")
    setup.beam(origin=(125, 70)) >> _box(bounds=(-200, -5, 200, 5))
    setup.beam(origin=(125, -300)) >> _box()
    before = setup.optics, setup.connections

    layout = setup.layout()

    component_label = next(caption for caption in layout.labels if caption.optic == source.end.id)
    assert component_label.bounds[3] < layout.placements[source.end.id].bounds[1]
    assert next(segment for segment in layout.segments if segment.target).length == pytest.approx(250)
    assert {placed.position for placed in layout.placements.values()} == {
        (0, 0), (250, 0), (125, -95), (125, 70), (125, -300),
    }
    assert (setup.optics, setup.connections) == before
    assert setup.layout() == layout
    _assert_readable(layout)


def test_beam_caption_follows_both_endpoints_when_obstacles_force_more_spacing():
    setup = Setup()
    path = setup.beam() >> _box() >> label("Route caption") >> _box()
    style = Style(pitch=40)
    ordinary_length = next(segment.length for segment in path.layout(style=style).segments)
    # Clear of the artwork, these fixed bars block every initial text candidate.
    for y in (-70, 70):
        setup.beam(origin=(250, y)) >> _box(bounds=(-250, -5, 250, 5))
    before = setup.optics, setup.connections

    layout = setup.layout(style=style)

    route, = layout.segments
    caption, = layout.labels
    assert route.length > ordinary_length
    assert caption.bounds[0] >= 500 + style.font_size - 1e-7
    center = (caption.bounds[0] + caption.bounds[2]) / 2
    fraction = (center - route.start[0]) / (route.end[0] - route.start[0])
    assert any(fraction == pytest.approx(value) for value in (.5, 1 / 3, 2 / 3, .2, .8, .1, .9))
    assert {p.position for p in layout.placements.values()} >= {(0, 0), (250, -70), (250, 70)}
    assert (setup.optics, setup.connections) == before
    assert setup.layout(style=style) == layout
    _assert_readable(layout)


@pytest.mark.parametrize("direction", [0, 90, 37])
@pytest.mark.parametrize("font_size", [12, 32])
def test_joint_spacing_scales_with_text_and_preserves_explicit_beam_distance(direction, font_size):
    path = beam(direction, origin=(120, -80)) >> HWP("Input")
    path.append(HWP("Fixed"), distance=300)
    fixed = path.end.id
    path >> label("Transmission wavelength: 1550 nm") >> HWP("Output")
    before = path.setup.optics, path.setup.connections
    style = Style(pitch=40, font_size=font_size)

    layout = path.layout(style=style)

    assert next(segment for segment in layout.segments if segment.target == fixed).length == pytest.approx(300)
    caption = next(caption for caption in layout.labels if caption.segment is not None)
    route = next(segment for segment in layout.segments if segment.id == caption.segment)
    assert route.length > style.pitch
    assert (path.setup.optics, path.setup.connections) == before
    _assert_readable(layout)


@pytest.mark.parametrize("font_size", [23, 32])
def test_dense_cube_and_beam_annotation_get_readable_automatic_spacing(font_size):
    path = (beam() >> HWP("HWP1", "DDR25") >> label("Enclosed")
            >> beamsplitter("90:10 BS", turn="right"))
    path.reflect() >> QWP("QWP", "DDR25")
    before = path.setup.optics, path.setup.connections
    style = Style(pitch=65, font_size=font_size)

    layout = path.layout(style=style)

    cube = next(placed for placed in layout.placements.values()
                if placed.instance.spec.definition.name == "beamsplitter")
    annotated = next(segment for segment in layout.segments if segment.target == cube.id)
    assert annotated.length > style.pitch
    assert len(layout.labels) == 4
    assert (path.setup.optics, path.setup.connections) == before
    _assert_readable(layout)


@pytest.mark.parametrize("font_size", [23, 32])
def test_waveplate_label_clears_a_nearby_detector_without_moving_pinned_components(font_size):
    setup = Setup()
    plate = setup.beam(90) >> QWP("QWP", "DDR25")
    setup.beam(270, origin=(190, 0)) >> detector("SNSPD")
    setup.beam(origin=(-1000, 0)) >> _box()

    layout = setup.layout(style=Style(font_size=font_size))

    assert {placed.position for placed in layout.placements.values()} == {(0, 0), (190, 0), (-1000, 0)}
    plate_label = next(caption for caption in layout.labels if caption.optic == plate.end.id)
    assert plate_label.bounds[2] < layout.placements[plate.end.id].bounds[0]
    _assert_readable(layout)


@pytest.mark.parametrize("font_size", [23, 32])
def test_asymmetric_flip_mirror_label_is_unambiguous_near_a_fiber_coupler(font_size):
    path = beam(90) >> flip_mirror("Flip mirror", turn="right")
    mirror_id = path.end.id
    path.reflect() >> fiber_coupler("MMF")
    path.setup.beam(origin=(210, 0)) >> _box(bounds=(-10, -30, 10, 30))

    layout = path.layout(style=Style(pitch=80, font_size=font_size))

    caption = next(caption for caption in layout.labels if caption.optic == mirror_id)
    assert caption.bounds[0] > layout.placements[mirror_id].bounds[2]
    assert next(segment for segment in layout.segments if segment.target).length == pytest.approx(80)
    _assert_readable(layout)


def _fiber_fixture():
    setup = SimpleNamespace(
        connections=[SimpleNamespace(id="main", source="a", target="b",
                                     medium="fiber", label="Caption")],
        _output_labels={}, _roots=[])
    placements = {"a": SimpleNamespace(bounds=(-1100, -5, -1000, 5)),
                  "b": SimpleNamespace(bounds=(1000, -5, 1100, 5))}
    own = FiberRoute("main", ((0, 0), (200, 0)), "a", "out", "b", "in")
    peer = FiberRoute("peer", ((-50, -25), (250, -25)), "a", "out", "b", "in")
    return setup, placements, own, peer


def test_fiber_caption_candidates_defer_only_explicitly_movable_peers():
    setup, placements, own, peer = _fiber_fixture()
    style = Style(font_size=20)
    strict = domains(setup, placements, (), (own, peer), (), style)[own.id]
    deferred = domains(setup, placements, (), (own, peer), (), style,
                       defer_peers=True, movable={own.id, peer.id})[own.id]
    assert len(deferred) > len(strict)
    assert any(segment_intersects(peer.start, peer.end, caption.bounds) for caption in deferred)
    assert all(not segment_intersects(own.start, own.end, caption.bounds) for caption in deferred)

    fixed = Label(None, "Measured peer caption", (0, -500), (-100, -510, 100, -490), peer.id)
    protected = domains(setup, placements, (), (own, peer), (fixed,), style,
                        defer_peers=True, movable={peer.id})[own.id]
    assert protected == strict

    beam_route = Segment("beam", peer.start, peer.end, "a", "out", "b", "in")
    beam_blocked = domains(setup, placements, (beam_route,), (own,), (), style,
                          defer_peers=True, movable={beam_route.id})[own.id]
    assert beam_blocked == strict


def test_beam_only_caption_discovery_does_not_require_pending_fiber_routes():
    setup, placements, _, _ = _fiber_fixture()
    setup.connections.append(SimpleNamespace(id="beam", source="a", target="b",
                                            medium="free_space", label="Enclosed"))
    route = Segment("beam", (0, 0), (200, 0), "a", "out", "b", "in")
    assert _texts(setup, placements, (route,), medium="free_space") == {"beam": "Enclosed"}


def _fiber_terminal(kind):
    output = kind == "output"
    port = Port("out" if output else "in", kind, position=(5 if output else -5, 0), medium="fiber")
    return ComponentSpec(ComponentDefinition(
        "joint-fiber-" + kind, "", Artwork(
            (0, 0), (-5, -5, 5, 5), svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda _: Geometry((port,)), default_input=None if output else "in"), "")


def _parallel_annotated_fibers():
    setup = Setup()
    main = setup.beam(origin=(-300, 0)) >> _fiber_terminal("output") >> label("Main caption")
    main.append(_fiber_terminal("input"), at=(300, 0))
    peer = setup.beam(origin=(-600, -25)) >> _fiber_terminal("output") >> label("Peer caption")
    peer.append(_fiber_terminal("input"), at=(600, -25))
    return setup


def test_fiber_peer_repair_regenerates_the_moved_routes_caption():
    setup = _parallel_annotated_fibers()
    before = setup.optics, setup.connections

    layout = setup.layout()

    peer = next(route for route in layout.fibers if route.id == setup.connections[1].id)
    assert len(peer.points) > 2
    for caption in layout.labels:
        own = next(route for route in layout.fibers if route.id == caption.segment)
        gaps = [_distance(caption.bounds, (min(leg.start[0], leg.end[0]), min(leg.start[1], leg.end[1]),
                                          max(leg.start[0], leg.end[0]), max(leg.start[1], leg.end[1])))
                for leg in own.legs]
        assert min(gaps) == pytest.approx(layout.style.label_gap)
    assert {placed.position for placed in layout.placements.values()} == {
        (-300, 0), (300, 0), (-600, -25), (600, -25),
    }
    assert (setup.optics, setup.connections) == before
    assert setup.layout() == layout
    _assert_readable(layout)


def test_fiber_caption_repair_budget_exhaustion_is_not_reported_as_infeasibility(monkeypatch):
    from beampath import labels

    setup = _parallel_annotated_fibers()
    before = setup.optics, setup.connections
    monkeypatch.setattr(labels, "_SEARCH_LIMIT", 4)
    with pytest.raises(LayoutError, match="search budget exhausted"):
        setup.layout()
    assert (setup.optics, setup.connections) == before
