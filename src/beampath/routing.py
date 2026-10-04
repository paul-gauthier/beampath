"""Deterministic orthogonal fiber routing; no routing vertices enter the graph."""
from __future__ import annotations

from dataclasses import replace
import heapq
import math

from .errors import LayoutError
from .fiber_conflicts import conflict_score, leg_contacts, route_set_score, shared_attachments
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


def orthogonal_path(start, end, boxes, first_direction, last_direction, margin,
                    peers=(), clearance=None, prefix=None, suffix=None, attachments=()):
    """Visibility-grid search ordered by contacts, overlap, bends and length."""
    clearance = margin if clearance is None else clearance
    xs = {start[0], end[0]}
    ys = {start[1], end[1]}
    for x0, y0, x1, y1 in boxes:
        xs.update((x0, x1))
        ys.update((y0, y1))
    for peer in peers:
        for x, y in peer.points:
            xs.update((x - clearance, x, x + clearance))
            ys.update((y - clearance, y, y + clearance))
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

    contact_cache = {}

    def contact_cost(a, b, include_start=False):
        key = a, b, include_start
        if key not in contact_cache:
            count, shared_length = 0, 0.0
            length = math.dist(a, b)
            if length > EPSILON:
                for index, peer in enumerate(peers):
                    for low, high in leg_contacts(a, b, peer):
                        if high - low <= EPSILON and attachments:
                            p = (a[0] + (b[0] - a[0]) * low / length,
                                 a[1] + (b[1] - a[1]) * low / length)
                            if any(math.dist(p, q) <= EPSILON for q in attachments[index]):
                                continue
                        # The previous edge already counted contact at this
                        # vertex. Continuing an overlap adds length, not a new
                        # event. This also handles turns and grid subdivisions.
                        count += int(include_start or low > EPSILON)
                        shared_length += high - low
            contact_cache[key] = count, shared_length
        return contact_cache[key]

    initial = (first, first_direction)
    initial_contacts = contact_cost(prefix, start, True) if prefix is not None else (0, 0.0)
    costs = {initial: (*initial_contacts, 0, 0.0)}
    previous = {}
    queue = [(*costs[initial], first, first_direction)]
    best = None
    while queue:
        contacts, shared_length, bends, length, vertex, direction = heapq.heappop(queue)
        state = vertex, direction
        if costs[state] != (contacts, shared_length, bends, length):
            continue
        if best is not None and (contacts, shared_length, bends, length) > best[0]:
            break
        if vertex == last and not aligned(direction, last_direction + 180):
            tail = contact_cost(end, suffix) if suffix is not None else (0, 0.0)
            score = (contacts + tail[0], shared_length + tail[1],
                     bends + int(not aligned(direction, last_direction)), length)
            if best is None or score < best[0]:
                best = score, state
        for neighbor, outgoing, distance in adjacency[vertex]:
            if aligned(outgoing, direction + 180):
                continue
            added = contact_cost(vertices[vertex], vertices[neighbor], state == initial and prefix is None)
            score = (contacts + added[0], shared_length + added[1],
                     bends + int(not aligned(direction, outgoing)), length + distance)
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


def straight_connection(edge, placements, obstacles, clearance):
    """A direct connection can bypass overlapping endpoint escape corridors."""
    source, target = placements[edge.source], placements[edge.target]
    start, end = source.port_position(edge.output), target.port_position(edge.input)
    direction = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0])) % 360
    if (math.dist(start, end) > EPSILON
            and aligned(direction, source.port_exit_direction(edge.output))
            and aligned(direction + 180, target.port_exit_direction(edge.input))
            and not any(segment_intersects(start, end, inflate(box, clearance))
                        for ident, box in obstacles if ident not in {source.id, target.id})):
        return FiberRoute(edge.id, (start, end), edge.source, edge.output, edge.target, edge.input)
    return None


def route_connection(edge, placements, style, labels=(), peers=()):
    source, target = placements[edge.source], placements[edge.target]
    clearance = max(style.clearance, style.fiber_width)
    start, first = connector_lead(source, edge.output, clearance)
    end, last = connector_lead(target, edge.input, clearance)
    peers = tuple(peer for peer in peers if peer.id != edge.id)
    straight = FiberRoute(edge.id, (start, end), edge.source, edge.output, edge.target, edge.input)
    obstacles = [(p.id, p.bounds) for p in placements.values()]
    obstacles += [(f"label-{label.optic}", label.bounds) for label in labels]
    # A clear straight connection needs no detour or escape corridor. Endpoint
    # clearance boxes may overlap when compactly placed devices face each other.
    direct = straight_connection(edge, placements, obstacles, clearance)
    if direct is not None and not conflict_score(direct, peers)[0]:
        return direct
    try:
        for a, b, owner in ((start, first, source.id), (end, last, target.id)):
            for ident, box in obstacles:
                if ident != owner and segment_intersects(a, b, inflate(box, style.fiber_width / 2)):
                    raise LayoutError(f"fiber connector lead crosses {ident}")
        points = orthogonal_path(
            first, last, [inflate(box, clearance) for _, box in obstacles],
            source.port_exit_direction(edge.output),
            (target.port_exit_direction(edge.input) + 180) % 360, style.pitch,
            peers, clearance, start, end, tuple(shared_attachments(straight, peer) for peer in peers))
    except LayoutError as exc:
        raise LayoutError(f"{edge.id} ({edge.source}.{edge.output} → {edge.target}.{edge.input}): {exc}") from exc
    return FiberRoute(edge.id, simplify((start, *points, end)),
                      edge.source, edge.output, edge.target, edge.input)


def center_route(route, placements, style, labels=(), peers=()):
    """Center movable runs in their clear corridors, keeping length and bends.

    A run can slide without changing length only when its two perpendicular
    neighbors travel in the same direction. Their ends and the nearest obstacle
    on either side bound the safe interval. Visit longer runs first in a single
    deterministic pass; this is a local refinement, not another route search.
    """
    if len(route.points) < 4 or route.source is None or route.target is None:
        return route
    clearance = max(style.clearance, style.fiber_width)
    obstacles = [(p.id, inflate(p.bounds, clearance)) for p in placements.values()]
    obstacles += [(None, inflate(label.bounds, clearance)) for label in labels]
    peers = tuple(peer for peer in peers if peer.id != route.id)
    fiber_boxes = [(None, inflate((min(a[0], b[0]), min(a[1], b[1]),
                                  max(a[0], b[0]), max(a[1], b[1])), clearance))
                   for peer in peers for a, b in zip(peer.points, peer.points[1:])]
    _, first = connector_lead(placements[route.source], route.output, clearance)
    _, last = connector_lead(placements[route.target], route.input, clearance)
    points = list(route.points)
    order = sorted(range(1, len(points) - 2),
                   key=lambda i: (-math.dist(points[i], points[i + 1]), i))
    for i in order:
        a, b, c, d = points[i - 1:i + 3]
        if abs(b[1] - c[1]) < EPSILON:
            along, across = 0, 1
        elif abs(b[0] - c[0]) < EPSILON:
            along, across = 1, 0
        else:
            continue
        if (abs(a[along] - b[along]) > EPSILON
                or abs(c[along] - d[along]) > EPSILON
                or (b[across] - a[across]) * (d[across] - c[across]) <= 0):
            continue
        # Preserve the straight connector escape distances as well as tangents.
        before = first if i == 1 else a
        after = last if i == len(points) - 3 else d
        low, high = sorted((before[across], after[across]))
        left, right = sorted((b[along], c[along]))
        position = b[across]
        for _, box in obstacles + fiber_boxes:
            if box[along] >= right - EPSILON or box[along + 2] <= left + EPSILON:
                continue
            if box[across + 2] <= position + EPSILON:
                low = max(low, box[across + 2])
            elif box[across] >= position - EPSILON:
                high = min(high, box[across])
            else:
                # Labels placed after routing may already be closer than the
                # preferred clearance. Do not move through their padded bounds.
                low = high
                break
        if high - low <= EPSILON:
            continue
        middle = (low + high) / 2
        candidate = points.copy()
        for index in (i, i + 1):
            moved = list(candidate[index])
            moved[across] = middle
            candidate[index] = tuple(moved)
        # The neighboring legs change length too. Check all changed geometry;
        # only the endpoint legs may pass through their own connector artwork.
        if any(segment_intersects(candidate[j], candidate[j + 1], box)
               for j in range(i - 1, i + 2) for owner, box in obstacles
               if not (j == 0 and owner == route.source
                       or j == len(points) - 2 and owner == route.target)):
            continue
        trial = replace(route, points=tuple(candidate))
        if conflict_score(trial, peers) > conflict_score(replace(route, points=tuple(points)), peers):
            continue
        points = candidate
    return replace(route, points=tuple(points))


def refine_routes(edges, placements, style, labels, routes, fixed=()):
    """Improve only conflicted movable routes, then safely center the set.

    Every accepted reroute strictly improves the complete set's score; three
    stable-order sweeps bound work even when a crossing cannot be removed.
    Already measured child routes and open stubs remain fixed.
    """
    routes = list(routes)
    fixed = set(fixed)
    by_id = {edge.id: edge for edge in edges}
    order = sorted((i for i, route in enumerate(routes)
                    if route.id in by_id and route.id not in fixed), key=lambda i: routes[i].id)
    for _ in range(3):
        changed = False
        for i in order:
            peers = routes[:i] + routes[i + 1:]
            if not conflict_score(routes[i], peers)[0]:
                continue
            try:
                candidate = route_connection(by_id[routes[i].id], placements, style, labels, peers)
            except LayoutError:
                continue  # The known valid route is still available.
            trial = routes[:i] + [candidate] + routes[i + 1:]
            if route_set_score(trial) < route_set_score(routes):
                routes[i] = candidate
                changed = True
        if not changed:
            break
    for i in order:
        peers = routes[:i] + routes[i + 1:]
        candidate = center_route(routes[i], placements, style, labels, peers)
        trial = routes[:i] + [candidate] + routes[i + 1:]
        if candidate != routes[i] and route_set_score(trial) <= route_set_score(routes):
            routes[i] = candidate
    return routes


def _corner(a, b, c, radius):
    before, after = math.dist(a, b), math.dist(b, c)
    if before < EPSILON or after < EPSILON:
        return None
    r = min(radius, before / 2, after / 2)
    entry = (b[0] + r * (a[0] - b[0]) / before, b[1] + r * (a[1] - b[1]) / before)
    exit = (b[0] + r * (c[0] - b[0]) / after, b[1] + r * (c[1] - b[1]) / after)
    box = (min(entry[0], b[0], exit[0]), min(entry[1], b[1], exit[1]),
           max(entry[0], b[0], exit[0]), max(entry[1], b[1], exit[1]))
    return r, entry, exit, box


def rounded_path(route, radius, obstacles, width, peers=()):
    """SVG path commands, suppressing rounding near artwork, labels or fibers."""
    from .render import number

    obstacles = list(obstacles)
    for peer in peers:
        if peer.id == route.id:
            continue
        obstacles.extend(inflate((min(a[0], b[0]), min(a[1], b[1]),
                                  max(a[0], b[0]), max(a[1], b[1])), width / 2)
                         for a, b in zip(peer.points, peer.points[1:]))
        # Conservatively include the peer's possible rounded corners too, so
        # independently rounding two clear centerlines cannot make them touch.
        obstacles.extend(inflate(corner[3], width / 2)
                         for a, b, c in zip(peer.points, peer.points[1:], peer.points[2:])
                         if (corner := _corner(a, b, c, radius)) is not None)

    def xy(p):
        return f"{number(p[0])},{number(p[1])}"

    points = route.points
    commands = [f"M {xy(points[0])}"]
    for a, b, c in zip(points, points[1:], points[2:]):
        corner = _corner(a, b, c, radius)
        if corner is None:
            continue
        r, entry, exit, box = corner
        if r and not any(overlap(inflate(box, width / 2), obstacle) for obstacle in obstacles):
            commands.extend((f"L {xy(entry)}", f"Q {xy(b)} {xy(exit)}"))
        else:
            commands.append(f"L {xy(b)}")
    commands.append(f"L {xy(points[-1])}")
    return " ".join(commands)
