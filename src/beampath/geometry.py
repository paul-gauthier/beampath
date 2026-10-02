"""Clockwise angles in a drawing coordinate system: x east, y south."""
from __future__ import annotations

import math

from .errors import ComponentError

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]
EPSILON = 1e-7


def finite(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ComponentError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ComponentError(f"{name} must be a finite number")
    return result


def point(value: Point, name: str = "position") -> Point:
    try:
        x, y = value
    except (TypeError, ValueError) as exc:
        raise ComponentError(f"{name} must contain two coordinates") from exc
    return finite(x, name), finite(y, name)


def heading(value: str | float) -> float:
    if isinstance(value, str):
        directions = {"east": 0, "south": 90, "west": 180, "north": 270}
        if value.lower() not in directions:
            raise ComponentError(f"Unknown beam direction {value!r}")
        return float(directions[value.lower()])
    return finite(value, "direction") % 360


def aligned(a: float, b: float) -> bool:
    return abs((a - b + 180) % 360 - 180) < EPSILON


def unit(angle: float) -> Point:
    a = math.radians(angle)
    return clean(math.cos(a)), clean(math.sin(a))


def rotate(p: Point, angle: float) -> Point:
    c, s = unit(angle)
    return clean(c * p[0] - s * p[1]), clean(s * p[0] + c * p[1])


def clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-10 else value


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def overlap(a: Bounds, b: Bounds, padding: float = 0) -> bool:
    return (a[0] < b[2] + padding - EPSILON and b[0] < a[2] + padding - EPSILON
            and a[1] < b[3] + padding - EPSILON and b[1] < a[3] + padding - EPSILON)


def translated(b: Bounds, p: Point) -> Bounds:
    return b[0] + p[0], b[1] + p[1], b[2] + p[0], b[3] + p[1]


def envelope(points: list[Point]) -> Bounds:
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def reflection(incoming: float, normal_angle: float) -> float:
    """Normal is relative to incoming heading; d' = d - 2(d·n)n."""
    return (incoming + 180 + 2 * normal_angle) % 360
