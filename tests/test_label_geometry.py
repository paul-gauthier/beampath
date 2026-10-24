"""Readable label spacing uses the same geometry in detection and solving."""
from dataclasses import replace
from types import SimpleNamespace

import kiwisolver as kiwi
import pytest

from beampath import HWP, LayoutError, Style, beam
from beampath.geometry import overlap
from beampath.label_geometry import bounds_distance, clearance, origin, project_origin
from beampath.occupied import _Box, _Conflict, _Scene, occupied_geometry


@pytest.mark.parametrize("bounds,expected", [
    ((2, 2, 5, 5), 0),
    ((17, 2, 20, 5), 7),
    ((13, 14, 20, 20), 4),
])
def test_rectangle_distance_matches_padded_collision(bounds, expected):
    reference = (0, 0, 10, 10)
    assert bounds_distance(reference, bounds) == expected
    assert bounds_distance(bounds, reference) == expected
    if expected:
        assert not overlap(reference, bounds, expected)
        assert overlap(reference, bounds, expected + .01)


@pytest.mark.parametrize("font_size,expected", [(2, 3), (23, 23), (40, 40)])
def test_clearance_is_one_em_with_a_small_absolute_floor(font_size, expected):
    assert clearance(Style(font_size=font_size)) == expected


def test_affine_box_uses_both_component_origins():
    placements = {"a": SimpleNamespace(position=(0, 0)),
                  "b": SimpleNamespace(position=(20, 40))}
    anchor = (("a", .25), ("b", .75))
    assert origin(anchor, placements) == (15, 30)
    box = _Box(anchor, (-2, -3, 2, 3), "route", "label")
    assert box.anchors == ("a", "b")
    assert box.placed(placements) == (13, 27, 17, 33)
    assert project_origin(anchor, (2, -1), (1, 2),
                          {"a": 0, "b": 20}, {"a": 0, "b": 40}) == 75


def test_affine_separating_constraint_can_expand_an_automatic_endpoint():
    xs = {ident: kiwi.Variable(ident + ".x") for ident in ("a", "b")}
    ys = {ident: kiwi.Variable(ident + ".y") for ident in ("a", "b")}
    artwork = _Box("a", (-5, -5, 5, 5), "a", "artwork")
    caption = _Box((("a", .5), ("b", .5)), (-8, -2, 8, 2), "route", "label")
    solver = kiwi.Solver()
    for constraint in (xs["a"] == 0, ys["a"] == 0, ys["b"] == 0,
                       xs["b"] >= 20, (xs["b"] == 20) | kiwi.strength.weak):
        solver.addConstraint(constraint)
    solver.addConstraint(_Conflict(artwork, caption, 10, "caption").alternatives(xs, ys)[0])
    solver.updateVariables()
    assert xs["b"].value() == pytest.approx(46)
    placements = {ident: SimpleNamespace(position=(xs[ident].value(), ys[ident].value()))
                  for ident in xs}
    assert bounds_distance(artwork.placed(placements), caption.placed(placements)) == 10


def test_component_ownership_reserves_its_attachment_gap_plus_one_em():
    own = _Box("a", (-5, -5, 5, 5), "a", "artwork")
    foreign = _Box("b", (-5, -5, 5, 5), "b", "artwork")
    caption = _Box("a", (15, -2, 25, 2), "a", "label")
    placements = {"a": SimpleNamespace(position=(0, 0), bounds=(-5, -5, 5, 5)),
                  "b": SimpleNamespace(position=(0, 30), bounds=(-5, 25, 5, 35))}
    scene = _Scene((own, foreign, caption), (), 23)
    conflict = scene.conflict(placements, Style(clearance=5))
    assert conflict.separation == 33
    assert "ambiguous near component b" in conflict.context
    assert scene.bounds(placements, within={"a"}) == (-18, -35, 58, 35)


def test_affine_bounds_belong_only_to_a_scope_containing_all_anchors():
    placements = {"a": SimpleNamespace(position=(0, 0)),
                  "b": SimpleNamespace(position=(100, 0))}
    local = _Box("a", (-5, -5, 5, 5), "a", "artwork")
    caption = _Box((("a", .5), ("b", .5)), (-5, -5, 5, 5), "route", "label")
    scene = _Scene((local, caption), (), 10)
    assert scene.bounds(placements, within={"a"}) == (-5, -5, 5, 5)
    assert scene.bounds(placements, within={"a", "b"}) == (-5, -15, 65, 15)


def test_label_avoids_visible_beam_stroke_when_its_centerline_is_clear():
    path = beam() >> HWP("") >> HWP("")
    layout = path.layout(style=Style(beam_width=40))
    ident = next(iter(layout.placements))
    caption = _Box(ident, (60, -15, 90, -5), "annotation", "label")
    scene = occupied_geometry(path.setup, layout.placements, layout.style)
    conflict = replace(scene, boxes=(*scene.boxes, caption)).conflict(layout.placements, layout.style)
    assert conflict is not None
    assert "beam crosses stage label annotation" in conflict.context


def test_fiber_refinement_propagates_shared_budget_exhaustion(monkeypatch):
    from beampath import routing
    from beampath.labels import _Budget
    from beampath.layout import FiberRoute

    def unexpected(*args, **kwargs):
        pytest.fail("route replacement ran after the shared budget was exhausted")

    monkeypatch.setattr(routing, "route_connection", unexpected)
    routes = (FiberRoute("a", ((0, 0), (100, 0)), "source-a", "out"),
              FiberRoute("b", ((50, -50), (50, 50)), "source-b", "out"))
    with pytest.raises(LayoutError, match="a: fiber route refinement.*search budget exhausted"):
        routing.refine_routes((SimpleNamespace(id="a"),), {}, Style(), (), routes,
                              fixed=("b",), budget=_Budget(0))
