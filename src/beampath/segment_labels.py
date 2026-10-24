"""Place upright labels beside semantic beam segments and fiber routes."""
from __future__ import annotations

import math

from .errors import LayoutError
from .geometry import EPSILON, overlap
from .layout import Label, _text_size, segment_intersects
from .routing import inflate


_SEARCH_LIMIT = 1000


def _texts(setup, placements, routes):
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
        if edge.source in placements and edge.target in placements:
            add(by_id.get(edge.id), edge.label, edge.id)
    for (ident, port), text in setup._output_labels.items():
        if ident in placements:
            add(by_output.get((ident, port)), text, f"{ident}.{port}")
    for root in setup._roots:
        if root.optic in placements:
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


def place_segment_labels(setup, placements, segments, fibers, fixed, style):
    """Find a deterministic, collision-free joint assignment beside the routes.

    Measured child-stage labels remain fixed. Every new label avoids artwork,
    all beam and cable legs, and the already placed component/stage labels.
    """
    routes = (*segments, *fibers)
    texts = _texts(setup, placements, routes)
    existing = {label.segment for label in fixed if label.segment is not None}
    lines = [(segment, style.beam_width / 2) for segment in segments]
    lines += [(leg, style.fiber_width / 2) for route in fibers for leg in route.legs]
    domains = {}
    for route in routes:
        if route.id not in texts or route.id in existing:
            continue
        domains[route.id] = tuple(
            label for label in _candidates(route, texts[route.id], style)
            if not any(overlap(label.bounds, p.bounds, 3) for p in placements.values())
            and not any(overlap(label.bounds, other.bounds, 3) for other in fixed)
            and not any(segment_intersects(line.start, line.end, inflate(label.bounds, padding))
                        for line, padding in lines)
        )
    if not domains:
        return tuple(fixed)
    attempts = 0
    failed = next(iter(domains))

    def search(remaining, chosen):
        nonlocal attempts, failed
        if not remaining:
            return chosen
        ident = min(remaining, key=lambda key: len(remaining[key]))
        failed = ident
        for label in remaining[ident]:
            if attempts >= _SEARCH_LIMIT:
                raise LayoutError(f"{ident} ({texts[ident]}): segment label search budget exhausted "
                                  f"({_SEARCH_LIMIT} candidate states)")
            attempts += 1
            reduced = {key: tuple(other for other in options if not overlap(label.bounds, other.bounds, 3))
                       for key, options in remaining.items() if key != ident}
            if any(not options for options in reduced.values()):
                continue
            result = search(reduced, {**chosen, ident: label})
            if result is not None:
                return result
        return None

    selected = search(domains, {})
    if selected is None:
        raise LayoutError(f"{failed} ({texts[failed]}): no clear adjacent position for its segment label")
    return tuple(fixed) + tuple(selected[ident] for ident in domains)
