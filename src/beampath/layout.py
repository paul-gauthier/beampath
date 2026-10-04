"""Resolve fixed headings and globally solve segment lengths with Kiwi."""
from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping
import math

import kiwisolver as kiwi

from .errors import LayoutError
from .geometry import (
    Bounds, Point, EPSILON, add, aligned, clean, envelope, finite, overlap,
    rotate, translated, unit,
)
from .model import OpticInstance, Setup


@dataclass(frozen=True)
class Style:
    """Control spacing, labels, beam appearance, and fiber routing.

    pitch sets the minimum automatic port gap; clearance reserves artwork
    space; margin surrounds the canvas; open_length sets nominal open stubs.
    font_size, font_family, and label_gap control labels. beam_color and
    beam_width control free space; fiber_color, fiber_width, and fiber_radius
    control cables; background sets the canvas color. Dimensions are diagram
    units. Numeric options must be positive, except fiber_radius may be zero."""
    pitch: float = 190
    clearance: float = 20
    margin: float = 80
    font_size: float = 23
    label_gap: float = 14
    open_length: float = 95
    beam_width: float = 2.3
    beam_color: str = "#CC0000"
    font_family: str = "Helvetica, Arial, sans-serif"
    background: str = "#FFFFFF"
    fiber_color: str = "#1B1E89"
    fiber_width: float = 3.75
    fiber_radius: float = 10

    def __post_init__(self):
        for name in ("pitch", "clearance", "margin", "font_size", "label_gap", "open_length", "beam_width", "fiber_width"):
            value = finite(getattr(self, name), name)
            if value <= 0:
                raise LayoutError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        radius = finite(self.fiber_radius, "fiber_radius")
        if radius < 0:
            raise LayoutError("fiber_radius must be nonnegative")
        object.__setattr__(self, "fiber_radius", radius)
        for name in ("beam_color", "font_family", "background", "fiber_color"):
            if not isinstance(getattr(self, name), str):
                raise LayoutError(f"{name} must be a string")


def artwork_point(node: OpticInstance, source_point: Point, rotation: float | None = None) -> Point:
    """Transform a source SVG coordinate, relative to its placement origin."""
    art = node.spec.definition.artwork
    x, y = ((source_point[i] - art.center[i]) * art.scale for i in (0, 1))
    if node.geometry.reflected:
        x = -x
    pose = (node.heading or 0) if rotation is None else rotation
    return rotate((x, y), pose + node.geometry.artwork_rotation)


def footprint(node: OpticInstance, rotation: float | None = None) -> Bounds:
    x0, y0, x1, y1 = node.spec.definition.artwork.bounds
    return envelope([artwork_point(node, p, rotation) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])


def _text_size(text: str, font_size: float) -> Point:
    # Conservative label metrics.
    widths = {"i": .3, "l": .3, "I": .35, " ": .35, "W": 1, "M": 1}
    lines = text.split("\n")
    width = max(sum(widths.get(c, .72) for c in line) for line in lines)
    return font_size * width + 4, font_size * 1.25 * len(lines)


@dataclass(frozen=True)
class PlacedOptic:
    instance: OpticInstance
    position: Point
    bounds: Bounds
    rotation: float | None = None

    def __post_init__(self):
        if self.rotation is None:
            object.__setattr__(self, "rotation", self.instance.heading or 0)

    @property
    def id(self):
        return self.instance.id

    def port_position(self, name: str) -> Point:
        return add(self.position, rotate(self.instance.port(name).position, self.rotation))

    def port_direction(self, name: str) -> float | None:
        direction = self.instance.port(name).direction
        return None if direction is None else (self.rotation + direction) % 360

    def port_exit_direction(self, name: str) -> float:
        """Outward drawing tangent, independent of a fiber's optical heading."""
        port = self.instance.port(name)
        direction = (port.exit_direction if port.medium == "fiber" else
                     port.direction + (180 if port.kind == "input" else 0))
        return (self.rotation + direction) % 360


@dataclass(frozen=True)
class Segment:
    """A beam segment; open ends have no source/output or target/input."""

    id: str
    start: Point
    end: Point
    source: str | None
    output: str | None
    target: str | None = None
    input: str | None = None

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class _Beam:
    """A visible beam with endpoint offsets in fixed component frames."""

    segment: Segment
    start_owner: str
    end_owner: str
    direction: Point

    def placed(self, placements):
        return replace(self.segment,
                       start=add(placements[self.start_owner].position, self.segment.start),
                       end=add(placements[self.end_owner].position, self.segment.end))


@dataclass(frozen=True)
class FiberRoute:
    """One semantic connection with any number of layout-only bends."""

    id: str
    points: tuple[Point, ...]
    source: str | None
    output: str | None
    target: str | None = None
    input: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "points", tuple(tuple(p) for p in self.points))
        if len(self.points) < 2:
            raise LayoutError("A fiber route needs at least two points")

    @property
    def start(self):
        return self.points[0]

    @property
    def end(self):
        return self.points[-1]

    @property
    def legs(self):
        return tuple(Segment(f"{self.id}-{i}", a, b, self.source, self.output, self.target, self.input)
                     for i, (a, b) in enumerate(zip(self.points, self.points[1:])))

    @property
    def length(self):
        return sum(leg.length for leg in self.legs)


@dataclass(frozen=True)
class Label:
    """An upright text block, positioned at its first line's centered baseline."""

    optic: str
    text: str
    position: Point
    bounds: Bounds


@dataclass(frozen=True)
class Layout:
    """An immutable rendered snapshot with placements, segments, fibers, labels, bounds, and style."""
    placements: Mapping[str, PlacedOptic]
    segments: tuple[Segment, ...]
    labels: tuple[Label, ...]
    bounds: Bounds
    style: Style
    fibers: tuple[FiberRoute, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "placements", MappingProxyType(dict(self.placements)))
        object.__setattr__(self, "segments", tuple(self.segments))
        object.__setattr__(self, "labels", tuple(self.labels))
        object.__setattr__(self, "fibers", tuple(self.fibers))


def _project(bounds: Bounds, anchor: Point, direction: Point) -> tuple[float, float]:
    values = [(x - anchor[0]) * direction[0] + (y - anchor[1]) * direction[1]
              for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])]
    return min(values), max(values)


def segment_intersects(start: Point, end: Point, bounds: Bounds) -> bool:
    """Liang–Barsky clipping, allowing lines that merely touch a box edge."""
    x0, y0, x1, y1 = bounds
    x0, y0, x1, y1 = x0 + EPSILON, y0 + EPSILON, x1 - EPSILON, y1 - EPSILON
    lo, hi = 0.0, 1.0
    dx, dy = end[0] - start[0], end[1] - start[1]
    for p, q in ((-dx, start[0] - x0), (dx, x1 - start[0]),
                 (-dy, start[1] - y0), (dy, y1 - start[1])):
        if abs(p) < EPSILON:
            if q < 0:
                return False
        elif p < 0:
            lo = max(lo, q / p)
        else:
            hi = min(hi, q / p)
        if lo > hi:
            return False
    return True


def _labels(placements: Mapping[str, PlacedOptic], segments: list[Segment], style: Style,
            fixed: tuple[Label, ...] = (), exclusions: tuple[Bounds, ...] = ()) -> tuple[Label, ...]:
    result: list[Label] = list(fixed)
    labeled = {label.optic for label in fixed}
    center_bounds = envelope([p.position for p in placements.values()])
    middle = ((center_bounds[0] + center_bounds[2]) / 2, (center_bounds[1] + center_bounds[3]) / 2)
    for placed in placements.values():
        if placed.id in labeled:
            continue
        text = placed.instance.spec.display_label
        if not text:
            continue
        # Conservative text metrics keep SVG generation independent of a font
        # installation or raster backend. Actual labels remain editable text.
        width, height = _text_size(text, style.font_size)
        art_anchor = placed.instance.spec.definition.label_anchor
        anchor = (add(placed.position, artwork_point(placed.instance, art_anchor, placed.rotation))
                  if art_anchor is not None else placed.position)
        x0, y0, x1, y1 = placed.bounds
        candidates = {
            "top": (anchor[0], y0 - style.label_gap - height / 2),
            "bottom": (anchor[0], y1 + style.label_gap + height / 2),
            "left": (x0 - style.label_gap - width / 2, anchor[1]),
            "right": (x1 + style.label_gap + width / 2, anchor[1]),
            "top_left": (x0 - style.label_gap - width / 2, y0 - style.label_gap - height / 2),
            "top_right": (x1 + style.label_gap + width / 2, y0 - style.label_gap - height / 2),
            "bottom_left": (x0 - style.label_gap - width / 2, y1 + style.label_gap + height / 2),
            "bottom_right": (x1 + style.label_gap + width / 2, y1 + style.label_gap + height / 2),
        }
        h = placed.rotation % 180
        if 45 < h < 135:
            preferred = "left" if placed.position[0] < middle[0] else "right"
        else:
            preferred = "top" if placed.position[1] < middle[1] else "bottom"
        order = [preferred] + [side for side in ("bottom", "top", "right", "left") if side != preferred]
        corners = ("bottom_right", "bottom_left", "top_right", "top_left")
        order += [side for side in corners if preferred in side] + [side for side in corners if preferred not in side]
        # Preserve immediate placements first, then search a bounded set of
        # outward rings. Tight branch layouts can surround all eight neighbors.
        positions = []
        for ring in range(9):
            gap = ring * style.font_size * 1.25
            for side in order:
                cx, cy = candidates[side]
                cx += gap * (("right" in side) - ("left" in side))
                cy += gap * (("bottom" in side) - ("top" in side))
                positions.append((cx, cy))
        for cx, cy in positions:
            box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
            if any(overlap(box, p.bounds, 3) for p in placements.values()):
                continue
            if any(overlap(box, bounds) for bounds in exclusions):
                continue
            if any(overlap(box, label.bounds, 3) for label in result):
                continue
            if any(segment_intersects(s.start, s.end, box) for s in segments):
                continue
            baseline = cy + style.font_size * .35 - (height - style.font_size * 1.25) / 2
            result.append(Label(placed.id, text, (cx, baseline), box))
            break
        else:
            raise LayoutError(f"{placed.id} ({text}): no clear position for its label")
    return tuple(result)


def layout(setup: Setup, *, style: Style | None = None) -> Layout:
    style = style or Style()
    if not isinstance(style, Style):
        raise LayoutError("style must be a Style object")
    nodes = {n.id: n for n in setup.optics}
    if not nodes:
        raise LayoutError("The setup has no components")
    anchors = _root_origins(setup)
    if setup._layout_groups:
        from .group_layout import grouped_layout
        return grouped_layout(setup, style)
    if any(p.medium == "fiber" for n in nodes.values() for p in n.geometry.ports):
        from .fiber_layout import mixed_layout
        return mixed_layout(setup, style)
    for node in nodes.values():
        if node.heading is None:
            raise LayoutError(f"{node.id}: connect the optic to an initial beam")
        for port in node.geometry.ports:
            if port.kind == "input" and port.required and not setup._input_used(node.id, port.name):
                raise LayoutError(f"{node.id}.{port.name}: required input is not connected")

    placements = _solve_beams(nodes, setup.connections, anchors, style, drawing=setup)
    return _finish_free_space(setup, placements, style)


def _root_origins(setup):
    origins = {}
    for root in setup._roots:
        if root.optic in origins and math.dist(origins[root.optic], root.origin) > EPSILON:
            raise LayoutError(f"{root.optic}: incompatible placement constraints on initial paths")
        origins[root.optic] = root.origin
    return origins


_BEAM_SEARCH_LIMIT = 1000


def _solve_beams(nodes, connections, anchors, style, blocks=None, *, drawing):
    """Continuous spacing for one or more already oriented free-space sections."""
    solver = kiwi.Solver()
    constraints = []
    xs = {ident: kiwi.Variable(f"{ident}.x") for ident in nodes}
    ys = {ident: kiwi.Variable(f"{ident}.y") for ident in nodes}
    lengths = {edge.id: kiwi.Variable(f"{edge.id}.length") for edge in connections}
    blocks = blocks or {}
    poses = {ident: placed.rotation for block in blocks.values()
             for ident, placed in block.placements.items()}
    footprints = {ident: footprint(node, poses.get(ident)) for ident, node in nodes.items()}
    beams = _beam_geometry(drawing, nodes, style, poses)

    def add_constraint(constraint):
        solver.addConstraint(constraint)
        constraints.append(constraint)

    def required(constraint, context):
        try:
            add_constraint(constraint)
        except kiwi.UnsatisfiableConstraint as exc:
            raise LayoutError(f"{context}: incompatible placement constraints") from exc

    for ident, origin in anchors.items():
        required(xs[ident] == origin[0], ident)
        required(ys[ident] == origin[1], ident)
    for node in nodes.values():
        if node.at is not None:
            required(xs[node.id] == node.at[0], node.id)
            required(ys[node.id] == node.at[1], node.id)

    # A nested group has already solved its internal geometry in this render.
    # Its frame can translate while participating in surrounding beam equations.
    for entry, block in blocks.items():
        origin = block.placements[entry].position
        for ident, placed in block.placements.items():
            required(xs[ident] - xs[entry] == placed.position[0] - origin[0], ident)
            required(ys[ident] - ys[entry] == placed.position[1] - origin[1], ident)

    for edge in connections:
        source, target = nodes[edge.source], nodes[edge.target]
        out, inp = source.port(edge.output), target.port(edge.input)
        d = unit(source.heading + out.direction)
        a, b = rotate(out.position, source.heading), rotate(inp.position, target.heading)
        clearance = max(1.0, _project(footprints[source.id], a, d)[1]
                        - _project(footprints[target.id], b, d)[0] + style.clearance)
        length = lengths[edge.id]
        context = f"{edge.target}.{edge.input} ({target.spec.display_label})"
        required(length >= clearance, context)
        if edge.distance is None:
            minimum = max(style.pitch, clearance)
            required(length >= minimum, context)
            add_constraint((length == minimum) | kiwi.strength.weak)
        else:
            required(length == edge.distance, context)
        required(xs[target.id] + b[0] == xs[source.id] + a[0] + length * d[0], context)
        required(ys[target.id] + b[1] == ys[source.id] + a[1] + length * d[1], context)

    # Prefer equal gaps along maximal straight runs, without making equality a
    # hard requirement when explicit pins or varying glyph clearances conflict.
    incoming, outgoing = {}, {}
    for edge in connections:
        incoming.setdefault(edge.target, []).append(edge)
        outgoing.setdefault(edge.source, []).append(edge)
    for node in nodes.values():
        inputs = [p for p in node.geometry.ports if p.kind == "input"]
        outputs = [p for p in node.geometry.ports if p.kind == "output"]
        if (len(inputs) == len(outputs) == 1
                and inputs[0].medium == outputs[0].medium == "free_space"
                and aligned(inputs[0].direction, outputs[0].direction)
                and len(incoming.get(node.id, [])) == len(outgoing.get(node.id, [])) == 1):
            a, b = incoming[node.id][0], outgoing[node.id][0]
            add_constraint((lengths[a.id] == lengths[b.id]) | kiwi.strength.medium)
    solver.updateVariables()

    def placements_now():
        result = {}
        for ident, node in nodes.items():
            position = clean(xs[ident].value()), clean(ys[ident].value())
            result[ident] = PlacedOptic(
                node, position, translated(footprints[ident], position), poses.get(ident),
            )
        return result

    def conflict(placements):
        items = list(placements.values())
        for index, a in enumerate(items):
            for b in items[index + 1:]:
                if not overlap(a.bounds, b.bounds):
                    continue
                alternatives = []
                for axis, coordinates in enumerate((xs, ys)):
                    for first, second in ((a, b), (b, a)):
                        separation = (footprints[first.id][axis + 2]
                                      - footprints[second.id][axis] + style.clearance)
                        alternatives.append(coordinates[second.id] - coordinates[first.id]
                                            >= separation)
                return f"{a.id} and {b.id}: component artwork overlaps", alternatives
        for beam in beams:
            segment = beam.placed(placements)
            for obstacle in items:
                if obstacle.id in {segment.source, segment.target} or not segment_intersects(
                        segment.start, segment.end, obstacle.bounds):
                    continue
                alternatives = []
                # Separating-axis theorem for a finite segment and an axis-aligned
                # box: box axes plus the segment normal. Fixed headings keep all
                # projected endpoints linear, including displaced optical ports.
                for axis in ((1, 0), (0, 1), (-beam.direction[1], beam.direction[0])):
                    beam_start, beam_end = (
                        (xs[owner] + offset[0]) * axis[0] + (ys[owner] + offset[1]) * axis[1]
                        for owner, offset in ((beam.start_owner, beam.segment.start),
                                              (beam.end_owner, beam.segment.end)))
                    advance = sum(d * a for d, a in zip(beam.direction, axis))
                    low, high = ((beam_start, beam_end) if advance >= 0
                                 else (beam_end, beam_start))
                    origin = xs[obstacle.id] * axis[0] + ys[obstacle.id] * axis[1]
                    lo, hi = _project(footprints[obstacle.id], (0, 0), axis)
                    alternatives.extend((origin + lo >= high + style.clearance,
                                         low >= origin + hi + style.clearance))
                return (f"{segment.id}: beam crosses unrelated optic {obstacle.id}",
                        alternatives)
        return None

    # A greedy separation can block a later collision. Explore alternatives with
    # backtracking; each branch permanently separates the selected conflict.
    # Rebuild every candidate solver because rejected Kiwi constraints can leave
    # its tableau changed. Stored solvers share variables, so update on each pop.
    pending = [((), solver)]
    attempts = 0
    first_error = None
    while pending:
        accepted, current = pending.pop()
        current.updateVariables()
        placements = placements_now()
        collision = conflict(placements)
        if collision is None:
            return placements
        context, alternatives = collision
        first_error = first_error or context
        candidates = []
        for order, alternative in enumerate(alternatives):
            if attempts >= _BEAM_SEARCH_LIMIT:
                raise LayoutError(f"{context}: automatic layout search budget exhausted "
                                  f"({_BEAM_SEARCH_LIMIT} candidate states)")
            attempts += 1
            trial = kiwi.Solver()
            branch = (*accepted, alternative)
            try:
                for constraint in (*constraints, *branch):
                    trial.addConstraint(constraint)
            except kiwi.UnsatisfiableConstraint:
                continue
            trial.updateVariables()
            score = round(sum(length.value() for length in lengths.values()), 7)
            candidates.append((score, order, branch, trial))
        # Stack order visits the smallest total length first, with stable axis
        # order breaking ties. Existing soft preferences still apply per solve.
        for _, _, branch, trial in sorted(candidates, key=lambda item: item[:2], reverse=True):
            pending.append((branch, trial))
    raise LayoutError(f"{first_error}: no feasible automatic spacing with required constraints")


def _finish_free_space(setup, placements, style):
    segments = _beam_segments(setup, placements, style)
    labels = _labels(placements, segments, style)
    return _assemble_layout(placements, segments, labels, style)


def _beam_geometry(setup, nodes, style, poses=None):
    """Describe beams once for both solving and drawing, using full port occupancy.

    Both endpoints of an open beam move with its owner. A connected beam has
    one endpoint in each component frame. Scope-only roots must not be supplied
    here: they anchor placement but do not represent incoming light.
    """
    poses = poses or {}
    placements = {ident: PlacedOptic(node, (0, 0), footprint(node, poses.get(ident)), poses.get(ident))
                  for ident, node in nodes.items()}
    beams = []
    for edge in setup.connections:
        if edge.medium != "free_space" or edge.source not in nodes or edge.target not in nodes:
            continue
        source, target = placements[edge.source], placements[edge.target]
        segment = Segment(edge.id, source.port_position(edge.output), target.port_position(edge.input),
                          edge.source, edge.output, edge.target, edge.input)
        beams.append(_Beam(segment, edge.source, edge.target, unit(source.port_direction(edge.output))))
    for placed in placements.values():
        connected_outputs = [p for p in placed.instance.geometry.ports
                             if p.kind == "output" and p.medium == "free_space"
                             and setup._output_used(placed.id, p.name)]
        for index, port in enumerate(placed.instance.geometry.ports):
            if (port.kind == "output" and port.medium == "free_space" and port.draw_open
                    and not setup._output_used(placed.id, port.name)):
                # Collinear modes share a drawn path. An unused coincident port
                # must not add a second arrow or a stub past the next optic.
                if any(port.position == other.position and aligned(port.direction, other.direction)
                       for other in connected_outputs):
                    continue
                a = placed.port_position(port.name)
                d = unit(placed.port_direction(port.name))
                reach = _project(placed.bounds, a, d)[1]
                length = max(style.open_length, reach + style.clearance)
                b = a[0] + length * d[0], a[1] + length * d[1]
                segment = Segment(f"stub-{placed.id}-{index:02d}", a, b, placed.id, port.name)
                beams.append(_Beam(segment, placed.id, placed.id, d))
    for index, root in enumerate(setup._roots):
        if root.input is None or root.optic not in placements:
            continue
        placed = placements[root.optic]
        port = placed.instance.port(root.input, "input")
        if not port.draw_lead_in or port.medium == "fiber":
            continue
        b = placed.port_position(root.input)
        d = unit(placed.port_direction(root.input))
        reach = -_project(placed.bounds, b, d)[0]
        length = max(style.open_length, reach + style.clearance)
        a = b[0] - length * d[0], b[1] - length * d[1]
        segment = Segment(f"lead-in-{placed.id}-{index:02d}", a, b, None, None, placed.id, root.input)
        beams.append(_Beam(segment, placed.id, placed.id, d))
    return tuple(beams)


def _beam_segments(setup, placements, style):
    items = list(placements.values())
    for index, a in enumerate(items):
        for b in items[index + 1:]:
            if overlap(a.bounds, b.bounds):
                raise LayoutError(f"{a.id} and {b.id}: component artwork overlaps")
    beams = _beam_geometry(setup, {ident: p.instance for ident, p in placements.items()}, style,
                           {ident: p.rotation for ident, p in placements.items()})
    segments = [beam.placed(placements) for beam in beams]
    for segment in segments:
        for placed in placements.values():
            if placed.id not in {segment.source, segment.target} and segment_intersects(
                    segment.start, segment.end, placed.bounds):
                raise LayoutError(f"{segment.id}: beam crosses unrelated optic {placed.id}")
    return segments


def _content_bounds(placements, segments, labels, fibers=()):
    points = []
    for bounds in [p.bounds for p in placements.values()] + [label.bounds for label in labels]:
        points.extend(((bounds[0], bounds[1]), (bounds[2], bounds[3])))
    for segment in segments:
        points.extend((segment.start, segment.end))
    for route in fibers:
        points.extend(route.points)
    return envelope(points)


def _assemble_layout(placements, segments, labels, style, fibers=()):
    x0, y0, x1, y1 = _content_bounds(placements, segments, labels, fibers)
    bounds = x0 - style.margin, y0 - style.margin, x1 + style.margin, y1 + style.margin
    return Layout(placements, tuple(segments), labels, bounds, style, tuple(fibers))
