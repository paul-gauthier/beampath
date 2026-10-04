"""Typed, translatable geometry used when placing measured stage content.

Boxes obstruct drawing; lines may cross other lines. Keeping these primitives
separate leaves empty space inside a stage available to surrounding content.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .geometry import Bounds, EPSILON, add, envelope, overlap, translated, unit
from .layout import _Beam, _beam_geometry, _project, Segment, footprint, segment_intersects
from .labels import ASSOCIATION_MARGIN, boundary_leads, bounds_distance
from .routing import connector_lead, inflate, straight_connection


@dataclass(frozen=True)
class _Box:
    anchor: str
    bounds: Bounds
    owner: str
    kind: str
    frame: str | None = None

    @property
    def anchors(self):
        return (self.anchor,)

    def placed(self, placements):
        return translated(self.bounds, placements[self.anchor].position)


@dataclass(frozen=True)
class _Line:
    geometry: _Beam
    kind: str = "beam"
    padding: float = 0
    frame: str | None = None
    active: bool = True
    labels_only: bool = False

    @property
    def anchors(self):
        return self.geometry.start_owner, self.geometry.end_owner


def _position(owner, offset, axis, xs, ys):
    return (xs[owner] + offset[0]) * axis[0] + (ys[owner] + offset[1]) * axis[1]


@dataclass(frozen=True)
class _Conflict:
    first: _Box | _Line
    second: _Box
    separation: float
    context: str

    def alternatives(self, xs, ys):
        """Separating axes give linear alternatives for boxes and fixed headings."""
        a, b = self.first, self.second
        result = []
        axes = [(1, 0), (0, 1)]
        if isinstance(a, _Line):
            beam = a.geometry
            axes.append((-beam.direction[1], beam.direction[0]))
        for axis in axes:
            origin = _position(b.anchor, (0, 0), axis, xs, ys)
            bounds = inflate(b.bounds, a.padding) if isinstance(a, _Line) else b.bounds
            lo, hi = _project(bounds, (0, 0), axis)
            b_low, b_high = origin + lo, origin + hi
            if isinstance(a, _Box):
                origin = _position(a.anchor, (0, 0), axis, xs, ys)
                lo, hi = _project(a.bounds, (0, 0), axis)
                a_low, a_high = origin + lo, origin + hi
            else:
                start = _position(beam.start_owner, beam.segment.start, axis, xs, ys)
                end = _position(beam.end_owner, beam.segment.end, axis, xs, ys)
                advance = sum(d * v for d, v in zip(beam.direction, axis))
                a_low, a_high = (start, end) if advance >= 0 else (end, start)
            result.extend((b_low >= a_high + self.separation,
                           a_low >= b_high + self.separation))
        return result


@dataclass(frozen=True)
class _Scene:
    boxes: tuple[_Box, ...]
    lines: tuple[_Line, ...]

    def conflict(self, placements, style, across=None):
        def consider(a, b):
            if a.frame is not None and a.frame == b.frame:
                return False  # This immutable child was already measured and checked.
            owners = (*a.anchors, *b.anchors)
            return across is None or (any(o in across for o in owners)
                                      and any(o not in across for o in owners))

        boxes = [(box, box.placed(placements)) for box in self.boxes]
        artwork_bounds = {box.owner: bounds for box, bounds in boxes if box.kind == "artwork"}
        ambiguity = None
        for i, (a, bounds_a) in enumerate(boxes):
            for b, bounds_b in boxes[i + 1:]:
                artwork = a.kind == b.kind == "artwork"
                # Detect near misses too, including when label placement moves
                # optics that were previously clear of one another.
                padding = style.clearance if artwork else 3
                if not consider(a, b):
                    continue
                if {a.kind, b.kind} == {"artwork", "label"}:
                    label, art = (a, b) if a.kind == "label" else (b, a)
                    label_bounds = bounds_a if a.kind == "label" else bounds_b
                    if label.owner == art.owner:
                        padding = 0
                    else:
                        separation = bounds_distance(label_bounds, artwork_bounds[label.owner]) + ASSOCIATION_MARGIN
                        if bounds_distance(bounds_a, bounds_b) + EPSILON < separation:
                            context = (f"{label.owner}: stage label overlaps component artwork {art.owner}"
                                       if overlap(bounds_a, bounds_b, 3) else
                                       f"{label.owner}: label is ambiguous near component {art.owner}")
                            ambiguity = ambiguity or _Conflict(a, b, separation, context)
                if not overlap(bounds_a, bounds_b, padding):
                    continue
                if artwork:
                    problem = "overlaps" if overlap(bounds_a, bounds_b) else "has insufficient clearance"
                    context = f"{a.owner} and {b.owner}: component artwork {problem}"
                elif a.kind == b.kind == "label":
                    context = f"{a.owner}: stage labels overlap"
                else:
                    label, art = (a, b) if a.kind == "label" else (b, a)
                    context = f"{label.owner}: stage label overlaps component artwork {art.owner}"
                return _Conflict(a, b, style.clearance if artwork else 3, context)
        if ambiguity is not None:
            return ambiguity
        for line in self.lines:
            if not line.active:
                continue
            segment = line.geometry.placed(placements)
            for box, bounds in boxes:
                if line.labels_only and box.kind != "label":
                    continue
                if not consider(line, box):
                    continue
                if box.kind == "artwork" and box.owner in {segment.source, segment.target}:
                    continue
                if not segment_intersects(segment.start, segment.end, inflate(bounds, line.padding)):
                    continue
                if line.kind == "connector":
                    context = f"{segment.id}: fiber connector has insufficient clearance near {box.owner}"
                else:
                    obstacle = (f"unrelated optic {box.owner}" if box.kind == "artwork"
                                else f"stage label {box.owner}")
                    context = f"{segment.id}: {line.kind} crosses {obstacle}"
                return _Conflict(line, box, 0 if line.padding else style.clearance, context)
        return None

    def bounds(self, placements, within=None):
        # Include potential escapes even for currently straight connections:
        # moving a frame sideways can make those connector leads necessary.
        points = []
        for box in self.boxes:
            if within is not None and box.anchor not in within:
                continue
            bounds = box.placed(placements)
            if box.kind == "label":
                bounds = inflate(bounds, bounds_distance(bounds, placements[box.owner].bounds) + ASSOCIATION_MARGIN)
            x0, y0, x1, y1 = bounds
            points.extend(((x0, y0), (x1, y1)))
        for line in self.lines:
            if within is not None and not all(owner in within for owner in line.anchors):
                continue
            segment = line.geometry.placed(placements)
            for point in (segment.start, segment.end):
                points.extend((add(point, (-line.padding, -line.padding)),
                               add(point, (line.padding, line.padding))))
        return envelope(points)


def occupied_geometry(drawing, placements, style, blocks=None, *, labels=(), reserve_labels=False):
    """Freeze child content in its frame; derive current boundary port escapes.

    Only actual graph connections reserve escapes. Full-graph occupancy keeps
    stage boundaries from introducing artificial open ports or incoming beams.
    """
    blocks = {entry: block for entry, block in (blocks or {}).items() if entry in placements}
    frames = {ident: entry for entry, block in blocks.items() for ident in block.placements}
    boxes = [_Box(ident, footprint(p.instance, p.rotation),
                  ident, "artwork", frames.get(ident)) for ident, p in placements.items()]
    beams = _beam_geometry(drawing, {ident: p.instance for ident, p in placements.items()}, style,
                           {ident: p.rotation for ident, p in placements.items()})
    lines = [_Line(beam, frame=(frames.get(beam.start_owner)
                               if frames.get(beam.start_owner) == frames.get(beam.end_owner) else None))
             for beam in beams]
    for entry, block in blocks.items():
        origin = block.placements[entry].position
        offset = -origin[0], -origin[1]
        boxes.extend(_Box(entry, translated(label.bounds, offset), label.optic, "label", entry)
                     for label in block.labels)
        for route in block.fibers:
            for leg in route.legs:
                start, end = add(leg.start, offset), add(leg.end, offset)
                angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
                geometry = _Beam(Segment(leg.id, start, end, leg.source, leg.output, leg.target, leg.input),
                                 entry, entry, unit(angle))
                lines.append(_Line(geometry, "fiber", frame=entry))

    boxes.extend(_Box(label.optic, translated(label.bounds, tuple(-v for v in placements[label.optic].position)),
                      label.optic, "label") for label in labels)

    # Moving optics to accommodate labels must preserve routable attachments,
    # just as moving measured stages must. Cable interiors remain movable.
    if blocks or reserve_labels:
        clearance = max(style.clearance, style.fiber_width)
        obstacles = [(box.owner if box.kind == "artwork" else f"label-{box.owner}", box.placed(placements))
                     for box in boxes]
        for edge in drawing.connections:
            if edge.medium != "fiber":
                continue
            if (frames.get(edge.source) is not None
                    and frames.get(edge.source) == frames.get(edge.target)):
                continue  # Its measured cable already represents this connection.
            direct = (edge.source in placements and edge.target in placements
                      and straight_connection(edge, placements, obstacles, clearance) is not None)
            for ident, port in ((edge.source, edge.output), (edge.target, edge.input)):
                if ident not in placements:
                    continue
                placed = placements[ident]
                start, end = connector_lead(placed, port, clearance)
                offset = -placed.position[0], -placed.position[1]
                a, b = add(start, offset), add(end, offset)
                direction = unit(placed.port_exit_direction(port))
                # The lead must clear stroke-width obstacles; the grid endpoint
                # must additionally lie outside their full routing clearance.
                for begin, padding in ((a, style.fiber_width / 2), (b, clearance)):
                    segment = Segment(f"lead-{ident}-{port}", begin, b, ident, port)
                    lines.append(_Line(_Beam(segment, ident, ident, direction), "connector", padding,
                                       frames.get(ident), active=not direct))
    if reserve_labels:
        # Cable interiors can be rerouted. Their attachments and open ends cannot.
        from .fiber_layout import _open_fibers

        for segment in boundary_leads(drawing, placements, style):
            ident = segment.source
            offset = tuple(-v for v in placements[ident].position)
            a, b = add(segment.start, offset), add(segment.end, offset)
            direction = unit(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
            geometry = _Beam(replace(segment, start=a, end=b), ident, ident, direction)
            lines.append(_Line(geometry, labels_only=True))
        for route in _open_fibers(drawing, placements, style):
            ident = route.source or route.target
            offset = tuple(-v for v in placements[ident].position)
            for leg in route.legs:
                a, b = add(leg.start, offset), add(leg.end, offset)
                direction = unit(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
                geometry = _Beam(Segment(leg.id, a, b, leg.source, leg.output, leg.target, leg.input),
                                 ident, ident, direction)
                lines.append(_Line(geometry, "fiber", labels_only=True))
        for edge in drawing.connections:
            if edge.medium != "fiber":
                continue
            for ident, port in ((edge.source, edge.output), (edge.target, edge.input)):
                if ident not in placements:
                    continue
                placed = placements[ident]
                a, b = connector_lead(placed, port, max(style.clearance, style.fiber_width))
                offset = tuple(-v for v in placed.position)
                clearance = max(style.clearance, style.fiber_width)
                for begin, padding in ((a, style.fiber_width / 2), (b, clearance)):
                    segment = Segment(f"lead-{ident}-{port}", add(begin, offset), add(b, offset), ident, port)
                    lines.append(_Line(_Beam(segment, ident, ident, unit(placed.port_exit_direction(port))),
                                       "connector", padding, labels_only=True))
    return _Scene(tuple(boxes), tuple(lines))
