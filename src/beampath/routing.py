"""Deterministic orthogonal fiber routing; no routing vertices enter the graph."""
from __future__ import annotations

import heapq
import math

from .errors import LayoutError
from .geometry import EPSILON, add, aligned, overlap, unit
from .layout import FiberRoute, _project, segment_intersects


def inflate(box, amount):
    return box[0] - amount, box[1] - amount, box[2] + amount, box[3] + amount


def simplify(points):
    result = []
    for p in points:
        if result and math.dist(result[-1], p) < EPSILON:
            continue
        while len(result) > 1:
            a, b = result[-2:]
            u, v = (b[0] - a[0], b[1] - a[1]), (p[0] - b[0], p[1] - b[1])
            if abs(u[0] * v[1] - u[1] * v[0]) > EPSILON or u[0] * v[0] + u[1] * v[1] <= 0:
                break
            result.pop()
        result.append(p)
    return tuple(result)


def connector_lead(placed, name, clearance):
    start = placed.port_position(name)
    direction = unit(placed.port_exit_direction(name))
    reach = max(0, _project(placed.bounds, start, direction)[1])
    length = reach + clearance
    return start, add(start, (direction[0] * length, direction[1] * length))


def orthogonal_path(start, end, boxes, first_direction, last_direction, margin):
    """Visibility-grid Dijkstra, ordered by bend count and then drawn length."""
    xs = {start[0], end[0]}
    ys = {start[1], end[1]}
    for x0, y0, x1, y1 in boxes:
        xs.update((x0, x1))
        ys.update((y0, y1))
    xs.update((min(xs) - margin, max(xs) + margin))
    ys.update((min(ys) - margin, max(ys) + margin))
    xs, ys = sorted(xs), sorted(ys)

    def inside(p):
        return any(x0 + EPSILON < p[0] < x1 - EPSILON and
                   y0 + EPSILON < p[1] < y1 - EPSILON for x0, y0, x1, y1 in boxes)

    vertices = {(i, j): (x, y) for i, x in enumerate(xs) for j, y in enumerate(ys)
                if not inside((x, y))}
    first = (xs.index(start[0]), ys.index(start[1]))
    last = (xs.index(end[0]), ys.index(end[1]))
    if first not in vertices or last not in vertices:
        raise LayoutError("fiber connector has insufficient clearance")
    adjacency = {v: [] for v in vertices}
    for (i, j), a in vertices.items():
        for neighbor, direction in (((i + 1, j), 0), ((i, j + 1), 90)):
            if neighbor not in vertices:
                continue
            b = vertices[neighbor]
            if not any(segment_intersects(a, b, box) for box in boxes):
                distance = math.dist(a, b)
                adjacency[i, j].append((neighbor, direction, distance))
                adjacency[neighbor].append(((i, j), (direction + 180) % 360, distance))

    initial = (first, first_direction)
    costs = {initial: (0, 0.0)}
    previous = {}
    queue = [(0, 0.0, first, first_direction)]
    best = None
    while queue:
        bends, length, vertex, direction = heapq.heappop(queue)
        state = vertex, direction
        if costs[state] != (bends, length):
            continue
        if best is not None and (bends, length) > best[0]:
            break
        if vertex == last and not aligned(direction, last_direction + 180):
            score = (bends + int(not aligned(direction, last_direction)), length)
            if best is None or score < best[0]:
                best = score, state
        for neighbor, outgoing, distance in adjacency[vertex]:
            if aligned(outgoing, direction + 180):
                continue
            score = bends + int(not aligned(direction, outgoing)), length + distance
            next_state = neighbor, outgoing
            if next_state not in costs or score < costs[next_state]:
                costs[next_state] = score
                previous[next_state] = state
                heapq.heappush(queue, (*score, neighbor, outgoing))
    if best is None:
        raise LayoutError("no clear orthogonal fiber route")
    state = best[1]
    result = [vertices[state[0]]]
    while state != initial:
        state = previous[state]
        result.append(vertices[state[0]])
    return tuple(reversed(result))


def route_connection(edge, placements, style, labels=()):
    source, target = placements[edge.source], placements[edge.target]
    clearance = max(style.clearance, style.fiber_width)
    start, first = connector_lead(source, edge.output, clearance)
    end, last = connector_lead(target, edge.input, clearance)
    obstacles = [(p.id, p.bounds) for p in placements.values()]
    obstacles += [(f"label-{label.optic}", label.bounds) for label in labels]
    # A clear straight connection needs no detour or escape corridor. Endpoint
    # clearance boxes may overlap when compactly placed devices face each other.
    direction = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0])) % 360
    if (math.dist(start, end) > EPSILON
            and aligned(direction, source.port_exit_direction(edge.output))
            and aligned(direction + 180, target.port_exit_direction(edge.input))
            and not any(segment_intersects(start, end, inflate(box, clearance))
                        for ident, box in obstacles if ident not in {source.id, target.id})):
        return FiberRoute(edge.id, (start, end), edge.source, edge.output, edge.target, edge.input)
    try:
        for a, b, owner in ((start, first, source.id), (end, last, target.id)):
            for ident, box in obstacles:
                if ident != owner and segment_intersects(a, b, inflate(box, style.fiber_width / 2)):
                    raise LayoutError(f"fiber connector lead crosses {ident}")
        points = orthogonal_path(
            first, last, [inflate(box, clearance) for _, box in obstacles],
            source.port_exit_direction(edge.output),
            (target.port_exit_direction(edge.input) + 180) % 360, style.pitch)
    except LayoutError as exc:
        raise LayoutError(f"{edge.id} ({edge.source}.{edge.output} → {edge.target}.{edge.input}): {exc}") from exc
    return FiberRoute(edge.id, simplify((start, *points, end)),
                      edge.source, edge.output, edge.target, edge.input)


def rounded_path(route, radius, obstacles, width):
    """SVG path commands, with rounding suppressed near artwork or labels."""
    from .render import number

    def xy(p):
        return f"{number(p[0])},{number(p[1])}"

    points = route.points
    commands = [f"M {xy(points[0])}"]
    for a, b, c in zip(points, points[1:], points[2:]):
        before, after = math.dist(a, b), math.dist(b, c)
        r = min(radius, before / 2, after / 2)
        if before < EPSILON or after < EPSILON:
            continue
        u = ((a[0] - b[0]) / before, (a[1] - b[1]) / before)
        v = ((c[0] - b[0]) / after, (c[1] - b[1]) / after)
        entry = (b[0] + r * u[0], b[1] + r * u[1])
        exit = (b[0] + r * v[0], b[1] + r * v[1])
        box = (min(entry[0], b[0], exit[0]), min(entry[1], b[1], exit[1]),
               max(entry[0], b[0], exit[0]), max(entry[1], b[1], exit[1]))
        if r and not any(overlap(inflate(box, width / 2), obstacle) for obstacle in obstacles):
            commands.extend((f"L {xy(entry)}", f"Q {xy(b)} {xy(exit)}"))
        else:
            commands.append(f"L {xy(b)}")
    commands.append(f"L {xy(points[-1])}")
    return " ".join(commands)
