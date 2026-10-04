"""Measure local stage frames, arrange rows, then route between the frames."""
from __future__ import annotations

from dataclasses import replace

from .errors import LayoutError
from .fiber_layout import _collides, _open_fibers, _orient_fiber_components, _place, _validate
from .geometry import add, overlap, translated
from .layout import (
    Layout, Segment, _assemble_layout, _beam_segments, _content_bounds, _labels, segment_intersects,
)
from .model import Root, Setup
from .routing import connector_lead, inflate, refine_routes, route_connection
from .occupied import occupied_geometry


def _translate(layout, delta):
    return replace(
        layout,
        placements={ident: replace(p, position=add(p.position, delta), bounds=translated(p.bounds, delta))
                    for ident, p in layout.placements.items()},
        segments=tuple(replace(s, start=add(s.start, delta), end=add(s.end, delta)) for s in layout.segments),
        labels=tuple(replace(label, position=add(label.position, delta), bounds=translated(label.bounds, delta))
                     for label in layout.labels),
        fibers=tuple(replace(route, points=tuple(add(p, delta) for p in route.points)) for route in layout.fibers),
        bounds=translated(layout.bounds, delta),
    )


def _finish(setup, placements, style, children=()):
    """Keep measured child content intact; route new edges around all labels.

    Use the full graph for port occupancy even inside a local frame. A boundary
    connection must not temporarily grow a stub (or leave room for one).
    """
    fixed_labels = tuple(label for child in children for label in child.labels)
    fixed_fibers = {route.id: route for child in children for route in child.fibers}
    fixed_nodes = {ident for child in children for ident in child.placements}
    blocks = {next(iter(child.placements)): child for child in children}
    edges = [edge for edge in setup.connections if edge.medium == "fiber"
             and edge.source in placements and edge.target in placements]
    _orient_fiber_components(placements, edges, setup, style, fixed_nodes, blocks)
    segments = _beam_segments(setup, placements, style)
    opens = [fixed_fibers.get(route.id, route) for route in _open_fibers(setup, placements, style)]

    # Reserve escapes even for connections that leave this scope, so local
    # labels cannot obstruct the return fiber routed by the enclosing group.
    leads = []
    for edge in setup.connections:
        if edge.medium != "fiber":
            continue
        for ident, port in ((edge.source, edge.output), (edge.target, edge.input)):
            if ident in placements:
                a, b = connector_lead(placements[ident], port, max(style.clearance, style.fiber_width))
                leads.append(Segment(f"lead-{ident}-{port}", a, b, ident, port))
    clearance = max(style.clearance, style.fiber_width)
    exclusions = tuple(inflate((min(s.start[0], s.end[0]), min(s.start[1], s.end[1]),
                                max(s.start[0], s.end[0]), max(s.start[1], s.end[1])), clearance)
                       for s in leads)
    fibers = [fixed_fibers[edge.id] if edge.id in fixed_fibers
              else route_connection(edge, placements, style, fixed_labels) for edge in edges] + opens
    try:
        labels = _labels(placements, segments + leads + [leg for r in fibers for leg in r.legs],
                         style, fixed_labels, exclusions)
    except LayoutError:
        reserved = [leg for route in (*fixed_fibers.values(), *opens) for leg in route.legs]
        labels = _labels(placements, segments + reserved + leads, style, fixed_labels, exclusions)
        fibers = [fixed_fibers[edge.id] if edge.id in fixed_fibers
                  else route_connection(edge, placements, style, labels) for edge in edges] + opens
    for index, label in enumerate(labels):
        if any(overlap(label.bounds, other.bounds, 3) for other in labels[index + 1:]):
            raise LayoutError(f"{label.optic}: stage labels overlap")
        if any(overlap(label.bounds, p.bounds, 3) for p in placements.values()):
            raise LayoutError(f"{label.optic}: stage label overlaps component artwork")
        if any(segment_intersects(s.start, s.end, label.bounds) for s in segments):
            raise LayoutError(f"{label.optic}: beam crosses a stage label")

    fibers = refine_routes(edges, placements, style, labels, fibers, fixed_fibers)
    for route in fibers:
        for leg in route.legs:
            if any(segment_intersects(leg.start, leg.end, p.bounds) for p in placements.values()
                   if p.id not in {route.source, route.target}):
                raise LayoutError(f"{route.id}: stage fiber crosses unrelated artwork")
            if any(segment_intersects(leg.start, leg.end, label.bounds) for label in labels):
                raise LayoutError(f"{route.id}: stage fiber crosses a label")
    return _assemble_layout(placements, segments, labels, style, fibers)


def _place_children(scope, setup, style, children):
    blocks = {group.entry: _group(setup, group, style) for group in children}
    placements = _place(scope, style, blocks, drawing=setup)
    moved = []
    for entry, block in blocks.items():
        a, b = block.placements[entry].position, placements[entry].position
        moved.append(_translate(block, (b[0] - a[0], b[1] - a[1])))
    return _finish(setup, placements, style, moved)


def _group(setup, group, style):
    if not group.rows:
        scope = Setup()
        scope._nodes = {ident: node for ident, node in setup._nodes.items() if ident in group.members}
        scope._connections = [edge for edge in setup.connections
                              if edge.source in group.members and edge.target in group.members]
        # This root anchors placement only. Actual roots and port occupancy
        # still come from the original setup when drawing and measuring content.
        scope._roots = [Root(group.entry, None, 0, group.origin)]
        return _place_children(scope, setup, style, group.children)

    children, placements = [], {}
    gap = max(group.gap if group.gap is not None else style.pitch,
              2 * max(style.clearance, style.fiber_width))
    entry_x = None
    bottom = None
    for child in group.children:
        measured = _group(setup, child, style)
        entry = measured.placements[child.entry].position
        bounds = _content_bounds(measured.placements, measured.segments, measured.labels, measured.fibers)
        if entry_x is None:
            entry_x = entry[0]
        else:
            # Measure content directly: subtracting a potentially large canvas
            # margin back out of Layout.bounds would introduce roundoff here.
            delta = entry_x - entry[0], bottom + gap - bounds[1]
            measured = _translate(measured, delta)
            bounds = translated(bounds, delta)
            blocks = {next(iter(item.placements)): item for item in (*children, measured)}
            if _collides(measured.placements, placements, setup, style, 0, blocks):
                # Keep the entry x coordinate and minimum content gap. Extend
                # the row only when boundary connector space requires it.
                combined = {**placements, **measured.placements}
                geometry = occupied_geometry(setup, combined, style, blocks)
                bottom_used = geometry.bounds(combined, within=placements)[3]
                top_used = geometry.bounds(combined, within=measured.placements)[1]
                extra = max(0, bottom_used + gap - top_used)
                measured = _translate(measured, (0, extra))
                bounds = translated(bounds, (0, extra))
        children.append(measured)
        placements.update(measured.placements)
        bottom = bounds[3]
    return _finish(setup, placements, style, children)


def grouped_layout(setup: Setup, style) -> Layout:
    _validate(setup)
    return _place_children(setup, setup, style, setup._layout_groups)
