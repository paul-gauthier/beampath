"""Shared readable spacing and affine origins for label geometry."""
from __future__ import annotations

from .geometry import Bounds


Anchor = str | tuple[tuple[str, float], ...]


def clearance(style):
    """Reserve one em around unrelated text and for clear label ownership."""
    return max(3.0, style.font_size)


def bounds_distance(a: Bounds, b: Bounds) -> float:
    """Minimum square padding that makes two rectangles touch.

    This uses the same axis-aligned metric as ``overlap(..., padding)`` and
    the separating constraints, including for diagonally separated boxes.
    """
    return max(a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3], 0.0)


def origin(anchor: Anchor, placements):
    """Resolve a component origin or a weighted combination of origins."""
    if isinstance(anchor, str):
        return placements[anchor].position
    return tuple(sum(weight * placements[ident].position[axis]
                     for ident, weight in anchor) for axis in (0, 1))


def project_origin(anchor: Anchor, offset, axis, xs, ys):
    """Project an affine origin and fixed offset onto a separating axis."""
    terms = ((anchor, 1.0),) if isinstance(anchor, str) else anchor
    return (sum(weight * (xs[ident] * axis[0] + ys[ident] * axis[1])
                for ident, weight in terms)
            + offset[0] * axis[0] + offset[1] * axis[1])
