"""Measure local stage frames, arrange rows, then route between the frames."""
from __future__ import annotations

from dataclasses import replace

from .fiber_layout import _collides, _orient_fiber_components, _place, _validate
from .geometry import add, translated
from .layout import Layout, _content_bounds
from .model import Root, Setup
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


def _finish(setup, placements, style, children=(), *, scope=None, resolved_labels=None):
    """Finish the surrounding scope while retaining measured child frames."""
    from .labels import finish_layout

    fixed_nodes = {ident for child in children for ident in child.placements}
    blocks = {next(iter(child.placements)): child for child in children}
    edges = [edge for edge in setup.connections if edge.medium == "fiber"
             and edge.source in placements and edge.target in placements]
    if resolved_labels is None:
        _orient_fiber_components(placements, edges, setup, style, fixed_nodes, blocks)
    return finish_layout(setup, placements, style, scope=scope, blocks=blocks)


def _place_children(scope, setup, style, children):
    blocks = {group.entry: _group(setup, group, style) for group in children}
    placements = _place(scope, style, blocks, drawing=setup)
    moved = []
    for entry, block in blocks.items():
        a, b = block.placements[entry].position, placements[entry].position
        moved.append(_translate(block, (b[0] - a[0], b[1] - a[1])))
    return _finish(setup, placements, style, moved, scope=scope)


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
            if _collides(measured.placements, placements, setup, style, blocks):
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
