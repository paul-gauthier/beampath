"""Contacts between drawn fibers, independent of optical graph connectivity."""
from __future__ import annotations

import math

from .geometry import EPSILON


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _segment_contact(a, b, c, d):
    """Return the contact interval in distance along a→b, or None.

    Intersections include endpoints and oblique leads. A point has zero extent;
    collinear runs retain their overlapping length.
    """
    if any(max(a[i], b[i]) < min(c[i], d[i]) - EPSILON
           or max(c[i], d[i]) < min(a[i], b[i]) - EPSILON for i in (0, 1)):
        return None
    r, s = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
    length, other_length = math.hypot(*r), math.hypot(*s)
    if length <= EPSILON or other_length <= EPSILON:
        return None
    q = c[0] - a[0], c[1] - a[1]
    determinant = _cross(r, s)
    if abs(determinant) > EPSILON * max(length, other_length):
        t, u = _cross(q, s) / determinant, _cross(q, r) / determinant
        if -EPSILON / length <= t <= 1 + EPSILON / length and -EPSILON / other_length <= u <= 1 + EPSILON / other_length:
            distance = min(length, max(0, t * length))
            return distance, distance
        return None
    if abs(_cross(q, r)) > EPSILON * length:
        return None
    project = lambda p: ((p[0] - a[0]) * r[0] + (p[1] - a[1]) * r[1]) / length
    low, high = sorted((project(c), project(d)))
    low, high = max(0, low), min(length, high)
    if low <= high + EPSILON:
        return low, max(low, high)
    return None


def _merge(intervals):
    merged = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1] + EPSILON:
            merged[-1] = merged[-1][0], max(high, merged[-1][1])
        else:
            merged.append((low, high))
    return merged


def leg_contacts(a, b, peer):
    return _merge(contact for c, d in zip(peer.points, peer.points[1:])
                  if (contact := _segment_contact(a, b, c, d)) is not None)


def shared_attachments(route, peer):
    """Only endpoints belonging to the same physical optic may meet freely."""
    return tuple(p for owner, p in ((route.source, route.start), (route.target, route.end))
                 for other, q in ((peer.source, peer.start), (peer.target, peer.end))
                 if owner is not None and owner == other and math.dist(p, q) <= EPSILON)


def route_contacts(route, peer):
    intervals, offset = [], 0.0
    for a, b in zip(route.points, route.points[1:]):
        intervals.extend((low + offset, high + offset) for low, high in leg_contacts(a, b, peer))
        offset += math.dist(a, b)
    shared = shared_attachments(route, peer)
    result = []
    for low, high in _merge(intervals):
        if high - low <= EPSILON:
            endpoint = route.start if low <= EPSILON else (route.end if high >= offset - EPSILON else None)
            if endpoint is not None and any(math.dist(endpoint, p) <= EPSILON for p in shared):
                continue
        result.append((low, high))
    return tuple(result)


def conflict_score(route, peers):
    contacts = [interval for peer in peers if peer.id != route.id for interval in route_contacts(route, peer)]
    return len(contacts), round(sum(high - low for low, high in contacts), 7)


def route_set_score(routes):
    contacts = [interval for i, route in enumerate(routes) for peer in routes[i + 1:]
                for interval in route_contacts(route, peer)]
    # Collinear subdivisions are not bends. Import lazily to avoid a module
    # cycle with the search implementation.
    from .routing import simplify
    return (len(contacts), round(sum(high - low for low, high in contacts), 7),
            sum(len(simplify(route.points)) - 2 for route in routes),
            round(sum(route.length for route in routes), 7))
