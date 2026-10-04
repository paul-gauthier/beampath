"""Place beam sections and heading-free fiber components, then route cables."""
from __future__ import annotations

from dataclasses import replace
import math

from .errors import LayoutError
from .geometry import add, aligned, overlap, translated, unit
from .layout import (
    FiberRoute, PlacedOptic, Segment, _assemble_layout, _beam_segments,
    _labels, _project, _root_origins, _solve_beams, footprint, segment_intersects,
)
from .routing import connector_lead, inflate, refine_routes, route_connection
from .occupied import occupied_geometry
from .labels import LabelPlacementError, space_labels


def _validate(setup):
    reachable = set()
    todo = [r.optic for r in setup._roots]
    outgoing = {}
    for edge in setup.connections:
        outgoing.setdefault(edge.source, []).append(edge.target)
    while todo:
        ident = todo.pop()
        if ident not in reachable:
            reachable.add(ident)
            todo.extend(outgoing.get(ident, ()))
    for node in setup.optics:
        if node.id not in reachable:
            raise LayoutError(f"{node.id}: connect the optic to an initial beam or fiber source")
        if node.heading is None and any(p.medium == "free_space" for p in node.geometry.ports):
            raise LayoutError(f"{node.id}: free-space section has no initial heading")
        for port in node.geometry.ports:
            if port.kind == "input" and port.required and not setup._input_used(node.id, port.name):
                raise LayoutError(f"{node.id}.{port.name}: required input is not connected")


def _sections(nodes, edges, blocks=None):
    neighbors = {ident: [] for ident in nodes}
    for edge in edges:
        if edge.medium == "free_space":
            neighbors[edge.source].append(edge.target)
            neighbors[edge.target].append(edge.source)
    for entry, block in (blocks or {}).items():
        for ident in block.placements:
            if ident != entry:
                neighbors[entry].append(ident)
                neighbors[ident].append(entry)
    sections, membership = [], {}
    for ident in nodes:
        if ident in membership:
            continue
        todo, members = [ident], set()
        while todo:
            current = todo.pop()
            if current not in members:
                members.add(current)
                todo.extend(neighbors[current])
        ordered = [key for key in nodes if key in members]
        for key in ordered:
            membership[key] = len(sections)
        sections.append(ordered)
    return sections, membership


def _nearest_hint(ident, edges, hints, forward):
    todo, seen = [ident], {ident}
    while todo:
        current = todo.pop(0)
        for edge in edges:
            if (edge.source if forward else edge.target) != current:
                continue
            neighbor = edge.target if forward else edge.source
            if neighbor in seen:
                continue
            if neighbor in hints:
                return hints[neighbor]
            seen.add(neighbor)
            todo.append(neighbor)
    return None


def _initial_rotation(node, edges, hints):
    before = _nearest_hint(node.id, edges, hints, False)
    after = _nearest_hint(node.id, edges, hints, True)
    own = hints.get(node.id)
    a, b = (own, after) if own is not None and after is not None else (
        (before, own) if before is not None and own is not None else (before, after))
    if a is None or b is None or a == b:
        return 0
    angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360
    return min((0, 90, 180, 270), key=lambda r: abs((r - angle + 180) % 360 - 180))


def _move(placements, delta):
    return {ident: replace(p, position=add(p.position, delta), bounds=translated(p.bounds, delta))
            for ident, p in placements.items()}


def _collides(candidate, placed, drawing, style, blocks=None):
    combined = {**placed, **candidate}
    return occupied_geometry(drawing, combined, style, blocks).conflict(
        combined, style, across=candidate)


def _place(setup, style, blocks=None, *, drawing=None):
    drawing = setup if drawing is None else drawing
    blocks = blocks or {}
    grouped = {ident for block in blocks.values() for ident in block.placements}
    nodes = {n.id: n for n in setup.optics}
    # Interior pins belong to the group's frame. Only its entry can pin that
    # frame in the enclosing scope; all interior offsets are solved below.
    nodes = {ident: replace(n, at=None) if ident in grouped and ident not in blocks else n
             for ident, n in nodes.items()}
    beam_edges = [e for e in setup.connections if e.medium == "free_space"]
    fiber_edges = [e for e in setup.connections if e.medium == "fiber"]
    sections, membership = _sections(nodes, setup.connections, blocks)
    anchors = _root_origins(setup)
    hints = {**anchors, **{n.id: n.at for n in nodes.values() if n.at is not None}}
    local, fixed = {}, set()
    # First solve beam sections with all their hard pins; their coordinates can
    # then inform the initial orientation of nearby fiber-only components.
    for index, members in enumerate(sections):
        subset = {ident: nodes[ident] for ident in members}
        if any(ident in hints for ident in members):
            fixed.add(index)
        nested = {entry: block for entry, block in blocks.items() if entry in subset}
        if not nested and all(nodes[ident].heading is None for ident in members):
            continue
        origins = {ident: anchors[ident] for ident in members if ident in anchors}
        if index not in fixed:
            origins[members[0]] = (0, 0)
        local[index], _ = _solve_beams(subset, [e for e in beam_edges if e.source in subset],
                                    origins, style, nested, drawing=drawing)
        if index in fixed:
            hints.update({ident: p.position for ident, p in local[index].items()})
    for index, members in enumerate(sections):
        if index in local:
            continue
        ident, = members
        node = nodes[ident]
        rotation = _initial_rotation(node, fiber_edges, hints)
        position = hints.get(ident, (0, 0))
        local[index] = {ident: PlacedOptic(node, position, translated(footprint(node, rotation), position), rotation)}

    placed, done = {}, set()
    # Fixed beam geometry takes precedence over the drawing pose of a fiber
    # device. A pinned fiber position still permits all four artwork rotations.
    for index in sorted(fixed, key=lambda i: (all(p.instance.heading is None for p in local[i].values()), i)):
        block = local[index]
        if len(block) == 1:
            ident, original = next(iter(block.items()))
            if original.instance.heading is None and ident not in grouped:
                for rotation in dict.fromkeys((original.rotation, 0, 90, 180, 270)):
                    candidate = replace(original, rotation=rotation,
                                        bounds=translated(footprint(original.instance, rotation), original.position))
                    if not _collides({ident: candidate}, placed, drawing, style, blocks):
                        block = {ident: candidate}
                        break
        if collision := _collides(block, placed, drawing, style, blocks):
            raise LayoutError(f"{sections[index][0]}: pinned placement: {collision.context}")
        placed.update(block)
        done.add(index)
    while len(done) < len(sections):
        pending = [index for index in range(len(sections)) if index not in done]
        # Contracting a DAG's free-space sections can introduce a section-level
        # cycle. Prefer ready sections, then the one with most placed neighbors.
        def ready_score(index):
            incoming = [e for e in fiber_edges if membership[e.target] == index
                        and membership[e.source] != index]
            return (any(membership[e.source] not in done for e in incoming),
                    -sum(e.source in placed for e in incoming), index)
        index = min(pending, key=ready_score)
        block = local[index]
        incoming = [e for e in fiber_edges if e.target in block and e.source in placed]
        if incoming:
            edge = incoming[0]
            source = placed[edge.source]
            direction = unit(source.port_exit_direction(edge.output))
            # Separate parallel exits into lanes; perpendicular exits already
            # lead to distinct sides of the source and can run straight out.
            branches = [e for e in fiber_edges if e.source == edge.source
                        and aligned(source.port_exit_direction(e.output),
                                    source.port_exit_direction(edge.output))]
            lane = branches.index(edge)
            lane = ((lane + 1) // 2) * (1 if lane % 2 else -1) if lane else 0
            target_component = block[edge.target]
            if len(block) == 1 and target_component.instance.heading is None and edge.target not in grouped:
                # Orient an unpinned fiber device before positioning its input.
                # Rotating an offset input after placement creates a needless
                # sideways jog and changes the intended connector-to-connector gap.
                desired = (source.port_exit_direction(edge.output) + 180
                           - target_component.instance.port(edge.input).exit_direction) % 360
                rotation = min(dict.fromkeys((target_component.rotation, 0, 90, 180, 270)),
                               key=lambda r: abs((r - desired + 180) % 360 - 180))
                target_component = replace(target_component, rotation=rotation,
                                           bounds=translated(footprint(target_component.instance, rotation),
                                                             target_component.position))
                block = {edge.target: target_component}
            origin = source.port_position(edge.output)
            target = target_component.port_position(edge.input)
            # Like free-space edges, pitch measures the gap between ports.
            # Housing-edge attachments must leave a visible run of cable;
            # measuring center-to-center lets large housings consume the gap.
            clearance = (_project(source.bounds, origin, direction)[1]
                         - _project(target_component.bounds, target, direction)[0] + style.clearance)
            if not aligned(source.port_exit_direction(edge.output) + 180,
                           target_component.port_exit_direction(edge.input)):
                # Turning connections need space for both connector escape
                # corridors, including the larger projection at oblique exits.
                margin = max(style.clearance, style.fiber_width)
                clearance = (_project(inflate(source.bounds, margin), origin, direction)[1]
                             - _project(inflate(target_component.bounds, margin), target, direction)[0])
            gap = max(style.pitch, clearance)
            delta = add(origin, (gap * direction[0], gap * direction[1]))
            delta = add(delta, (-direction[1] * lane * style.pitch, direction[0] * lane * style.pitch))
            delta = delta[0] - target[0], delta[1] - target[1]
        else:
            right = max((p.bounds[2] for p in placed.values()), default=0)
            left = min(p.bounds[0] for p in block.values())
            delta = right + style.pitch - left, 0
        candidate = _move(block, delta)
        # Shift an unpinned section to a clear lane, preserving its solved beam
        # geometry. The fallback clears all measured content, not just artwork.
        if _collides(candidate, placed, drawing, style, blocks):
            combined = {**placed, **candidate}
            geometry = occupied_geometry(drawing, combined, style, blocks)
            right = geometry.bounds(combined, within=placed)[2]
            left = geometry.bounds(combined, within=candidate)[0]
            gap = max(style.pitch, style.clearance, 3)
            candidate = _move(candidate, (max(gap, right + gap - left), 0))
        if collision := _collides(candidate, placed, drawing, style, blocks):
            raise LayoutError(f"{sections[index][0]}: cannot place fiber-connected section: {collision.context}")
        placed.update(candidate)
        done.add(index)
    return {ident: replace(placed[ident], instance=setup._nodes[ident]) for ident in nodes}


def _orient_fiber_components(placements, edges, drawing, style, fixed=(), blocks=None):
    # Select the drawing pose using actual neighboring ports, after placement.
    # The graph's heading remains None and its geometry is never rewritten.
    for ident, original in list(placements.items()):
        if original.instance.heading is not None or ident in fixed:
            continue
        incident = [e for e in edges if ident in {e.source, e.target}]
        if not incident:
            continue
        best = None
        for rotation in dict.fromkeys((original.rotation, 0, 90, 180, 270)):
            bounds = translated(footprint(original.instance, rotation), original.position)
            if any(overlap(bounds, p.bounds, style.clearance) for key, p in placements.items() if key != ident):
                continue
            candidate = replace(original, rotation=rotation, bounds=bounds)
            if _collides({ident: candidate}, {key: p for key, p in placements.items() if key != ident},
                         drawing, style, blocks):
                continue
            trial = {**placements, ident: candidate}
            try:
                labels = tuple(label for block in (blocks or {}).values() for label in block.labels)
                routes = [route_connection(edge, trial, style, labels) for edge in incident]
            except LayoutError:
                continue
            score = sum(len(r.points) - 2 for r in routes), sum(r.length for r in routes)
            if best is None or score < best[0]:
                best = score, candidate
        if best is not None:
            placements[ident] = best[1]


def _open_fibers(setup, placements, style):
    routes = []
    connected_inputs = {(edge.target, edge.input) for edge in setup.connections}
    for p in placements.values():
        for index, port in enumerate(p.instance.geometry.ports):
            if port.medium != "fiber":
                continue
            output = port.kind == "output" and port.draw_open and not setup._output_used(p.id, port.name)
            incoming = (port.kind == "input" and port.draw_lead_in
                        and (p.id, port.name) not in connected_inputs)
            if not (output or incoming):
                continue
            a, nearest = connector_lead(p, port.name, style.clearance)
            direction = unit(p.port_exit_direction(port.name))
            length = max(style.open_length, math.dist(a, nearest))
            b = add(a, (length * direction[0], length * direction[1]))
            if any(segment_intersects(a, b, other.bounds) for other in placements.values() if other.id != p.id):
                b = nearest
                if any(segment_intersects(a, b, other.bounds) for other in placements.values() if other.id != p.id):
                    raise LayoutError(f"{p.id}.{port.name}: open fiber lead crosses unrelated artwork")
            if output:
                routes.append(FiberRoute(f"stub-{p.id}-{index:02d}", (a, b), p.id, port.name))
            else:
                routes.append(FiberRoute(f"lead-in-{p.id}-{index:02d}", (b, a), None, None, p.id, port.name))
    return routes


def mixed_layout(setup, style):
    _validate(setup)
    placements = _place(setup, style)
    edges = [e for e in setup.connections if e.medium == "fiber"]
    _orient_fiber_components(placements, edges, setup, style)
    segments = _beam_segments(setup, placements, style)
    open_routes = _open_fibers(setup, placements, style)
    fibers = [route_connection(edge, placements, style) for edge in edges] + open_routes
    try:
        labels = _labels(placements, segments + [leg for r in fibers for leg in r.legs], style)
    except LabelPlacementError:
        # Reserve the straight connector leads while trying label positions,
        # then route cable interiors around the resulting label obstacles.
        leads = [leg for r in open_routes for leg in r.legs]
        for edge in edges:
            for ident, name in ((edge.source, edge.output), (edge.target, edge.input)):
                a, b = connector_lead(placements[ident], name, max(style.clearance, style.fiber_width))
                leads.append(Segment(f"lead-{ident}-{name}", a, b, ident, name))
        try:
            labels = _labels(placements, segments + leads, style)
        except LabelPlacementError:
            placements, labels = space_labels(setup, placements, style)
            segments = _beam_segments(setup, placements, style)
            open_routes = _open_fibers(setup, placements, style)
        fibers = [route_connection(edge, placements, style, labels) for edge in edges] + open_routes
    fibers = refine_routes(edges, placements, style, labels, fibers)
    return _assemble_layout(placements, segments, labels, style, fibers)
