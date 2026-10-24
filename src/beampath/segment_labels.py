"""Place upright labels beside semantic beam segments and fiber routes."""
from __future__ import annotations

import math

from .errors import LayoutError
from .geometry import EPSILON, overlap
from .label_geometry import clearance
from .layout import Label, _text_size, segment_intersects
from .routing import inflate


def _texts(setup, placements, routes, *, medium=None):
    """Resolve graph-owned labels without depending on layout-only fiber bends."""
    by_id = {route.id: route for route in routes}
    by_output = {(route.source, route.output): route for route in routes if route.source is not None}
    by_input = {(route.target, route.input): route for route in routes if route.source is None}
    result = {}

    def add(route, text, context):
        if not text:
            return
        if route is None:
            raise LayoutError(f"{context} ({text}): label has no visible segment")
        result[route.id] = text

    for edge in setup.connections:
        if (edge.source in placements and edge.target in placements
                and (medium is None or edge.medium == medium)):
            add(by_id.get(edge.id), edge.label, edge.id)
    for (ident, port), text in setup._output_labels.items():
        if (ident in placements
                and (medium is None or placements[ident].instance.port(port).medium == medium)):
            add(by_output.get((ident, port)), text, f"{ident}.{port}")
    for root in setup._roots:
        if (root.optic in placements
                and (medium is None or (root.input is not None
                     and placements[root.optic].instance.port(root.input).medium == medium))):
            add(by_input.get((root.optic, root.input)), root.label, f"{root.optic}.{root.input}")
    return result


def _candidates(route, text, style):
    """Prefer a route's longest straight leg and its center, on either side."""
    width, height = _text_size(text, style.font_size)
    points = getattr(route, "points", (route.start, route.end))
    legs, traversed = [], 0.0
    total = route.length
    for index, (a, b) in enumerate(zip(points, points[1:])):
        length = math.dist(a, b)
        if length > EPSILON:
            legs.append((length, abs(traversed + length / 2 - total / 2), index, a, b))
        traversed += length
    seen = set()
    for length, _, _, a, b in sorted(legs, key=lambda leg: (-leg[0], leg[1], leg[2])):
        dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        nx, ny = dy, -dx
        offset = style.label_gap + (abs(nx) * width + abs(ny) * height) / 2
        for fraction in (.5, 1 / 3, 2 / 3, .2, .8, .1, .9):
            for side in (1, -1):
                cx = a[0] + fraction * (b[0] - a[0]) + side * offset * nx
                cy = a[1] + fraction * (b[1] - a[1]) + side * offset * ny
                key = round(cx, 7), round(cy, 7)
                if key in seen:
                    continue
                seen.add(key)
                bounds = cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2
                baseline = cy + style.font_size * .35 - (height - style.font_size * 1.25) / 2
                yield Label(None, text, (cx, baseline), bounds, route.id)


def domains(setup, placements, segments, fibers, fixed, style, *,
            defer_peers=False, movable=()):
    """Generate clear annotation choices from the current route geometry.

    Movable peer fibers may be deferred while a caller tries routing them around
    a caption. Its own route, free-space beams, and measured child fibers always
    obstruct that caption. The caller must reroute and validate deferred peers
    before accepting the assignment.
    """
    routes = (*segments, *fibers)
    texts = _texts(setup, placements, routes)
    existing = {label.segment for label in fixed if label.segment is not None}
    movable = set(movable) - existing
    fiber_ids = {route.id for route in fibers}
    lines = [(segment, style.beam_width / 2, None) for segment in segments]
    lines += [(leg, style.fiber_width / 2, route.id) for route in fibers for leg in route.legs]
    padding = clearance(style)
    result = {}
    for route in routes:
        if route.id not in texts or route.id in existing:
            continue
        obstacles = [(line, width) for line, width, owner in lines
                     if not (defer_peers and route.id in fiber_ids and owner in movable
                             and owner != route.id)]
        result[route.id] = tuple(
            label for label in _candidates(route, texts[route.id], style)
            if not any(overlap(label.bounds, p.bounds, padding) for p in placements.values())
            and not any(overlap(label.bounds, other.bounds, padding) for other in fixed)
            and not any(segment_intersects(line.start, line.end, inflate(label.bounds, padding))
                        for line, padding in obstacles)
        )
    return result


def place_segment_labels(setup, placements, segments, fibers, fixed, style, *, budget=None):
    """Place route captions with the same search and clearance as optic labels."""
    from .labels import LabelPlacementError, search_domains

    texts = _texts(setup, placements, (*segments, *fibers))
    choices = domains(setup, placements, segments, fibers, fixed, style)
    try:
        return search_domains(choices, style, fixed, budget=budget, texts=texts)
    except LabelPlacementError as exc:
        raise LayoutError(f"{exc.optic} ({texts[exc.optic]}): no clear adjacent position "
                          "for its segment label") from exc
