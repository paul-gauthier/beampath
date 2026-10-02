"""Resolve fixed headings and globally solve segment lengths with Kiwi."""
from __future__ import annotations

from dataclasses import dataclass
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

    def __post_init__(self):
        for name in ("pitch", "clearance", "margin", "font_size", "label_gap", "open_length", "beam_width"):
            value = finite(getattr(self, name), name)
            if value <= 0:
                raise LayoutError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        for name in ("beam_color", "font_family", "background"):
            if not isinstance(getattr(self, name), str):
                raise LayoutError(f"{name} must be a string")


def artwork_point(node: OpticInstance, source_point: Point) -> Point:
    """Transform a source SVG coordinate, relative to its placement origin."""
    art = node.spec.definition.artwork
    x, y = ((source_point[i] - art.center[i]) * art.scale for i in (0, 1))
    if node.geometry.reflected:
        x = -x
    return rotate((x, y), node.heading + node.geometry.artwork_rotation)


def footprint(node: OpticInstance) -> Bounds:
    x0, y0, x1, y1 = node.spec.definition.artwork.bounds
    return envelope([artwork_point(node, p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])


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

    @property
    def id(self):
        return self.instance.id

    def port_position(self, name: str) -> Point:
        return add(self.position, rotate(self.instance.port(name).position, self.instance.heading))

    def port_direction(self, name: str) -> float:
        return (self.instance.heading + self.instance.port(name).direction) % 360


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
class Label:
    """An upright text block, positioned at its first line's centered baseline."""

    optic: str
    text: str
    position: Point
    bounds: Bounds


@dataclass(frozen=True)
class Layout:
    placements: Mapping[str, PlacedOptic]
    segments: tuple[Segment, ...]
    labels: tuple[Label, ...]
    bounds: Bounds
    style: Style

    def __post_init__(self):
        object.__setattr__(self, "placements", MappingProxyType(dict(self.placements)))
        object.__setattr__(self, "segments", tuple(self.segments))
        object.__setattr__(self, "labels", tuple(self.labels))


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


def _labels(placements: Mapping[str, PlacedOptic], segments: list[Segment], style: Style) -> tuple[Label, ...]:
    result: list[Label] = []
    center_bounds = envelope([p.position for p in placements.values()])
    middle = ((center_bounds[0] + center_bounds[2]) / 2, (center_bounds[1] + center_bounds[3]) / 2)
    for placed in placements.values():
        text = placed.instance.spec.display_label
        if not text:
            continue
        # Conservative text metrics keep SVG generation independent of a font
        # installation or raster backend. Actual labels remain editable text.
        width, height = _text_size(text, style.font_size)
        art_anchor = placed.instance.spec.definition.label_anchor
        anchor = (add(placed.position, artwork_point(placed.instance, art_anchor))
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
        h = placed.instance.heading % 180
        if 45 < h < 135:
            preferred = "left" if placed.position[0] < middle[0] else "right"
        else:
            preferred = "top" if placed.position[1] < middle[1] else "bottom"
        order = [preferred] + [side for side in ("bottom", "top", "right", "left") if side != preferred]
        corners = ("bottom_right", "bottom_left", "top_right", "top_left")
        order += [side for side in corners if preferred in side] + [side for side in corners if preferred not in side]
        for side in order:
            cx, cy = candidates[side]
            box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
            if any(overlap(box, p.bounds, 3) for p in placements.values()):
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
    for node in nodes.values():
        if node.heading is None:
            raise LayoutError(f"{node.id}: connect the optic to an initial beam")
        for port in node.geometry.ports:
            if port.kind == "input" and port.required and not setup._input_used(node.id, port.name):
                raise LayoutError(f"{node.id}.{port.name}: required input is not connected")

    solver = kiwi.Solver()
    xs = {ident: kiwi.Variable(f"{ident}.x") for ident in nodes}
    ys = {ident: kiwi.Variable(f"{ident}.y") for ident in nodes}
    lengths = {edge.id: kiwi.Variable(f"{edge.id}.length") for edge in setup.connections}
    footprints = {ident: footprint(node) for ident, node in nodes.items()}

    def required(constraint, context):
        try:
            solver.addConstraint(constraint)
        except kiwi.UnsatisfiableConstraint as exc:
            raise LayoutError(f"{context}: incompatible placement constraints") from exc

    for root in setup._roots:
        required(xs[root.optic] == root.origin[0], root.optic)
        required(ys[root.optic] == root.origin[1], root.optic)
    for node in nodes.values():
        if node.at is not None:
            required(xs[node.id] == node.at[0], node.id)
            required(ys[node.id] == node.at[1], node.id)

    for edge in setup.connections:
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
            solver.addConstraint((length == minimum) | kiwi.strength.weak)
        else:
            required(length == edge.distance, context)
        required(xs[target.id] + b[0] == xs[source.id] + a[0] + length * d[0], context)
        required(ys[target.id] + b[1] == ys[source.id] + a[1] + length * d[1], context)

    # Prefer equal gaps along maximal straight runs, without making equality a
    # hard requirement when explicit pins or varying glyph clearances conflict.
    incoming, outgoing = {}, {}
    for edge in setup.connections:
        incoming.setdefault(edge.target, []).append(edge)
        outgoing.setdefault(edge.source, []).append(edge)
    for node in nodes.values():
        inputs = [p for p in node.geometry.ports if p.kind == "input"]
        outputs = [p for p in node.geometry.ports if p.kind == "output"]
        if (len(inputs) == len(outputs) == 1 and aligned(inputs[0].direction, outputs[0].direction)
                and len(incoming.get(node.id, [])) == len(outgoing.get(node.id, [])) == 1):
            a, b = incoming[node.id][0], outgoing[node.id][0]
            solver.addConstraint((lengths[a.id] == lengths[b.id]) | kiwi.strength.medium)
    solver.updateVariables()

    placements = {}
    for ident, node in nodes.items():
        position = clean(xs[ident].value()), clean(ys[ident].value())
        placements[ident] = PlacedOptic(node, position, translated(footprints[ident], position))
    items = list(placements.values())
    for index, a in enumerate(items):
        for b in items[index + 1:]:
            if overlap(a.bounds, b.bounds):
                raise LayoutError(f"{a.id} and {b.id}: component artwork overlaps")
    segments = [Segment(edge.id, placements[edge.source].port_position(edge.output),
                        placements[edge.target].port_position(edge.input),
                        edge.source, edge.output, edge.target, edge.input)
                for edge in setup.connections]
    for placed in placements.values():
        for index, port in enumerate(placed.instance.geometry.ports):
            if port.kind == "output" and not setup._output_used(placed.id, port.name):
                a = placed.port_position(port.name)
                d = unit(placed.port_direction(port.name))
                reach = _project(placed.bounds, a, d)[1]
                length = max(style.open_length, reach + style.clearance)
                b = a[0] + length * d[0], a[1] + length * d[1]
                segments.append(Segment(f"stub-{placed.id}-{index:02d}", a, b, placed.id, port.name))
    for index, root in enumerate(setup._roots):
        if root.input is None:
            continue
        placed = placements[root.optic]
        if not placed.instance.port(root.input, "input").draw_lead_in:
            continue
        b = placed.port_position(root.input)
        d = unit(placed.port_direction(root.input))
        reach = -_project(placed.bounds, b, d)[0]
        length = max(style.open_length, reach + style.clearance)
        a = b[0] - length * d[0], b[1] - length * d[1]
        segments.append(Segment(f"lead-in-{placed.id}-{index:02d}", a, b,
                                None, None, placed.id, root.input))
    for segment in segments:
        for placed in placements.values():
            if placed.id not in {segment.source, segment.target} and segment_intersects(
                    segment.start, segment.end, placed.bounds):
                raise LayoutError(f"{segment.id}: beam crosses unrelated optic {placed.id}")
    labels = _labels(placements, segments, style)
    points = []
    for bounds in [p.bounds for p in placements.values()] + [label.bounds for label in labels]:
        points.extend(((bounds[0], bounds[1]), (bounds[2], bounds[3])))
    for segment in segments:
        points.extend((segment.start, segment.end))
    x0, y0, x1, y1 = envelope(points)
    bounds = x0 - style.margin, y0 - style.margin, x1 + style.margin, y1 + style.margin
    return Layout(placements, tuple(segments), labels, bounds, style)
