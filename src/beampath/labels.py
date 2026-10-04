"""Adjacent label candidates and deterministic joint placement."""
from __future__ import annotations

from dataclasses import replace
import heapq
import itertools
import math

import kiwisolver as kiwi

from .errors import LayoutError
from .geometry import EPSILON, add, envelope, overlap, translated, unit
from .layout import Label, Segment, _project, _text_size, artwork_point, segment_intersects


_SEARCH_LIMIT = 1000
ASSOCIATION_MARGIN = 3


def bounds_distance(a, b):
    """Euclidean distance between the nearest points of two rectangles."""
    return math.hypot(max(a[0] - b[2], b[0] - a[2], 0),
                      max(a[1] - b[3], b[1] - a[3], 0))


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


def associated(label, placements):
    own = bounds_distance(label.bounds, placements[label.optic].bounds)
    return all(bounds_distance(label.bounds, p.bounds) + EPSILON >= own + ASSOCIATION_MARGIN
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


def place_labels(placements, segments, style, fixed=(), exclusions=(), *, choices=None):
    """Try complete local assignments before requesting any component movement."""
    choices = candidates(placements, style) if choices is None else choices
    fixed_ids = {label.optic for label in fixed}
    domains = {}
    for ident, options in choices.items():
        if ident in fixed_ids:
            continue
        domains[ident] = tuple(label for label in options
                              if associated(label, placements)
                              and not any(overlap(label.bounds, p.bounds,
                                                  0 if p.id == ident else 3)
                                          for p in placements.values())
                              and not any(overlap(label.bounds, b) for b in exclusions)
                              and not any(overlap(label.bounds, other.bounds, 3) for other in fixed)
                              and not any(segment_intersects(s.start, s.end, label.bounds) for s in segments))
    attempts = 0
    failed = next(iter(domains), None)

    def search(remaining, chosen):
        nonlocal attempts, failed
        if not remaining:
            return chosen
        ident = min(remaining, key=lambda key: len(remaining[key]))
        failed = ident
        for label in remaining[ident]:
            if attempts >= _SEARCH_LIMIT:
                raise LayoutError(f"{ident} ({label.text}): automatic label search budget exhausted "
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
        raise LabelPlacementError(failed, placements[failed].instance.spec.display_label)
    return tuple(fixed) + tuple(selected[ident] for ident in placements if ident in selected)


def space_labels(scope, placements, style, blocks=None, *, drawing=None):
    """Refine automatic spacing while preserving pins and measured child frames."""
    from .layout import _root_origins, _solve_beams

    blocks = blocks or {}
    grouped = {ident for block in blocks.values() for ident in block.placements}
    nodes = {ident: replace(p.instance, at=None) if ident in grouped and ident not in blocks else p.instance
             for ident, p in placements.items()}
    edges = [edge for edge in scope.connections if edge.medium == "free_space"
             and edge.source in nodes and edge.target in nodes]
    solved, labels = _solve_beams(nodes, edges, _root_origins(scope), style, blocks,
                                  drawing=scope if drawing is None else drawing, initial=placements)
    return {ident: replace(p, instance=placements[ident].instance) for ident, p in solved.items()}, labels


def solve_spacing(drawing, style, blocks, initial,
                  constraints, xs, ys, lengths, placements_now, limit):
    """Branch over attached labels and separating axes, preferring compact solves.

    Each queue entry owns its discrete choices and required separations. Kiwi
    variables are shared, so every popped solver must refresh them before use.
    """
    from .occupied import _Box, occupied_geometry
    from .routing import inflate

    fixed_ids = {label.optic for block in blocks.values() for label in block.labels}
    initial_scene = occupied_geometry(drawing, initial, style, blocks, reserve_labels=True)
    # A label cannot escape a collision with a line fixed in its own frame by
    # moving that frame. Remove those choices before exploring spacing states.
    def movable(label):
        return not any(line.active and line.anchors == (label.optic, label.optic)
                       and segment_intersects(line.geometry.placed(initial).start,
                                              line.geometry.placed(initial).end,
                                              inflate(label.bounds, line.padding))
                       for line in initial_scene.lines)

    local_choices = {ident: tuple(move_label(label, tuple(-v for v in initial[ident].position))
                                 for label in options if movable(label))
                     for ident, options in candidates(initial, style).items() if ident not in fixed_ids}
    pending, serial = [], itertools.count()
    seen = set()
    attempts = 0
    first_error = None

    def enqueue(branch, selected, context):
        nonlocal attempts
        # Different conflict orders can produce the same required constraints.
        # Deduplicate those branches without merging genuinely different solves.
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
        if attempts >= limit:
            raise LayoutError(f"{context}: automatic label spacing search budget exhausted "
                              f"({limit} candidate states)")
        attempts += 1
        trial = kiwi.Solver()
        try:
            for constraint in (*constraints, *branch):
                trial.addConstraint(constraint)
        except kiwi.UnsatisfiableConstraint:
            return
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
        chosen = {ident: move_label(local_choices[ident][index], placements[ident].position)
                  for ident, index in selected.items()}
        scene = occupied_geometry(drawing, placements, style, blocks,
                                  labels=tuple(chosen.values()), reserve_labels=True)
        collision = scene.conflict(placements, style)
        if collision is not None:
            first_error = first_error or collision.context
            for alternative in collision.alternatives(xs, ys):
                enqueue((*branch, alternative), selected, collision.context)
            continue
        fixed = tuple(move_label(label, tuple(placements[entry].position[i]
                                             - block.placements[entry].position[i] for i in (0, 1)))
                      for entry, block in blocks.items() for label in block.labels)
        choices = {}
        for ident, options in local_choices.items():
            if ident in chosen:
                choices[ident] = (chosen[ident],)
                continue
            valid = []
            for local in options:
                label = move_label(local, placements[ident].position)
                box = _Box(ident, local.bounds, ident, "label")
                if replace(scene, boxes=(*scene.boxes, box)).conflict(placements, style) is None:
                    valid.append(label)
            choices[ident] = tuple(valid)
        try:
            labels = place_labels(placements, (), style, fixed, choices=choices)
        except LabelPlacementError as exc:
            first_error = first_error or str(exc)
            for index in range(len(local_choices[exc.optic])):
                enqueue(branch, {**selected, exc.optic: index}, str(exc))
        else:
            return placements, labels
    raise LayoutError(f"{first_error}: no feasible adjacent labeling with required constraints")
