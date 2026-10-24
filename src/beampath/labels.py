"""Adjacent label candidates and deterministic joint placement."""
from __future__ import annotations

from dataclasses import dataclass, replace
import heapq
import itertools

import kiwisolver as kiwi

from .errors import LayoutError
from .geometry import EPSILON, add, envelope, overlap, translated, unit
from .layout import Label, Segment, _project, _text_size, artwork_point, segment_intersects
from .label_geometry import Anchor, bounds_distance, clearance, origin


_SEARCH_LIMIT = 1000

class _Budget:
    """One allowance for discrete choices, spacing states and route repairs."""

    def __init__(self, limit=None):
        self.limit = _SEARCH_LIMIT if limit is None else min(limit, _SEARCH_LIMIT)
        self.used = 0

    def tick(self, context):
        if self.used >= self.limit:
            raise LayoutError(f"{context}: automatic label search budget exhausted "
                              f"({self.limit} candidate states)")
        self.used += 1


def move_label(label, delta):
    return replace(label, position=add(label.position, delta), bounds=translated(label.bounds, delta))


class LabelPlacementError(LayoutError):
    def __init__(self, optic, text):
        self.optic = optic
        super().__init__(f"{optic} ({text}): no clear adjacent position for its label")


def candidates(placements, style):
    """The eight local choices, in a stable order favoring the diagram exterior."""
    bounds = envelope([p.position for p in placements.values()])
    middle = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
    result = {}
    for placed in placements.values():
        text = placed.instance.spec.display_label
        if not text:
            continue
        width, height = _text_size(text, style.font_size)
        art_anchor = placed.instance.spec.definition.label_anchor
        anchor = (add(placed.position, artwork_point(placed.instance, art_anchor, placed.rotation))
                  if art_anchor is not None else placed.position)
        x0, y0, x1, y1 = placed.bounds
        left, right = x0 - style.label_gap - width / 2, x1 + style.label_gap + width / 2
        top, bottom = y0 - style.label_gap - height / 2, y1 + style.label_gap + height / 2
        positions = {
            "top": (anchor[0], top), "bottom": (anchor[0], bottom),
            "left": (left, anchor[1]), "right": (right, anchor[1]),
            "top_left": (left, top), "top_right": (right, top),
            "bottom_left": (left, bottom), "bottom_right": (right, bottom),
        }
        if 45 < placed.rotation % 180 < 135:
            preferred = "left" if placed.position[0] < middle[0] else "right"
        else:
            preferred = "top" if placed.position[1] < middle[1] else "bottom"
        order = [preferred] + [side for side in ("bottom", "top", "right", "left") if side != preferred]
        corners = ("bottom_right", "bottom_left", "top_right", "top_left")
        order += [side for side in corners if preferred in side] + [side for side in corners if preferred not in side]
        choices = []
        for side in order:
            cx, cy = positions[side]
            box = cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2
            baseline = cy + style.font_size * .35 - (height - style.font_size * 1.25) / 2
            choices.append(Label(placed.id, text, (cx, baseline), box))
        result[placed.id] = tuple(choices)
    return result


def associated(label, placements, style):
    if label.optic is None:
        return True  # A segment label is associated with its route, not an optic.
    own = bounds_distance(label.bounds, placements[label.optic].bounds)
    return all(bounds_distance(label.bounds, p.bounds) + EPSILON >= own + clearance(style)
               for p in placements.values() if p.id != label.optic)


def boundary_leads(drawing, placements, style):
    """Reserve true external beam attachments while measuring a child stage.

    These rays only obstruct local label candidates; they are not drawn stubs.
    Their reach covers every candidate of the attached component, including
    unusually long user labels.
    """
    options = candidates(placements, style)
    result = []
    for edge in drawing.connections:
        if edge.medium != "free_space" or (edge.source in placements) == (edge.target in placements):
            continue
        incoming = edge.target in placements
        ident, port = (edge.target, edge.input) if incoming else (edge.source, edge.output)
        placed = placements[ident]
        start = placed.port_position(port)
        direction = unit(placed.port_exit_direction(port))
        reach = max([style.open_length] + [_project(label.bounds, start, direction)[1] + style.clearance
                                          for label in options.get(ident, ())])
        end = add(start, tuple(reach * v for v in direction))
        result.append(Segment(f"boundary-{edge.id}", start, end, ident, port))
    return result


def search_domains(domains, style, fixed=(), *, budget=None, complete=None, texts=None):
    """Joint MRV search; terminal rejection resumes earlier candidate choices."""
    budget = budget or _Budget()
    texts = texts or {}
    padding = clearance(style)
    failed = next(iter(domains), None)
    terminal_error = None

    def search(remaining, chosen):
        nonlocal failed, terminal_error
        if not remaining:
            labels = tuple(fixed) + tuple(chosen[key] for key in domains)
            if complete is None:
                return labels
            try:
                return complete(labels)
            except LabelPlacementError as exc:
                terminal_error = exc
                return None
        ident = min(remaining, key=lambda key: len(remaining[key]))
        failed = ident
        for label in remaining[ident]:
            budget.tick(f"{ident} ({label.text})")
            reduced = {key: tuple(other for other in options
                                  if not overlap(label.bounds, other.bounds, padding))
                       for key, options in remaining.items() if key != ident}
            empty = next((key for key, options in reduced.items() if not options), None)
            if empty is not None:
                failed = empty
                continue
            result = search(reduced, {**chosen, ident: label})
            if result is not None:
                return result
        return None

    result = search(domains, {})
    if result is None:
        if terminal_error is not None:
            raise terminal_error
        text = texts.get(failed, next((a.text for a in domains.get(failed, ())), ""))
        raise LabelPlacementError(failed, text)
    return result


def place_labels(placements, segments, style, fixed=(), exclusions=(), *, choices=None,
                 budget=None, complete=None):
    """Compatibility entry point for component-only candidate placement."""
    choices = candidates(placements, style) if choices is None else choices
    fixed_ids = {label.optic for label in fixed}
    padding = clearance(style)
    domains = {ident: tuple(label for label in options
                           if associated(label, placements, style)
                           and not any(overlap(label.bounds, p.bounds, 0 if p.id == ident else padding)
                                       for p in placements.values())
                           and not any(overlap(label.bounds, b) for b in exclusions)
                           and not any(overlap(label.bounds, other.bounds, padding) for other in fixed)
                           and not any(segment_intersects(s.start, s.end, label.bounds) for s in segments))
               for ident, options in choices.items() if ident not in fixed_ids}
    return search_domains(domains, style, fixed, budget=budget, complete=complete,
                          texts={ident: placements[ident].instance.spec.display_label for ident in domains})


@dataclass(frozen=True)
class _Candidate:
    """A label expressed in an optic frame or a weighted pair of beam frames."""
    anchor: Anchor
    label: Label

    def placed(self, placements):
        return move_label(self.label, origin(self.anchor, placements))

    def box(self):
        from .occupied import _Box
        return _Box(self.anchor, self.label.bounds, self.label.optic or self.label.segment, "label")


def _prototypes(drawing, placements, style, blocks):
    from .layout import _beam_geometry
    from .segment_labels import _candidates, _texts

    fixed = {a.optic or a.segment for block in blocks.values() for a in block.labels}
    result = {ident: tuple(_Candidate(ident, move_label(a, tuple(-v for v in placements[ident].position)))
                           for a in options)
              for ident, options in candidates(placements, style).items() if ident not in fixed}
    beams = _beam_geometry(drawing, {ident: p.instance for ident, p in placements.items()}, style,
                           {ident: p.rotation for ident, p in placements.items()})
    texts = _texts(drawing, placements, [b.placed(placements) for b in beams], medium="free_space")
    for beam in beams:
        ident = beam.segment.id
        if ident not in texts or ident in fixed:
            continue
        route = beam.placed(placements)
        options = []
        for index, label in enumerate(_candidates(route, texts[ident], style)):
            fraction = (.5, 1 / 3, 2 / 3, .2, .8, .1, .9)[index // 2]
            anchor = (beam.start_owner if beam.start_owner == beam.end_owner else
                      ((beam.start_owner, 1 - fraction), (beam.end_owner, fraction)))
            options.append(_Candidate(anchor, move_label(label, tuple(-v for v in origin(anchor, placements)))))
        result[ident] = tuple(options)
    return result


def _fixed_content(blocks, placements):
    labels, routes = [], []
    for entry, block in blocks.items():
        delta = tuple(placements[entry].position[i] - block.placements[entry].position[i] for i in (0, 1))
        labels.extend(move_label(label, delta) for label in block.labels)
        routes.extend(replace(route, points=tuple(add(point, delta) for point in route.points))
                      for route in block.fibers)
    return tuple(labels), tuple(routes)


def _domains(scene, prototypes, placements, style):
    result = {}
    for ident, options in prototypes.items():
        result[ident] = tuple(candidate.placed(placements) for candidate in options
                             if replace(scene, boxes=(*scene.boxes, candidate.box())).conflict(placements, style) is None)
    return result


def space_labels(scope, placements, style, blocks=None, *, drawing=None, budget=None, complete=None):
    """Refine automatic spacing while preserving pins and measured child frames."""
    from .layout import _root_origins, _solve_beams

    blocks = blocks or {}
    grouped = {ident for block in blocks.values() for ident in block.placements}
    nodes = {ident: replace(p.instance, at=None) if ident in grouped and ident not in blocks else p.instance
             for ident, p in placements.items()}
    edges = [edge for edge in scope.connections if edge.medium == "free_space"
             and edge.source in nodes and edge.target in nodes]
    solved, labels = _solve_beams(nodes, edges, _root_origins(scope), style, blocks,
                                 drawing=scope if drawing is None else drawing, initial=placements,
                                 label_budget=budget, label_complete=complete)
    return {ident: replace(p, instance=placements[ident].instance) for ident, p in solved.items()}, labels


def solve_spacing(drawing, style, blocks, initial,
                  constraints, xs, ys, lengths, placements_now, limit, *, budget=None, complete=None):
    """Search affine label choices and separating axes, preferring compact solves."""
    from .occupied import occupied_geometry
    from .routing import inflate

    budget = budget or _Budget(limit)
    budget.limit = min(budget.limit, limit)
    initial_scene = occupied_geometry(drawing, initial, style, blocks, reserve_labels=True)
    prototypes = _prototypes(drawing, initial, style, blocks)
    # Intersections fixed in a single frame cannot be repaired by translating it.
    for ident, options in prototypes.items():
        prototypes[ident] = tuple(candidate for candidate in options
            if not any(line.active and set(line.anchors) == set(candidate.box().anchors)
                       and len(set(line.anchors)) == 1
                       and segment_intersects(line.geometry.placed(initial).start,
                                              line.geometry.placed(initial).end,
                                              inflate(candidate.placed(initial).bounds, line.padding))
                       for line in initial_scene.lines))
    pending, serial, seen = [], itertools.count(), set()
    first_error = None

    def enqueue(branch, selected, context):
        def key(constraint):
            expression = constraint.expression()
            sign = -1 if constraint.op() == "<=" else 1
            terms = tuple(sorted((term.variable().name(), round(sign * term.coefficient(), 12))
                                 for term in expression.terms()))
            return terms, round(sign * expression.constant(), 7)
        signature = tuple(sorted(selected.items())), frozenset(key(c) for c in branch)
        if signature in seen:
            return
        seen.add(signature)
        trial = kiwi.Solver()
        try:
            for constraint in (*constraints, *branch):
                trial.addConstraint(constraint)
        except kiwi.UnsatisfiableConstraint:
            return
        budget.tick(context)
        trial.updateVariables()
        length = round(sum(value.value() for value in lengths.values()), 7)
        displacement = round(sum(abs(xs[ident].value() - p.position[0])
                                 + abs(ys[ident].value() - p.position[1]) for ident, p in initial.items()), 7)
        heapq.heappush(pending, (length, displacement, next(serial), branch, selected, trial))

    enqueue((), {}, "labels")
    while pending:
        _, _, _, branch, selected, solver = heapq.heappop(pending)
        solver.updateVariables()
        placements = placements_now()
        scene = occupied_geometry(drawing, placements, style, blocks, reserve_labels=True)
        scene = replace(scene, boxes=(*scene.boxes, *(prototypes[key][index].box()
                                                     for key, index in selected.items())))
        collision = scene.conflict(placements, style)
        if collision is not None:
            first_error = first_error or collision.context
            for alternative in collision.alternatives(xs, ys):
                enqueue((*branch, alternative), selected, collision.context)
            continue
        fixed, _ = _fixed_content(blocks, placements)
        # Selected boxes already belong to the scene; avoid testing them twice.
        unselected = {key: options for key, options in prototypes.items() if key not in selected}
        domains = _domains(scene, unselected, placements, style)
        domains.update({key: (prototypes[key][index].placed(placements),) for key, index in selected.items()})
        texts = {key: options[0].label.text if options else
                 (initial[key].instance.spec.display_label if key in initial else key)
                 for key, options in prototypes.items()}
        try:
            labels = search_domains(domains, style, fixed, budget=budget, texts=texts,
                                    complete=(lambda labels: complete(placements, labels)) if complete else None)
        except LabelPlacementError as exc:
            first_error = first_error or str(exc)
            if exc.optic not in prototypes:
                raise  # Routed captions must be regenerated, never frozen into affine cuts.
            for index in range(len(prototypes[exc.optic])):
                if selected.get(exc.optic) != index:
                    enqueue(branch, {**selected, exc.optic: index}, str(exc))
        else:
            return placements, labels
    raise LayoutError(f"{first_error}: no feasible adjacent labeling with required constraints")


def _route_signature(routes):
    return tuple((route.id, tuple((round(x, 7), round(y, 7)) for x, y in route.points)) for route in routes)


def _fiber_labels(drawing, placements, segments, routes, fixed, fixed_ids, style, budget, validate=None):
    """Repair peer routes around captions, invalidating captions of changed routes."""
    from .segment_labels import domains, _texts
    from .routing import inflate, route_connection

    edges = {edge.id: edge for edge in drawing.connections if edge.medium == "fiber"
             and edge.source in placements and edge.target in placements and edge.id not in fixed_ids}
    seen = set()
    failure = None

    def solve(current, retained=()):
        nonlocal failure
        signature = (_route_signature(current), tuple(sorted((a.segment, a.bounds) for a in retained)))
        if signature in seen:
            return None
        seen.add(signature)
        base = (*fixed, *retained)
        options = domains(drawing, placements, segments, current, base, style,
                          defer_peers=True, movable=edges)
        texts = _texts(drawing, placements, (*segments, *current))

        def accept(labels):
            for i, route in enumerate(current):
                if route.id not in edges:
                    continue
                if not any(segment_intersects(leg.start, leg.end, inflate(label.bounds, style.fiber_width / 2))
                           for leg in route.legs for label in labels):
                    continue
                budget.tick(f"{route.id}: fiber annotation rerouting")
                obstacles = tuple(a for a in labels if a.segment != route.id)
                try:
                    changed = route_connection(edges[route.id], placements, style, obstacles,
                                               current[:i] + current[i + 1:])
                except LayoutError:
                    return None
                if changed == route:
                    return None
                kept = tuple(a for a in labels if a.segment in edges and a.segment != route.id)
                return solve((*current[:i], changed, *current[i + 1:]), kept)
            if validate is not None and not validate(labels, current):
                return None
            return tuple(labels), tuple(current)

        try:
            return search_domains(options, style, base, budget=budget, texts=texts, complete=accept)
        except LabelPlacementError as exc:
            failure = exc
            return None

    result = solve(tuple(routes))
    if result is None:
        if failure is not None:
            raise failure
        texts = _texts(drawing, placements, routes, medium="fiber")
        ident = next((key for key in texts if key not in {a.segment for a in fixed}), None)
        raise LabelPlacementError(ident or "fiber", texts.get(ident, "fiber routing"))
    return result


def finish_layout(drawing, placements, style, *, scope=None, blocks=None):
    """One terminally validated lifecycle for free-space, fiber and staged layouts."""
    from .fiber_layout import _open_fibers
    from .layout import _assemble_layout, _beam_segments
    from .occupied import _Box, occupied_geometry
    from .routing import inflate, refine_routes, route_connection

    blocks = blocks or {}
    budget = _Budget()
    accepted = {}
    rejected = {}

    def evaluate(current, labels):
        segments = _beam_segments(drawing, current, style)
        fixed_labels, fixed_routes = _fixed_content(blocks, current)
        frozen = {route.id: route for route in fixed_routes}
        edges = [edge for edge in drawing.connections if edge.medium == "fiber"
                 and edge.source in current and edge.target in current]
        opens = [frozen.get(route.id, route) for route in _open_fibers(drawing, current, style)]
        routes = []
        for edge in edges:
            if edge.id in frozen:
                routes.append(frozen[edge.id])
            else:
                budget.tick(f"{edge.id}: fiber routing")
                try:
                    routes.append(route_connection(edge, current, style, labels))
                except LayoutError as exc:
                    raise LabelPlacementError(edge.id, str(exc)) from exc
        routes += opens
        routes = refine_routes(edges, current, style, labels, routes, frozen, budget=budget)
        # Validate inside the caption search so rejection tries its alternatives.
        def validate(all_labels, all_routes):
            scene = occupied_geometry(drawing, current, style, blocks)
            fixed_keys = {a.optic or a.segment for a in fixed_labels}
            anchor = next(iter(current))
            extra = tuple(_Box(anchor, translated(a.bounds, tuple(-v for v in current[anchor].position)),
                               a.optic or a.segment, "label") for a in all_labels
                          if (a.optic or a.segment) not in fixed_keys)
            conflict = replace(scene, boxes=(*scene.boxes, *extra)).conflict(current, style)
            if conflict is not None:
                raise LabelPlacementError(conflict.second.owner, conflict.context)
            return not any(segment_intersects(leg.start, leg.end, inflate(label.bounds, style.fiber_width / 2))
                           for route in all_routes for leg in route.legs for label in all_labels)

        labels, routes = _fiber_labels(drawing, current, segments, routes, labels, frozen, style, budget, validate)
        accepted.update(segments=segments, fibers=routes)
        return labels

    def complete(current, labels):
        signature = (tuple((key, tuple(round(v, 7) for v in p.position)) for key, p in current.items()),
                     tuple(sorted((a.optic or a.segment, tuple(round(v, 7) for v in a.bounds)) for a in labels)))
        if signature in rejected:
            if rejected[signature] is not None:
                raise rejected[signature]
            return None
        try:
            result = evaluate(current, labels)
        except LabelPlacementError as exc:
            rejected[signature] = exc
            raise
        if result is None:
            rejected[signature] = None
        return result

    scene = occupied_geometry(drawing, placements, style, blocks, reserve_labels=True)
    prototypes = _prototypes(drawing, placements, style, blocks)
    fixed, _ = _fixed_content(blocks, placements)
    try:
        collision = scene.conflict(placements, style)
        if collision is not None:
            raise LabelPlacementError(next(iter(prototypes), next(iter(placements))), collision.context)
        labels = search_domains(_domains(scene, prototypes, placements, style), style, fixed, budget=budget,
                                texts={key: options[0].label.text for key, options in prototypes.items() if options},
                                complete=lambda labels: complete(placements, labels))
    except LabelPlacementError:
        placements, labels = space_labels(scope or drawing, placements, style, blocks, drawing=drawing,
                                          budget=budget, complete=complete)
    return _assemble_layout(placements, accepted["segments"], labels, style, accepted["fibers"])
